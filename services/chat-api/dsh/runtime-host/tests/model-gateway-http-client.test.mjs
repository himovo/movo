import assert from 'node:assert/strict'
import { createServer } from 'node:http'
import test from 'node:test'

import { postGatewayNdjson } from '../src/model-gateway-http-client.mjs'

async function withServer(handler, run) {
  const server = createServer(handler)
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve))
  try {
    await run(`http://127.0.0.1:${server.address().port}/generate`)
  } finally {
    server.closeAllConnections()
    await new Promise(resolve => server.close(resolve))
  }
}

test('model transport waits for delayed headers and streams before response completion', async () => {
  let finishResponse
  const finish = new Promise(resolve => { finishResponse = resolve })
  await withServer((_request, response) => {
    setTimeout(() => {
      response.writeHead(200, { 'content-type': 'application/x-ndjson' })
      response.write('{"type":"text-delta","text":"first"}\n')
      finish.then(() => response.end('{"type":"finish"}\n'))
    }, 80)
  }, async url => {
    const response = await postGatewayNdjson(url, { model: 'test' })
    assert.equal(response.ok, true)
    const iterator = response.body[Symbol.asyncIterator]()
    assert.match(String((await iterator.next()).value), /first/)
    finishResponse()
    assert.match(String((await iterator.next()).value), /finish/)
  })
})

test('model transport preserves error response bodies', async () => {
  await withServer((_request, response) => {
    response.writeHead(502, { 'content-type': 'application/json' })
    response.end(JSON.stringify({ error: { code: 'model_timeout' } }))
  }, async url => {
    const response = await postGatewayNdjson(url, {})
    assert.equal(response.ok, false)
    assert.equal(response.status, 502)
    assert.deepEqual(await response.json(), { error: { code: 'model_timeout' } })
  })
})

test('model transport follows cancellation before response headers', async () => {
  await withServer((_request, _response) => {}, async url => {
    const controller = new AbortController()
    const pending = postGatewayNdjson(url, {}, { signal: controller.signal })
    controller.abort(new Error('cancelled by DSH'))
    await assert.rejects(pending, /cancelled by DSH/)
  })
})

test('model transport stops an active response on cancellation', async () => {
  await withServer((_request, response) => {
    response.writeHead(200, { 'content-type': 'application/x-ndjson' })
    response.write('{"type":"text-delta","text":"first"}\n')
  }, async url => {
    const controller = new AbortController()
    const response = await postGatewayNdjson(url, {}, { signal: controller.signal })
    const iterator = response.body[Symbol.asyncIterator]()
    assert.match(String((await iterator.next()).value), /first/)
    controller.abort(new Error('cancelled by DSH'))
    await assert.rejects(iterator.next(), /cancelled by DSH/)
  })
})
