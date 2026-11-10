const RESERVED = ['/api', '/plugins', '/assets', '/health', '/v1']
const STATIC_FILES = new Set(['/favicon.svg', '/favicon-dark.svg', '/manifest.webmanifest'])
const MAX_ROUTE_LENGTH = 256
const REMOTE_ENDPOINT = /^[A-Za-z0-9_$.-]+\/[A-Za-z0-9_$.-]+$/
const SESSION_READ_ENDPOINTS = new Set([
  'session/list', 'session/search', 'session/projections', 'session/page',
  'session/control', 'session/follow',
])

function normalizedPath(value) {
  if (typeof value !== 'string' || !value.startsWith('/') || value.length > MAX_ROUTE_LENGTH) return undefined
  if (value.includes('\\') || value.includes('\0') || /%2f|%5c|%2e/i.test(value)) return undefined
  try {
    const url = new URL(value, 'http://plugin-ui.invalid')
    if (url.pathname !== value || value.includes('//') || value.split('/').includes('..')) return undefined
    return value
  } catch {
    return undefined
  }
}

function pluginRoute(route) {
  if (!route || !['exact', 'prefix'].includes(route.kind)) return undefined
  const path = normalizedPath(route.path)
  if (!path || path === '/') return undefined
  if (RESERVED.some(root => path === root || path.startsWith(`${root}/`))) return undefined
  return { kind: route.kind, path }
}

export function allowedPluginUiRequest({ method, path, routes = [], remoteEndpoints = [], pluginName = '', hasGenericApiRoute = false }) {
  const pathname = normalizedPath(path)
  if (!pathname) return false
  const namespace = typeof pluginName === 'string' && /^[A-Za-z0-9@._/-]{1,128}$/.test(pluginName)
    ? pluginName.replace(/^@/, '').replace('/', '-') : ''
  if (namespace && hasGenericApiRoute && pathname.startsWith(`/api/${namespace}/`)) {
    return ['GET', 'HEAD', 'POST', 'PUT', 'PATCH', 'DELETE'].includes(method)
  }
  if (method === 'POST' && pathname.startsWith('/api/')) {
    const endpoint = pathname.slice('/api/'.length)
    if (SESSION_READ_ENDPOINTS.has(endpoint)) return true
    return REMOTE_ENDPOINT.test(endpoint) && remoteEndpoints.includes(endpoint)
  }
  if (method === 'GET' || method === 'HEAD') {
    if (pathname === '/' || STATIC_FILES.has(pathname)) return true
    if (pathname.startsWith('/assets/') || pathname.startsWith('/plugins/')) return true
  }
  return routes.some(candidate => {
    const route = pluginRoute(candidate)
    if (!route) return false
    return pathname === route.path ||
      (route.kind === 'prefix' && pathname.startsWith(`${route.path}/`))
  })
}

export function safePluginRoutes(routes) {
  return Array.isArray(routes) ? routes.map(pluginRoute).filter(Boolean) : []
}
