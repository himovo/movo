import assert from 'node:assert/strict'
import { mkdtemp, rm } from 'node:fs/promises'
import { createServer } from 'node:http'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import test from 'node:test'

import { KernelRuntime } from '../src/kernel-runtime.mjs'

const BLUE_PNG = 'iVBORw0KGgoAAAANSUhEUgAAACAAAAAgCAIAAAD8GO2jAAAAKklEQVR4nGMQj7hNU8QwasGoBaMWjFowasGoBaMWjFowasGoBaMWDBULAFDvKEx9Oak2AAAAAElFTkSuQmCC'
const CLOCK = { captured_at_utc: '2026-10-25T00:00:00Z', user_local_time: '2026-10-25T08:00:00+08:00', user_timezone: 'Asia/Shanghai' }

async function waitFor(predicate) {
  const start = Date.now()
  while (!predicate()) {
    if (Date.now() - start > 8000) throw new Error('timed out waiting for the image model request')
    await new Promise(resolve => setTimeout(resolve, 25))
  }
}

test('official DSH admits a user image and keeps it available for a follow-up', async () => {
  const root = await mkdtemp(join(tmpdir(), 'movo-vision-e2e-'))
  const calls = []
  const server = createServer(async (request, response) => {
    const chunks = []
    for await (const chunk of request) chunks.push(chunk)
    calls.push(JSON.parse(Buffer.concat(chunks).toString('utf8')))
    response.writeHead(200, { 'content-type': 'application/x-ndjson' })
    response.end('{"type":"text-delta","text":"Blue."}\n{"type":"finish","reason":{"kind":"stop"}}\n')
  })
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve))
  const runtime = new KernelRuntime({
    runtimeId: 'vision-e2e', isolationKey: 'tenant:user:vision-e2e', profileVersion: 'vision-profile', storageRoot: root,
    modelProfile: {
      profileVersion: 'vision-profile', modelInstanceId: 'model-a', modelName: 'vision-model',
      gatewayUrl: `http://127.0.0.1:${server.address().port}/model`, accessToken: 'ephemeral', visionEnabled: true,
    },
  })
  try {
    await runtime.start()
    await runtime.createSession({ sessionId: 'vision-session' })
    await runtime.send({ sessionId: 'vision-session', mode: 'prompt', temporalContext: CLOCK, content: [
      { type: 'text', data: { text: 'What color is this square?' } },
      { type: 'image', data: { mediaType: 'image/png', data: BLUE_PNG, name: 'square.png' } },
    ] })
    await waitFor(() => calls.length >= 1)
    assert.match(calls[0].messages.find(item => item.role === 'user').content.find(item => item.type === 'image_url').image_url.url, /^data:image\/png;base64,/)
    await waitFor(() => runtime.events('vision-session', -1).some(event => event.nativeType === 'turn/end'))
    await runtime.send({ sessionId: 'vision-session', mode: 'followup', temporalContext: CLOCK, content: [
      { type: 'text', data: { text: 'Recall the picture.' } },
    ] })
    await waitFor(() => calls.length >= 2)
    assert.ok(calls[1].messages.some(item => item.role === 'user' && item.content.some?.(part => part.type === 'image_url')))
  } finally {
    await runtime.dispose()
    await new Promise(resolve => server.close(resolve))
    await rm(root, { recursive: true, force: true })
  }
})
