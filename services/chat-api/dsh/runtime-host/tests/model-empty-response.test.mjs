import assert from 'node:assert/strict'
import { createServer } from 'node:http'
import test from 'node:test'

import { AskaiModelGatewayAdapter } from '../src/askai-model-gateway-plugin.mjs'

test('a successful HTTP response with no model output is an error', async t => {
  const server = createServer((_request, response) => {
    response.writeHead(200, { 'content-type': 'application/x-ndjson' })
    response.end('{"type":"finish","reason":{"kind":"stop"}}\n')
  })
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve))
  t.after(() => new Promise(resolve => server.close(resolve)))
  const gatewayUrl = `http://127.0.0.1:${server.address().port}/generate`
  const adapter = new AskaiModelGatewayAdapter({
    profileVersion: 'profile-a', modelInstanceId: 'model-a', modelName: 'test-model',
    gatewayUrl, accessToken: 'test-token',
  })
  await assert.rejects(async () => {
    for await (const _event of adapter.stream({
      provider: 'askai-model-gateway', model: 'test-model',
      sessionId: 'session-a', messages: [{ role: 'user', content: [{ type: 'text', text: 'test' }] }],
    })) {}
  }, /no text or tool calls/)
})
