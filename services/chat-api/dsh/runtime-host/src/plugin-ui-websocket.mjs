import WebSocket, { WebSocketServer } from 'ws'

const MAX_FRAME_BYTES = 8 * 1024 * 1024
const server = new WebSocketServer({ noServer: true, maxPayload: MAX_FRAME_BYTES })
const READ_ONLY_STREAMS = new Set(['$events', 'session/control', 'session/follow', 'workspace/follow'])

export function rejectUpgrade(socket, status = 403) {
  socket.end(`HTTP/1.1 ${status} Forbidden\r\nConnection: close\r\n\r\n`)
}

export function proxyPluginUiSocket(request, socket, head, target, { endpoints } = {}) {
  server.handleUpgrade(request, socket, head, browser => {
    const upstream = new WebSocket(target.url, {
      headers: target.headers,
      maxPayload: MAX_FRAME_BYTES,
    })
    const streams = new Map()
    const allowed = endpoints ? new Set([...READ_ONLY_STREAMS, ...endpoints]) : null
    const pending = []
    let closed = false
    const close = () => {
      if (closed) return
      closed = true
      browser.close()
      upstream.close()
    }
    browser.on('message', (data, binary) => {
      if (allowed) {
        if (binary) { close(); return }
        let frame
        try { frame = JSON.parse(String(data)) } catch { close(); return }
        if (frame?.type === 'open') {
          if (!allowed.has(frame.endpoint) || typeof frame.streamId !== 'string') { close(); return }
          streams.set(frame.streamId, frame.endpoint)
        } else if (frame?.type === 'cancel') {
          if (!streams.has(frame.streamId)) { close(); return }
          streams.delete(frame.streamId)
        } else if (!['item', 'end'].includes(frame?.type) ||
                   !streams.has(frame.streamId) || READ_ONLY_STREAMS.has(streams.get(frame.streamId))) {
          close(); return
        }
      }
      if (upstream.readyState === WebSocket.OPEN) upstream.send(data, { binary })
      else if (upstream.readyState === WebSocket.CONNECTING && pending.length < 32) pending.push([data, binary])
      else close()
    })
    upstream.on('open', () => {
      for (const [data, binary] of pending) upstream.send(data, { binary })
      pending.length = 0
    })
    upstream.on('message', (data, binary) => {
      if (browser.readyState === WebSocket.OPEN) browser.send(data, { binary })
    })
    browser.on('close', close)
    upstream.on('close', close)
    browser.on('error', close)
    upstream.on('error', close)
  })
}
