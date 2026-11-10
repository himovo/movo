import assert from 'node:assert/strict'
import { createServer } from 'node:http'
import test from 'node:test'
import WebSocket, { WebSocketServer } from 'ws'

import { proxyPluginUiSocket } from '../src/plugin-ui-websocket.mjs'

async function listen(server) {
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve))
  return server.address().port
}

test('plugin UI socket forwards only declared and read-only streams', async () => {
  const nativeServer = createServer()
  const nativeSockets = new WebSocketServer({ server: nativeServer })
  nativeSockets.on('connection', socket => socket.on('message', data => socket.send(data)))
  const nativePort = await listen(nativeServer)
  const proxyServer = createServer()
  proxyServer.on('upgrade', (request, socket, head) => proxyPluginUiSocket(
    request, socket, head, { url: `ws://127.0.0.1:${nativePort}` },
    { endpoints: ['plugin/read'] },
  ))
  const proxyPort = await listen(proxyServer)
  try {
    const client = new WebSocket(`ws://127.0.0.1:${proxyPort}`)
    await new Promise(resolve => client.once('open', resolve))
    const received = new Promise(resolve => client.once('message', data => resolve(JSON.parse(String(data)))))
    client.send(JSON.stringify({ type: 'open', streamId: 'one', endpoint: 'session/follow', payload: {} }))
    assert.equal((await received).endpoint, 'session/follow')
    const workspace = new Promise(resolve => client.once('message', data => resolve(JSON.parse(String(data)))))
    client.send(JSON.stringify({ type: 'open', streamId: 'workspace', endpoint: 'workspace/follow', payload: {} }))
    assert.equal((await workspace).endpoint, 'workspace/follow')
    const closed = new Promise(resolve => client.once('close', resolve))
    client.send(JSON.stringify({ type: 'open', streamId: 'two', endpoint: 'session/create', payload: {} }))
    await closed
  } finally {
    for (const socket of nativeSockets.clients) socket.terminate()
    await new Promise(resolve => proxyServer.close(resolve))
    await new Promise(resolve => nativeSockets.close(resolve))
    await new Promise(resolve => nativeServer.close(resolve))
  }
})
