import assert from 'node:assert/strict'
import test from 'node:test'

import { resolveSessionSeed } from '../src/session-seed.mjs'

test('ordinary Session creation remains unchanged', async () => {
  const manager = { exportCompletedSeed: async () => assert.fail('must not export a seed') }
  assert.deepEqual(
    await resolveSessionSeed(manager, { sessionId: 'next', presetId: 'askai-enterprise' }),
    { sessionId: 'next', presetId: 'askai-enterprise' },
  )
})

test('predecessor identity becomes a native DSH seed without exposing raw events', async () => {
  const calls = []
  const events = [{ type: 'message', data: { role: 'user', content: 'prior context' } }]
  const manager = {
    exportCompletedSeed: async (runtimeId, sessionId) => {
      calls.push([runtimeId, sessionId])
      return events
    },
  }
  const resolved = await resolveSessionSeed(manager, {
    sessionId: 'next',
    seedRuntimeId: 'runtime-old',
    seedSessionId: 'session-old',
  })
  assert.deepEqual(calls, [['runtime-old', 'session-old']])
  assert.deepEqual(resolved, {
    sessionId: 'next',
    seed: events,
    parentSessionId: 'session-old',
  })
})

test('raw or incomplete seed requests are rejected', async () => {
  const manager = { exportCompletedSeed: async () => [] }
  await assert.rejects(() => resolveSessionSeed(manager, { seed: [] }), /raw Session seed is forbidden/)
  await assert.rejects(() => resolveSessionSeed(manager, { seedRuntimeId: 'runtime-old' }), /supplied together/)
  await assert.rejects(() => resolveSessionSeed(manager, { seedSessionId: 'session-old' }), /supplied together/)
})
