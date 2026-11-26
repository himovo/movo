import assert from 'node:assert/strict'
import test from 'node:test'
import { readContextUsage } from '../src/official-host/context-usage.mjs'

test('usage capacity comes from the measured session model metadata', async () => {
  const ctx = {
    get: () => ({ measure: () => ({ totalTokens: 25000, baseline: { kind: 'usage' }, logRevision: 4, surfaceDeltaTokens: 0 }) }),
    llm: { resolveModelInfo: async (provider, model) => {
      assert.equal(provider, 'managed')
      assert.equal(model, 'session-model')
      return { context: { contextWindow: 100000 } }
    } },
  }
  const agent = {
    options: { provider: 'other', model: 'other-model' },
    session: { requestHeader: () => ({ config: { provider: 'managed', model: 'session-model' } }), snapshotEvents: () => [] },
  }
  const result = await readContextUsage(ctx, agent)
  assert.equal(result.usedTokens / result.capacityTokens, 0.25)
  assert.equal(result.estimated, false)
})

test('persisted native usage remains readable when model capacity is unavailable', async () => {
  const ctx = {
    get: () => ({
      measure: () => ({ totalTokens: 53706, baseline: { kind: 'estimated' }, logRevision: 91, surfaceDeltaTokens: 0 }),
    }),
    llm: { resolveModelInfo: async () => { throw new Error('model metadata unavailable') } },
  }
  const agent = {
    options: { provider: 'managed', model: 'historical-model' },
    session: { requestHeader: () => undefined, snapshotEvents: () => [] },
  }
  const result = await readContextUsage(ctx, agent)
  assert.equal(result.available, true)
  assert.equal(result.usedTokens, 53706)
  assert.equal(result.capacityTokens, null)
  assert.equal(result.modelName, 'historical-model')
})
