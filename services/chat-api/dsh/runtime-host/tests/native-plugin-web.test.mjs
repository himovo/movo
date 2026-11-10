import assert from 'node:assert/strict'
import { createServer } from 'node:http'
import test from 'node:test'
import WebSocket, { WebSocketServer } from 'ws'

import { NativePluginWeb } from '../src/native-plugin-web.mjs'
import { injectPluginClientShell } from '../src/plugin-client-boot.mjs'

test('main plugin shell keeps native workspace and conversation providers', () => {
  const names = [
    '@deepseek-ai/dsh-api-workspace-controller',
    '@deepseek-ai/dsh-client-ui-conversation',
    'plugin-view',
  ]
  const html = `<script>globalThis["__DSH_BOOT__"] = ${JSON.stringify({
    entries: names.map(id => ({ id, url: `/${id}.js`, inject: [] })), batches: [],
  })}</script>`
  const output = injectPluginClientShell(html, { client_modules: [{ id: 'plugin-view' }] })
  const boot = JSON.parse(output.match(/globalThis\["__DSH_BOOT__"\] = (.*?)<\/script>/s)[1])
  assert.deepEqual(boot.entries.filter(entry => names.includes(entry.id)).map(entry => entry.id), names)
})

test('conversation shell keeps DSH conversation root out of the dedicated view', () => {
  const html = '<script>globalThis["__DSH_BOOT__"] = {"entries":[{"id":"@deepseek-ai/dsh-client-ui-conversation","url":"/conversation.js","inject":[]},{"id":"plugin-view","url":"/plugin.js","inject":[]}],"batches":[]}</script>'
  const output = injectPluginClientShell(html, { client_modules: [{ id: 'plugin-view' }] }, { conversation: true })
  const boot = JSON.parse(output.match(/globalThis\["__DSH_BOOT__"\] = (.*?)<\/script>/s)[1])
  assert.ok(boot.entries.some(entry => entry.id === 'plugin-view'))
  assert.ok(boot.entries.some(entry => entry.id === 'movo-plugin-client-shell'))
  assert.ok(!boot.entries.some(entry => entry.id === 'movo-plugin-conversation-shell'))
  assert.ok(!boot.entries.some(entry => entry.id === 'movo-plugin-conversation-locales'))
  assert.ok(!boot.entries.some(entry => entry.id === '@deepseek-ai/dsh-client-ui-conversation'))
})

test('native plugin web relay keeps the DSH operator cookie internal and rejects other routes', async () => {
  const native = createServer((request, response) => {
    if (request.url === '/?token=internal') {
      response.writeHead(303, { location: './', 'set-cookie': 'dsh_auth=secret; HttpOnly' })
      response.end()
      return
    }
    if (request.headers.cookie !== 'dsh_auth=secret') {
      response.writeHead(401)
      response.end()
      return
    }
    response.writeHead(200, { 'content-type': 'application/json', 'set-cookie': 'leak=forbidden' })
    response.end(JSON.stringify({ path: request.url }))
  })
  await new Promise(resolve => native.listen(0, '127.0.0.1', resolve))
  const ctx = { get: name => ({
    webServer: { port: native.address().port },
    connection: { authenticatedUrl: url => `${url}?token=internal` },
  })[name] }
  const bridge = new NativePluginWeb(ctx, [{
    installation_id: 'owned', client_modules: [{ id: 'media-desk' }],
    web_routes: [{ kind: 'prefix', path: '/media-desk' }],
  }])
  const outer = createServer((request, response) => {
    bridge.proxy('owned', request.url, request, response).catch(error => {
      response.writeHead(500)
      response.end(String(error))
    })
  })
  await new Promise(resolve => outer.listen(0, '127.0.0.1', resolve))
  try {
    const base = `http://127.0.0.1:${outer.address().port}`
    const allowed = await fetch(`${base}/media-desk/settings`)
    assert.equal(allowed.status, 200)
    assert.deepEqual(await allowed.json(), { path: '/media-desk/settings' })
    assert.equal(allowed.headers.get('set-cookie'), null)
    assert.equal((await fetch(`${base}/api/session.create`)).status, 403)
    assert.equal((await fetch(`${base}/other-plugin/data`)).status, 403)
  } finally {
    await new Promise(resolve => outer.close(resolve))
    await new Promise(resolve => native.close(resolve))
  }
})

