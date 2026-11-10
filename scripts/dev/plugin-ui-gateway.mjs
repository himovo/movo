import http from 'node:http'

const port = Number(process.env.MOVO_PLUGIN_UI_PORT || 3200)
const backend = new URL(process.env.MOVO_PLUGIN_UI_BACKEND || 'http://127.0.0.1:8000')
if (!Number.isInteger(port) || port < 1 || port > 65535) throw new Error('Invalid plugin UI port')

const csp = "default-src 'self' blob: data:; script-src 'self' 'unsafe-inline' 'unsafe-eval' blob:; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob: https: http:; connect-src 'self'; form-action 'self'; base-uri 'self'; object-src 'none'"

const server = http.createServer((request, response) => {
  const upstream = http.request(new URL(`/plugin-ui${request.url || '/'}`, backend), {
    method: request.method,
    headers: {
      ...request.headers,
      host: request.headers.host,
      'x-forwarded-host': request.headers.host,
      'x-forwarded-proto': 'http',
      authorization: '',
    },
  }, upstreamResponse => {
    response.writeHead(upstreamResponse.statusCode || 502, {
      ...upstreamResponse.headers,
      'content-security-policy': csp,
    })
    upstreamResponse.pipe(response)
  })
  upstream.on('error', () => {
    if (!response.headersSent) response.writeHead(502)
    response.end()
  })
  request.pipe(upstream)
})

server.on('upgrade', (request, socket, head) => {
  if (new URL(request.url || '/', 'http://plugin-ui.local').pathname !== '/api/remote.mux') {
    socket.destroy()
    return
  }
  const upstream = http.request(new URL('/plugin-ui/api/remote.mux', backend), {
    headers: {
      ...request.headers,
      host: request.headers.host,
      'x-forwarded-host': request.headers.host,
      'x-forwarded-proto': 'http',
      authorization: '',
    },
  })
  upstream.on('upgrade', (response, tunnel, upstreamHead) => {
    socket.write(`HTTP/1.1 101 Switching Protocols\r\n${Object.entries(response.headers)
      .map(([name, value]) => `${name}: ${value}`).join('\r\n')}\r\n\r\n`)
    if (head.length) tunnel.write(head)
    if (upstreamHead.length) socket.write(upstreamHead)
    socket.pipe(tunnel).pipe(socket)
    socket.on('error', () => tunnel.destroy())
    tunnel.on('error', () => socket.destroy())
  })
  upstream.on('response', response => {
    socket.write(`HTTP/1.1 ${response.statusCode || 502} ${response.statusMessage || 'Rejected'}\r\nConnection: close\r\n\r\n`)
    response.resume()
    response.on('end', () => socket.end())
  })
  upstream.on('error', () => socket.destroy())
  upstream.end()
})

server.listen(port, '127.0.0.1', () => {
  process.stdout.write(`Plugin UI gateway listening on http://127.0.0.1:${port}\n`)
})
