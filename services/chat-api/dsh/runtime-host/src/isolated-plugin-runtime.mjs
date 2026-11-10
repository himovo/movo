import { randomBytes } from 'node:crypto'
import { spawn } from 'node:child_process'
import { request as httpRequest } from 'node:http'
import { dirname, resolve } from 'node:path'
import { mkdir } from 'node:fs/promises'
import { fileURLToPath } from 'node:url'

import { pluginUserHome } from './plugin-user-home.mjs'

const HOST_ENTRY = resolve(dirname(fileURLToPath(import.meta.url)), 'host.mjs')
const READY_EVENT = 'askai-dsh-runtime-ready'

export function pluginChildEnvironment(token, home) {
  const names = [
    'PATH', 'HOME', 'USERPROFILE', 'APPDATA', 'LOCALAPPDATA', 'SYSTEMROOT',
    'TEMP', 'TMP', 'TMPDIR', 'NODE_ENV', 'DSH_TELEMETRY_DISABLED',
  ]
  const env = Object.fromEntries(names.filter(name => process.env[name] !== undefined)
    .map(name => [name, process.env[name]]))
  env.DSH_RUNTIME_HOST_TOKEN = token
  env.MOVO_DSH_PLUGIN_CHILD = '1'
  env.HOME = home
  env.USERPROFILE = home
  env.APPDATA = resolve(home, 'AppData', 'Roaming')
  env.LOCALAPPDATA = resolve(home, 'AppData', 'Local')
  if (process.versions.electron) env.ELECTRON_RUN_AS_NODE = '1'
  return env
}

function waitForReady(child) {
  return new Promise((resolveReady, rejectReady) => {
    let output = ''
    let errorOutput = ''
    const timeout = setTimeout(() => rejectReady(new Error('isolated plugin Runtime did not start')), 30000)
    const cleanup = () => {
      clearTimeout(timeout)
      child.stdout.off('data', onData)
      child.stderr.off('data', onError)
      child.off('exit', onExit)
      child.off('error', onSpawnError)
    }
    const onSpawnError = error => { cleanup(); rejectReady(error) }
    const onExit = code => { cleanup(); rejectReady(new Error(`isolated plugin Runtime exited (${code}): ${errorOutput.slice(-800)}`)) }
    const onError = chunk => { errorOutput = (errorOutput + String(chunk)).slice(-1600) }
    const onData = chunk => {
      output += String(chunk)
      let lineEnd
      while ((lineEnd = output.indexOf('\n')) >= 0) {
        const line = output.slice(0, lineEnd)
        output = output.slice(lineEnd + 1)
        try {
          const event = JSON.parse(line)
          if (event.type === READY_EVENT && Number.isInteger(event.port)) {
            cleanup()
            resolveReady(event.port)
            return
          }
        } catch { /* DSH may write ordinary startup diagnostics. */ }
      }
    }
    child.on('exit', onExit)
    child.on('error', onSpawnError)
    child.stdout.on('data', onData)
    child.stderr.on('data', onError)
  })
}

function requestJson(port, token, method, path, body) {
  return new Promise((resolveRequest, rejectRequest) => {
    const request = httpRequest({
      hostname: '127.0.0.1', port, path, method,
      headers: { authorization: `Bearer ${token}`, 'content-type': 'application/json' },
    }, response => {
      let text = ''
      response.on('data', chunk => { text += String(chunk) })
      response.on('end', () => {
        let result
        try { result = JSON.parse(text) } catch { rejectRequest(new Error('isolated plugin Runtime returned invalid JSON')); return }
        if (response.statusCode >= 400) rejectRequest(new Error(result?.error?.message || 'isolated plugin Runtime failed'))
        else resolveRequest(result)
      })
    })
    request.on('error', rejectRequest)
    request.end(body === undefined ? undefined : JSON.stringify(body))
  })
}

export class IsolatedPluginRuntimePool {
  #byRuntime = new Map()
  #byIsolation = new Map()

