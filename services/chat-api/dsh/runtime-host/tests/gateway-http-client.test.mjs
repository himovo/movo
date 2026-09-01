import assert from 'node:assert/strict'
import { createServer } from 'node:http'
import test from 'node:test'

import { postGatewayJson } from '../src/gateway-http-client.mjs'

test('gateway transport waits for delayed response headers without a transport deadline', async t => {
  const server = createServer((request, response) => {
    const chunks = []
    request.on('data', chunk => chunks.push(chunk))
    request.on('end', () => {
      setTimeout(() => {
        response.writeHead(200, { 'content-type': 'application/json' })
        response.end(JSON.stringify({ result: JSON.parse(Buffer.concat(chunks).toString('utf8')) }))
      }, 80)
    })
  })
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve))
  t.after(() => new Promise(resolve => server.close(resolve)))
  const { port } = server.address()

  const response = await postGatewayJson(`http://127.0.0.1:${port}/execute`, { value: 42 })

  assert.equal(response.ok, true)
  assert.deepEqual(response.payload, { result: { value: 42 } })
})

test('gateway transport follows the DSH cancellation signal', async t => {
  const server = createServer((_request, _response) => {})
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve))
  t.after(() => new Promise(resolve => server.close(resolve)))
  const { port } = server.address()
  const controller = new AbortController()
  const pending = postGatewayJson(`http://127.0.0.1:${port}/execute`, {}, { signal: controller.signal })
  controller.abort(new Error('cancelled by DSH'))

  await assert.rejects(pending, /cancelled by DSH/)
})
