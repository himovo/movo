import assert from 'node:assert/strict'
import test from 'node:test'

import { AskaiModelGatewayAdapter } from '../src/askai-model-gateway-plugin.mjs'
import { normalizeTurnContext, renderTurnContext } from '../src/runtime-turn-context.mjs'
import { materializeModelImages } from '../src/official-host/model-image-compat.mjs'

test('vision profile materializes durable images for the authenticated model gateway', async () => {
  const originalFetch = globalThis.fetch
  const requests = []
  globalThis.fetch = async (_url, options) => {
    requests.push(JSON.parse(options.body))
    return new Response('{"type":"finish","reason":{"kind":"stop"}}\n', { status: 200 })
  }
  try {
    const adapter = new AskaiModelGatewayAdapter({
      profileVersion: 'profile-a', modelInstanceId: 'model-a', modelName: 'vision-model',
      gatewayUrl: 'https://gateway.example.test/generate', accessToken: 'short-lived', visionEnabled: true,
    }, { readImage: async () => ({ ref: { mediaType: 'image/png' }, data: Uint8Array.from([1, 2, 3]) }) })
    const models = await adapter.listModels('askai-model-gateway')
    assert.deepEqual(models[0].inputModalities, ['text', 'image'])
    const textOnly = new AskaiModelGatewayAdapter({ ...adapter.config, visionEnabled: false })
    assert.deepEqual((await textOnly.listModels('askai-model-gateway'))[0].inputModalities, ['text'])
    for await (const _event of adapter.stream({ provider: 'askai-model-gateway', model: 'vision-model', sessionId: 'session-a', messages: [
      { role: 'user', content: [{ type: 'text', text: 'Look at this' }, { type: 'image', attachment: { attachmentId: 'sha256:test', mediaType: 'image/png' } }] },
    ] })) {}
    assert.equal(requests[0].messages[0].content[1].image_url.url, 'data:image/png;base64,AQID')
  } finally {
    globalThis.fetch = originalFetch
  }
})

test('vision model receives image context without a redundant extraction instruction', () => {
  const context = normalizeTurnContext({ images: [{ object_path: 'user-a/image.png', content_type: 'image/png' }] })
  assert.match(renderTurnContext(context, true), /supplied this turn's images directly/)
  assert.doesNotMatch(renderTurnContext(context, true), /Use image_extract_facts/)
  assert.match(renderTurnContext(context, false), /Use image_extract_facts/)
})

test('text-only model cannot dispatch an image even if projection is bypassed', async () => {
  await assert.rejects(
    materializeModelImages([{ role: 'user', content: [{ type: 'image', attachment: {} }] }], null, false),
    /not configured for visual input/,
  )
})