  constructor(storageRoot) { this.storageRoot = storageRoot }

  async create(body) {
    if (this.#byIsolation.has(body.isolationKey)) throw new Error('isolation key already has a Runtime')
    const token = randomBytes(32).toString('hex')
    const home = pluginUserHome(this.storageRoot, body)
    await mkdir(home, { recursive: true })
    const child = spawn(process.execPath, [HOST_ENTRY, '--host', '127.0.0.1', '--port', '0', '--storage-root', this.storageRoot], {
      env: pluginChildEnvironment(token, home), stdio: ['ignore', 'pipe', 'pipe'], windowsHide: true,
    })
    let port
    try {
      port = await waitForReady(child)
      const created = await requestJson(port, token, 'POST', '/v1/runtimes', body)
      const runtime = await requestJson(port, token, 'GET', `/v1/runtimes/${created.runtimeId}`)
      const entry = { child, port, token, runtime }
      child.stdout.on('data', () => {})
      child.stderr.on('data', () => {})
      this.#byRuntime.set(runtime.runtimeId, entry)
      this.#byIsolation.set(body.isolationKey, entry)
      child.once('exit', () => {
        this.#byRuntime.delete(runtime.runtimeId)
        this.#byIsolation.delete(body.isolationKey)
      })
      return runtime
    } catch (error) {
      child.kill('SIGTERM')
      throw error
    }
  }

  get(runtimeId) { return this.#byRuntime.get(runtimeId) }
  upgradeTarget(entry, path) {
    return { url: `ws://127.0.0.1:${entry.port}${path}`,
      headers: { authorization: `Bearer ${entry.token}` } }
  }
  findByIsolation(isolationKey) { return this.#byIsolation.get(isolationKey)?.runtime }
  inventory() { return [...this.#byRuntime.values()].map(entry => entry.runtime) }

  async exportCompletedSeed(runtimeId, sessionId) {
    const entry = this.get(runtimeId)
    if (!entry) throw new Error(`runtime not found: ${runtimeId}`)
    const result = await requestJson(entry.port, entry.token, 'POST',
      `/v1/runtimes/${runtimeId}/seed-export`, { sessionId })
    return result.seed
  }

  async createSession(entry, body) {
    return await requestJson(entry.port, entry.token, 'POST',
      `/v1/runtimes/${entry.runtime.runtimeId}/trusted-session`, body)
  }

  async forward(entry, request, response) {
    const target = new URL(request.url, `http://127.0.0.1:${entry.port}`)
    await new Promise((resolveForward, rejectForward) => {
      let finished = false
      const finish = error => {
        if (finished) return
        finished = true
        if (error) rejectForward(error)
        else resolveForward()
      }
      const upstream = httpRequest(target, {
        method: request.method,
        headers: { ...request.headers, host: `127.0.0.1:${entry.port}`, authorization: `Bearer ${entry.token}` },
      }, result => {
        response.writeHead(result.statusCode ?? 502, result.headers)
        result.pipe(response)
        result.once('end', () => finish())
        result.once('error', finish)
      })
      upstream.once('error', finish)
      response.once('close', () => { upstream.destroy(); finish() })
      request.pipe(upstream)
    })
  }

  async dispose(runtimeId, { purge = false } = {}) {
    const entry = this.#byRuntime.get(runtimeId)
    if (!entry) throw new Error(`runtime not found: ${runtimeId}`)
    this.#byRuntime.delete(runtimeId)
    this.#byIsolation.delete(entry.runtime.isolationKey)
    try { await requestJson(entry.port, entry.token, 'DELETE', `/v1/runtimes/${runtimeId}${purge ? '?purge=1' : ''}`) }
    finally { entry.child.kill('SIGTERM') }
  }

  async disposeAll() {
    await Promise.allSettled([...this.#byRuntime.keys()].map(runtimeId => this.dispose(runtimeId)))
  }
}
