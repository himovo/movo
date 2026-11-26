import assert from 'node:assert/strict'
import test from 'node:test'
import { SharedOperation } from '../src/shared-operation.mjs'
import { IsolatedPluginRuntimePool } from '../src/isolated-plugin-runtime.mjs'
import { mkdtemp, rm } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'

test('concurrent initialization shares one result and failures allow a fresh retry', async () => {
  const operations = new SharedOperation()
  let calls = 0
  const results = await Promise.all(Array.from({ length: 8 }, () =>
    operations.run('runtime', async () => { calls++; return { id: 'one' } })))
  assert.equal(calls, 1)
  assert.ok(results.every(result => result === results[0]))
  await assert.rejects(operations.run('failed', async () => { throw new Error('startup failed') }))
  assert.equal(await operations.run('failed', async () => 'retried'), 'retried')
})

test('simultaneous isolated runtime creation starts one child for the profile', async () => {
  const root = await mkdtemp(join(tmpdir(), 'movo-concurrent-runtime-'))
  const pool = new IsolatedPluginRuntimePool(root)
  try {
    const body = { isolationKey: 'tenant:concurrent', profileVersion: 'concurrent', tenantId: 'tenant' }
    const results = await Promise.all(Array.from({ length: 8 }, () => pool.create(body)))
    assert.equal(new Set(results.map(result => result.runtimeId)).size, 1)
    assert.equal(pool.inventory().length, 1)
  } finally {
    await pool.disposeAll()
    await rm(root, { recursive: true, force: true })
  }
})
