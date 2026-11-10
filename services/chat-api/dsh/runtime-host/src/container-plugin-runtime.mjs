import { request as httpRequest } from 'node:http'

import { validBearerToken } from './host-auth.mjs'
import { readJson, sendJson } from './http-utils.mjs'
import { RuntimeIdleReaper } from './runtime-idle-reaper.mjs'
import { preparePluginCredentialRefresh, rewritePluginProfile } from './plugin-credential-relay.mjs'
import { personalSpaceKey } from './personal-space.mjs'

export { rewritePluginProfile } from './plugin-credential-relay.mjs'

async function managerRequest(baseUrl, token, method, path, body) {
  const response = await fetch(`${baseUrl.replace(/\/$/, '')}${path}`, {
    method,
    headers: { authorization: `Bearer ${token}`, 'content-type': 'application/json' },
    ...(body === undefined ? {} : { body: JSON.stringify(body) }),
    signal: AbortSignal.timeout(45_000),
  })
  const value = await response.json().catch(() => ({}))
  if (!response.ok) throw new Error(value.detail || `Sandbox manager returned HTTP ${response.status}`)
  return value
}

function requestJson(entry, method, path, body) {
  return new Promise((resolveRequest, rejectRequest) => {
    const request = httpRequest({
      hostname: entry.host, port: entry.port, path, method,
      headers: { authorization: `Bearer ${entry.token}`, 'content-type': 'application/json' },
      timeout: 120_000,
    }, response => {
      let text = ''
      response.on('data', chunk => { text += String(chunk) })
      response.on('end', () => {
        let result
        try { result = JSON.parse(text) } catch { rejectRequest(new Error('Plugin Runtime returned invalid JSON')); return }
        if (response.statusCode >= 400) rejectRequest(new Error(result?.error?.message || 'Plugin Runtime request failed'))
        else resolveRequest(result)
      })
    })
    request.once('timeout', () => request.destroy(new Error('Plugin Runtime request timed out')))
    request.once('error', rejectRequest)
    request.end(body === undefined ? undefined : JSON.stringify(body))
  })
}

async function waitForReady(entry) {
  const deadline = Date.now() + 45_000
  while (Date.now() < deadline) {
    try {
      const health = await requestJson(entry, 'GET', '/health')
      if (health.ok === true && health.kernel === 'dsh') return
    } catch { /* Startup may still be in progress. */ }
    await new Promise(resolve => setTimeout(resolve, 250))
  }
  throw new Error('Container plugin Runtime did not become healthy')
}

function relayTarget(profile, kind, suffix) {
  const base = kind === 'model' ? profile?.gatewayUrl
    : kind === 'tools' ? profile?.toolProfile?.gatewayUrl
      : kind === 'skill-bundles' ? profile?.bundleGatewayUrl
        : kind === 'plugin-archives' ? profile?.pluginGatewayUrl : undefined
  if (!base) return undefined
  if (kind === 'model' && suffix) return undefined
  const url = new URL(`${base.replace(/\/$/, '')}${suffix}`)
  if (url.protocol !== 'http:' || url.hostname !== 'chat-api') return undefined
  return { url, token: kind === 'tools' ? profile.toolProfile.accessToken : profile.accessToken }
}

export class ContainerPluginRuntimePool {
  #byRuntime = new Map()
  #byIsolation = new Map()
  #byLease = new Map()
  #pending = new Map()
  #reaper