test('client module with only generic DSH routes can load its shell', async () => {
  const native = createServer((request, response) => {
    if (request.url === '/?token=internal') {
      response.writeHead(303, { 'set-cookie': 'dsh_auth=secret; HttpOnly' })
      response.end()
      return
    }
    response.writeHead(200, { 'content-type': 'text/html' })
    response.end('<script>globalThis["__DSH_BOOT__"] = {"entries":[],"batches":[]}</script>')
  })
  await new Promise(resolve => native.listen(0, '127.0.0.1', resolve))
  const ctx = { get: name => ({
    webServer: { port: native.address().port },
    connection: { authenticatedUrl: url => `${url}?token=internal` },
  })[name] }
  const bridge = new NativePluginWeb(ctx, [{
    installation_id: 'owned', client_modules: [{ id: 'context' }],
    web_routes: [{ kind: 'prefix', path: '/api' }],
  }])
  const outer = createServer((request, response) => {
    bridge.proxy('owned', request.url, request, response).catch(error => {
      response.writeHead(500)
      response.end(String(error))
    })
  })
  await new Promise(resolve => outer.listen(0, '127.0.0.1', resolve))
  try {
    assert.equal((await fetch(`http://127.0.0.1:${outer.address().port}/`)).status, 200)
    assert.equal((await fetch(`http://127.0.0.1:${outer.address().port}/api/session.create`, { method: 'POST' })).status, 403)
  } finally {
    await new Promise(resolve => outer.close(resolve))
    await new Promise(resolve => native.close(resolve))
  }
})

test('plugin client shell preserves the route and cookie boundary', async () => {
  const original = '<script>globalThis["__DSH_BOOT__"] = {"entries":[],"batches":[]}</script>'
  const native = createServer((request, response) => {
    if (request.url === '/?token=internal') {
      response.writeHead(303, { 'set-cookie': 'dsh_auth=secret; HttpOnly' })
      response.end()
      return
    }
    response.writeHead(200, { 'content-type': 'text/html', 'set-cookie': 'leak=forbidden' })
    response.end(original)
  })
  await new Promise(resolve => native.listen(0, '127.0.0.1', resolve))
  const ctx = { get: name => ({
    webServer: { port: native.address().port },
    connection: { authenticatedUrl: url => `${url}?token=internal` },
  })[name] }
  const bridge = new NativePluginWeb(ctx, [{
    installation_id: 'owned', client_modules: [{ id: 'plugin' }],
  }])
  const outer = createServer((request, response) => {
    bridge.proxy('owned', request.url, request, response).catch(error => {
      response.writeHead(500)
      response.end(String(error))
    })
  })
  await new Promise(resolve => outer.listen(0, '127.0.0.1', resolve))
  try {
    const base = `http://127.0.0.1:${outer.address().port}`
    const page = await fetch(`${base}/`)
    assert.equal(page.status, 200)
    const html = await page.text()
    assert.match(html, /movo-plugin-client-shell/)
    const shell = await fetch(`${base}/movo-client-shell.js`)
    assert.equal(shell.status, 200)
    const source = await shell.text()
    assert.match(source, /id: 'movo-plugin-conversation-locales'/)
    assert.match(source, /id: 'movo-plugin-conversation-shell'/)
    assert.match(source, /id: 'movo-plugin-client-shell'/)
    assert.equal(page.headers.get('set-cookie'), null)
    const admin = await fetch(`${base}/api/pluginManager/installBundle`, {
      method: 'POST',
    })
    assert.equal(admin.status, 403)
  } finally {
    await new Promise(resolve => outer.close(resolve))
    await new Promise(resolve => native.close(resolve))
  }
})

test('native plugin stream uses its private DSH cookie and rejects unrelated streams', async () => {
  const native = createServer((request, response) => {
    response.writeHead(303, { 'set-cookie': 'dsh_auth=secret; HttpOnly' })
    response.end()
  })
  const nativeSockets = new WebSocketServer({ noServer: true })
  native.on('upgrade', (request, socket, head) => {
    if (request.headers.cookie !== 'dsh_auth=secret') { socket.destroy(); return }
    nativeSockets.handleUpgrade(request, socket, head, peer => {
      peer.on('message', data => peer.send(data))
    })
  })
  await new Promise(resolve => native.listen(0, '127.0.0.1', resolve))
  const ctx = { get: name => ({
    webServer: { port: native.address().port },
    connection: { authenticatedUrl: url => `${url}?token=internal` },
  })[name] }
  const bridge = new NativePluginWeb(ctx, [{
    installation_id: 'owned', client_modules: [{ id: 'plugin' }], remote_endpoints: ['plugin/read'],
  }])
  const outer = createServer()
  outer.on('upgrade', (request, socket, head) => {
    bridge.proxyUpgrade('owned', request, socket, head).catch(() => socket.destroy())
  })
  await new Promise(resolve => outer.listen(0, '127.0.0.1', resolve))
  try {
    const client = new WebSocket(`ws://127.0.0.1:${outer.address().port}/api/remote.mux`)
    await new Promise(resolve => client.once('open', resolve))
    const received = new Promise(resolve => client.once('message', data => resolve(JSON.parse(String(data)))))
    client.send(JSON.stringify({ type: 'open', streamId: '1', endpoint: 'plugin/read', payload: {} }))
    assert.equal((await received).endpoint, 'plugin/read')
    const closed = new Promise(resolve => client.once('close', resolve))
    client.send(JSON.stringify({ type: 'open', streamId: '2', endpoint: 'session/create', payload: {} }))
    await closed
  } finally {
    for (const peer of nativeSockets.clients) peer.terminate()
    await new Promise(resolve => outer.close(resolve))
    await new Promise(resolve => nativeSockets.close(resolve))
    await new Promise(resolve => native.close(resolve))
  }
})
