import { createServer } from 'node:http'

import { validBearerToken, assertSecureHost } from './host-auth.mjs'
import { runtimeHealth } from './host-protocol.mjs'
import { readJson, routeParts, sendJson } from './http-utils.mjs'
import { RuntimeManager } from './runtime-manager.mjs'
import { resolveSessionSeed } from './session-seed.mjs'

export class RuntimeHttpServer {
  #server
  #manager
  #started = false

  constructor({ host = '127.0.0.1', port = 0, storageRoot, authToken = '' }) {
    if (!Number.isInteger(port) || port < 0 || port > 65535) throw new TypeError('port must be an integer from 0 to 65535')
    if (authToken && authToken.length < 32) throw new TypeError('authToken must contain at least 32 characters')
    assertSecureHost(host, authToken)
    this.host = host
    this.port = port
    this.authToken = authToken
    this.#manager = new RuntimeManager({ storageRoot })
    this.#server = createServer((request, response) => {
      if (!validBearerToken(request.headers.authorization, this.authToken)) {
        response.setHeader('www-authenticate', 'Bearer realm="askai-dsh-runtime"')
        sendJson(response, 401, { error: { code: 'unauthorized', message: 'valid runtime bearer token required' } })
        return
      }
      this.#dispatch(request, response).catch(error => {
        sendJson(response, 400, {
          error: {
            code: 'kernel_request_failed',
            message: error instanceof Error ? error.message : String(error),
          },
        })
      })
    })
  }

  async start() {
    if (this.#started) return this.address()
    await this.#manager.probe()
    await new Promise((resolvePromise, reject) => {
      const onError = error => reject(error)
      this.#server.once('error', onError)
      this.#server.listen(this.port, this.host, () => {
        this.#server.off('error', onError)
        resolvePromise()
      })
    })
    this.#started = true
    return this.address()
  }

  address() {
    const address = this.#server.address()
    if (address === null || typeof address === 'string') throw new Error('DSH Runtime Host is not listening')
    return { host: this.host, port: address.port }
  }

  async stop() {
    if (!this.#started) return
    this.#started = false
    const closed = new Promise(resolvePromise => this.#server.close(() => resolvePromise()))
    await this.#manager.disposeAll()
    this.#server.closeAllConnections()
    await closed
  }

  async #dispatch(request, response) {
    const { parts, query } = routeParts(request)
    if (request.method === 'GET' && parts.join('/') === 'health') {
      return sendJson(response, 200, runtimeHealth(this.#manager.inventory()))
    }
    if (request.method === 'POST' && parts.join('/') === 'v1/runtimes') {
      const runtime = await this.#manager.create(await readJson(request))
      const health = runtimeHealth([])
      return sendJson(response, 201, {
        runtimeId: runtime.runtimeId,
        kernel: health.kernel,
        kernelVersion: health.version,
        profileVersion: runtime.profileVersion,
        isolationKey: runtime.isolationKey,
      })
    }
    if (request.method === 'GET' && parts.join('/') === 'v1/runtimes') {
      const isolationKey = query.get('isolationKey')
      if (isolationKey === null) return sendJson(response, 200, { runtimes: this.#manager.inventory() })
      const runtime = this.#manager.findByIsolation(isolationKey)
      return sendJson(response, 200, { runtime: runtime === undefined ? null : this.#manager.describe(runtime) })
    }
    if (parts[0] !== 'v1' || parts[1] !== 'runtimes' || parts[2] === undefined) {
      return sendJson(response, 404, { error: { code: 'not_found', message: 'route not found' } })
    }
    const runtimeId = parts[2]
    if (request.method === 'DELETE' && parts.length === 3) {
      await this.#manager.dispose(runtimeId)
      return sendJson(response, 200, { disposed: true })
    }
    const runtime = this.#manager.get(runtimeId)
    if (request.method === 'GET' && parts.length === 3) return sendJson(response, 200, this.#manager.describe(runtime))
    if (parts[3] === 'workspaces') {
      if (request.method === 'GET' && parts.length === 4) {
        return sendJson(response, 200, { workspaces: await runtime.listWorkspaces() })
      }
      if (request.method === 'POST' && parts.length === 4) {
        return sendJson(response, 201, await runtime.createWorkspace(await readJson(request)))
      }
      if (parts[4] !== undefined && request.method === 'PATCH' && parts.length === 5) {
        return sendJson(response, 200, await runtime.renameWorkspace(decodeURIComponent(parts[4]), await readJson(request)))
      }
      if (parts[4] !== undefined && request.method === 'DELETE' && parts.length === 5) {
        return sendJson(response, 200, await runtime.deleteWorkspace(decodeURIComponent(parts[4])))
      }
    }
    if (request.method === 'PUT' && parts[3] === 'model-credential' && parts.length === 4) {
      return sendJson(response, 200, runtime.refreshModelCredential(await readJson(request)))
    }
    if (request.method === 'PUT' && parts[3] === 'tool-credential' && parts.length === 4) {
      return sendJson(response, 200, runtime.refreshToolCredential(await readJson(request)))
    }
    if (request.method === 'POST' && parts[3] === 'sessions' && parts.length === 4) {
      let body = await readJson(request)
      if (Object.hasOwn(body, 'cwd')) throw new Error('raw cwd is forbidden over the Runtime Host API; use workspaceId')
      body = await resolveSessionSeed(this.#manager, body)
      if (body.presetId === 'code') {
        if (body.workspaceId === undefined) throw new Error('Code Session requires a DSH workspaceId')
        if (body.permissionPreset !== undefined && body.permissionPreset !== 'workspace-write') {
          throw new Error('desktop Code Session permissionPreset exceeds MOVO policy')
        }
        body.permissionPreset = 'workspace-write'
      }
      return sendJson(response, 201, await runtime.createSession(body))
    }
    if (parts[3] === 'sessions' && parts[4] !== undefined) {
      const sessionId = decodeURIComponent(parts[4])
      if (request.method === 'GET' && parts.length === 5) return sendJson(response, 200, await runtime.describeLiveSession(sessionId))
      if (request.method === 'POST' && parts[5] === 'resume') return sendJson(response, 200, await runtime.resumeSession(sessionId))
      if (request.method === 'POST' && parts[5] === 'send') {
        return sendJson(response, 202, runtime.send({ sessionId, ...await readJson(request) }))
      }
      if (request.method === 'POST' && parts[5] === 'cancel') {
        const body = await readJson(request)
        return sendJson(response, 202, await runtime.cancel(sessionId, body.cause ?? 'cancelled'))
      }
      if (request.method === 'GET' && parts[5] === 'events') {
        return sendJson(response, 200, { events: runtime.events(sessionId, Number(query.get('after') ?? -1)) })
      }
      if (request.method === 'GET' && parts[5] === 'approvals' && parts.length === 6) {
        return sendJson(response, 200, { approvals: runtime.pendingApprovals(sessionId) })
      }
      if (request.method === 'POST' && parts[5] === 'approvals' && parts[6] !== undefined && parts[7] === 'decision') {
        const body = await readJson(request)
        return sendJson(response, 200, runtime.decideApproval(
          sessionId, decodeURIComponent(parts[6]), body.outcome, body.grantScope ?? 'once',
        ))
      }
      if (request.method === 'GET' && parts[5] === 'event-stream') {
        const writeEvent = event => response.write(`${JSON.stringify(event)}\n`)
        const subscription = runtime.subscribeEvents(sessionId, Number(query.get('after') ?? -1), writeEvent)
        response.writeHead(200, {
          'content-type': 'application/x-ndjson; charset=utf-8',
          'cache-control': 'no-cache, no-transform',
          connection: 'keep-alive',
          'x-accel-buffering': 'no',
        })
        for (const event of subscription.replay) writeEvent(event)
        const heartbeat = setInterval(() => response.write('\n'), 2_000)
        const cleanup = () => {
          clearInterval(heartbeat)
          subscription.unsubscribe()
        }
        request.once('close', cleanup)
        response.once('close', cleanup)
        return
      }
      if (request.method === 'DELETE' && parts.length === 5) {
        return sendJson(response, 200, await runtime.disposeSession(sessionId))
      }
    }
    if (parts[3] === 'plugins') {
      const body = request.method === 'GET' ? {} : await readJson(request)
      if (request.method === 'GET' && parts.length === 4) {
        return sendJson(response, 200, { plugins: runtime.pluginInventory() })
      }
      if (request.method === 'POST' && parts[4] === 'load') return sendJson(response, 200, await runtime.loadPlugin(body.specifier))
      if (request.method === 'POST' && parts[4] === 'probe') return sendJson(response, 200, await runtime.probePlugin(body.specifier))
      if (request.method === 'POST' && parts[4] === 'unload') return sendJson(response, 200, await runtime.unloadPlugin(body.specifier))
    }
    return sendJson(response, 404, { error: { code: 'not_found', message: 'route not found' } })
  }
}