  constructor({ managerUrl, managerToken }) {
    if (!managerUrl || !managerToken) throw new Error('Container plugin Runtime needs manager URL and token')
    this.managerUrl = managerUrl
    this.managerToken = managerToken
    const idleSeconds = Number(process.env.MOVO_SANDBOX_PLUGIN_IDLE_SECONDS ?? 900)
    this.#reaper = new RuntimeIdleReaper({
      idleMs: idleSeconds * 1000,
      onIdle: entry => this.dispose(entry.runtime.runtimeId),
    })
  }

  async create(body) {
    const pending = this.#pending.get(body.isolationKey)
    if (pending) return await pending
    const operation = this.#createFresh(body)
    this.#pending.set(body.isolationKey, operation)
    try { return await operation }
    finally { this.#pending.delete(body.isolationKey) }
  }

  async #createFresh(body) {
    if (this.#byIsolation.has(body.isolationKey)) throw new Error('isolation key already has a Runtime')
    const lease = await managerRequest(this.managerUrl, this.managerToken, 'POST', '/v1/plugin-runtimes', {
      isolation_key: body.isolationKey,
      personal_space_key: personalSpaceKey(body.tenantId, body.modelProfile?.subjectUserId),
    })
    const entry = { ...lease, profile: body.modelProfile, runtime: undefined }
    this.#byLease.set(lease.lease_id, entry)
    try {
      await waitForReady(entry)
      const created = await requestJson(entry, 'POST', '/v1/runtimes', {
        ...body, modelProfile: rewritePluginProfile(body.modelProfile, lease),
      })
      entry.runtime = await requestJson(entry, 'GET', `/v1/runtimes/${created.runtimeId}`)
      this.#byRuntime.set(entry.runtime.runtimeId, entry)
      this.#byIsolation.set(body.isolationKey, entry)
      this.#reaper.add(entry)
      return entry.runtime
    } catch (error) {
      this.#byLease.delete(lease.lease_id)
      await managerRequest(this.managerUrl, this.managerToken, 'DELETE', `/v1/plugin-runtimes/${lease.lease_id}`).catch(() => {})
      throw error
    }
  }

  get(runtimeId) {
    const entry = this.#byRuntime.get(runtimeId)
    if (entry) this.#reaper.touch(entry)
    return entry
  }
  upgradeTarget(entry, path) {
    return { url: `ws://${entry.host}:${entry.port}${path}`,
      headers: { authorization: `Bearer ${entry.token}` } }
  }
  findByIsolation(isolationKey) {
    const entry = this.#byIsolation.get(isolationKey)
    if (entry) this.#reaper.touch(entry)
    return entry?.runtime
  }
  inventory() { return [...this.#byRuntime.values()].map(entry => entry.runtime) }

  async exportCompletedSeed(runtimeId, sessionId) {
    const entry = this.get(runtimeId)
    if (!entry) throw new Error(`runtime not found: ${runtimeId}`)
    const result = await this.#reaper.use(entry, () => requestJson(entry, 'POST', `/v1/runtimes/${runtimeId}/seed-export`, { sessionId }))
    return result.seed
  }

  async createSession(entry, body) {
    return await this.#reaper.use(entry, () => requestJson(entry, 'POST', `/v1/runtimes/${entry.runtime.runtimeId}/trusted-session`, body))
  }

  async forward(entry, request, response) {
    const credential = request.method === 'PUT'
      ? /^\/v1\/runtimes\/[^/]+\/(model|tool)-credential$/.exec(new URL(request.url, 'http://runtime-host.local').pathname)
      : null
    if (credential) {
      const refresh = preparePluginCredentialRefresh(entry, credential[1], await readJson(request))
      const result = await this.#reaper.use(entry, () => requestJson(
        entry, 'PUT', request.url, refresh.forwarded,
      ))
      entry.profile = refresh.profile
      sendJson(response, 200, result)
      return
    }
    await this.#reaper.use(entry, () => new Promise((resolveForward, rejectForward) => {
      const upstream = httpRequest({
        hostname: entry.host, port: entry.port, path: request.url, method: request.method,
        headers: { ...request.headers, host: `${entry.host}:${entry.port}`, authorization: `Bearer ${entry.token}` },
      }, result => {
        response.writeHead(result.statusCode ?? 502, result.headers)
        result.pipe(response)
        result.once('end', resolveForward)
        result.once('error', rejectForward)
      })
      upstream.once('error', rejectForward)
      response.once('close', () => upstream.destroy())
      request.pipe(upstream)
    }))
  }

  async relay(request, response) {
    const url = new URL(request.url, 'http://sandbox-gateway.local')
    const parts = url.pathname.split('/').filter(Boolean)
    const entry = this.#byLease.get(parts[2])
    if (parts[0] !== 'v1' || parts[1] !== 'sandbox-relay' || !entry ||
        !validBearerToken(request.headers.authorization, entry.token)) {
      sendJson(response, 401, { error: { code: 'unauthorized' } })
      return
    }
    const kind = parts[3]
    this.#reaper.touch(entry)
    const method = request.method?.toUpperCase()
    if ((kind === 'model' && method !== 'POST') ||
        (kind === 'tools' && method !== 'POST') ||
        (['skill-bundles', 'plugin-archives'].includes(kind) && method !== 'GET')) {
      sendJson(response, 405, { error: { code: 'method_not_allowed' } })
      return
    }
    const segments = parts.slice(4)
    try {
      for (const segment of segments) {
        const decoded = decodeURIComponent(segment)
        if (!decoded || decoded === '.' || decoded === '..' || /[\\/\0]/.test(decoded)) {
          throw new Error('invalid relay path')
        }
      }
    } catch {
      sendJson(response, 400, { error: { code: 'invalid_path' } })
      return
    }
    const suffix = segments.length ? `/${segments.join('/')}` : ''
    const target = relayTarget(entry.profile, kind, suffix)
    if (!target) {
      sendJson(response, 404, { error: { code: 'not_found' } })
      return
    }
    target.url.search = url.search
    await this.#reaper.use(entry, () => new Promise((resolveRelay, rejectRelay) => {
      const upstream = httpRequest(target.url, {
        method: request.method,
        headers: { ...request.headers, host: target.url.host, authorization: `Bearer ${target.token}` },
      }, result => {
        response.writeHead(result.statusCode ?? 502, result.headers)
        result.pipe(response)
        result.once('end', resolveRelay)
        result.once('error', rejectRelay)
      })
      upstream.once('error', rejectRelay)
      response.once('close', () => upstream.destroy())
      request.pipe(upstream)
    }))
  }

  async dispose(runtimeId) {
    const entry = this.get(runtimeId)
    if (!entry) throw new Error(`runtime not found: ${runtimeId}`)
    await managerRequest(this.managerUrl, this.managerToken, 'DELETE', `/v1/plugin-runtimes/${entry.lease_id}`)
    this.#byRuntime.delete(runtimeId)
    this.#byIsolation.delete(entry.runtime.isolationKey)
    this.#byLease.delete(entry.lease_id)
    this.#reaper.delete(entry)
  }

  async disposeAll() {
    this.#reaper.stop()
    await Promise.allSettled([...this.#byRuntime.keys()].map(id => this.dispose(id)))
  }
}
