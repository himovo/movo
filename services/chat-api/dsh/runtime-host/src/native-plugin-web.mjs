import { request as httpRequest } from 'node:http'

import { allowedPluginUiRequest, safePluginRoutes } from './plugin-ui-route-policy.mjs'
import { clientShellSource, injectPluginClientShell, isClientShellRequest } from './plugin-client-boot.mjs'
import { proxyPluginUiSocket, rejectUpgrade } from './plugin-ui-websocket.mjs'

const REQUEST_HEADERS = new Set([
  'accept', 'accept-language', 'content-type', 'content-length', 'range',
  'if-none-match', 'if-modified-since',
])
const RESPONSE_HEADERS = new Set([
  'content-type', 'content-length', 'content-encoding', 'cache-control', 'etag',
  'last-modified', 'content-range', 'accept-ranges', 'vary',
])

function requestLocal(port, path, headers = {}, method = 'GET') {
  return httpRequest({ hostname: '127.0.0.1', port, path, method, headers })
}

async function browserCookie(connection, port) {
  const launch = new URL(connection.authenticatedUrl(`http://127.0.0.1:${port}/`))
  return await new Promise((resolve, reject) => {
    const request = requestLocal(port, `${launch.pathname}${launch.search}`)
    request.on('response', response => {
      response.resume()
      const cookie = response.headers['set-cookie']?.[0]?.split(';', 1)[0]
      if (response.statusCode !== 303 || !cookie) reject(new Error('DSH browser session could not be initialized'))
      else resolve(cookie)
    })
    request.once('error', reject)
    request.end()
  })
}

export class NativePluginWeb {
  #cookie

  constructor(ctx, plugins) {
    this.ctx = ctx
    this.plugins = plugins ?? []
  }

  async proxyUpgrade(pluginId, request, socket, head) {
    const plugin = this.plugins.find(item => item.installation_id === pluginId)
    const webServer = this.ctx.get('webServer')
    const connection = this.ctx.get('connection')
    if (!plugin?.client_modules?.length || !webServer?.port || !connection ||
        new URL(request.url, 'http://plugin-ui.invalid').pathname !== '/api/remote.mux') {
      rejectUpgrade(socket)
      return
    }
    this.#cookie ??= await browserCookie(connection, webServer.port)
    proxyPluginUiSocket(request, socket, head, {
      url: `ws://127.0.0.1:${webServer.port}/api/remote.mux`,
      headers: { cookie: this.#cookie },
    }, { endpoints: plugin.remote_endpoints ?? [] })
  }

  async proxy(pluginId, path, request, response) {
    const plugin = this.plugins.find(item => item.installation_id === pluginId)
    const routes = safePluginRoutes(plugin?.web_routes)
    const webServer = this.ctx.get('webServer')
    const connection = this.ctx.get('connection')
    const pathname = new URL(path, 'http://plugin-ui.invalid').pathname
    if (!plugin || !plugin.client_modules?.length || !webServer?.port || !connection ||
        !isClientShellRequest(pathname, request.method) &&
        !allowedPluginUiRequest({ method: request.method, path: pathname, routes,
          remoteEndpoints: plugin.remote_endpoints, pluginName: plugin.name,
          hasGenericApiRoute: plugin.web_routes?.some(route => route.kind === 'prefix' && route.path === '/api') })) {
      response.writeHead(403)
      response.end()
      return
    }
    if (isClientShellRequest(pathname, request.method)) {
      response.writeHead(200, { 'content-type': 'text/javascript; charset=utf-8', 'cache-control': 'public, max-age=3600' })
      response.end(clientShellSource)
      return
    }
    this.#cookie ??= await browserCookie(connection, webServer.port)
    const headers = Object.fromEntries(Object.entries(request.headers).filter(([name]) =>
      REQUEST_HEADERS.has(name) || (name.startsWith('x-') && !name.startsWith('x-forwarded-') && name !== 'x-real-ip')))
    headers.cookie = this.#cookie
    await new Promise((resolve, reject) => {
      const upstream = requestLocal(webServer.port, path, headers, request.method)
      upstream.on('response', result => {
        const responseHeaders = Object.fromEntries(Object.entries(result.headers).filter(([name]) => RESPONSE_HEADERS.has(name)))
        if (pathname === '/' && result.statusCode === 200 && request.method === 'GET') {
          const chunks = []
          result.on('data', chunk => chunks.push(chunk))
          result.once('end', () => {
            try {
              const conversation = new URL(path, 'http://plugin-ui.invalid').searchParams.get('surface') === 'conversation'
              const body = Buffer.from(injectPluginClientShell(Buffer.concat(chunks).toString('utf8'), plugin, { conversation }))
              delete responseHeaders['content-length']
              delete responseHeaders.etag
              response.writeHead(200, responseHeaders)
              response.end(body)
              resolve()
            } catch (error) { reject(error) }
          })
          result.once('error', reject)
          return
        }
        response.writeHead(result.statusCode ?? 502, responseHeaders)
        result.pipe(response)
        result.once('end', resolve)
        result.once('error', reject)
      })
      upstream.once('error', reject)
      request.once('aborted', () => upstream.destroy())
      request.pipe(upstream)
    })
  }
}
