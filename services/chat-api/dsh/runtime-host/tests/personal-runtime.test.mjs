import assert from 'node:assert/strict'
import { mkdtemp, stat, rm } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import test from 'node:test'

import { KernelRuntime } from '../src/kernel-runtime.mjs'

test('server conversation gets a durable cwd that survives runtime restart', async () => {
  const root = await mkdtemp(join(tmpdir(), 'movo-personal-runtime-'))
  const previous = process.env.MOVO_PERSONAL_SPACE_ROOT
  process.env.MOVO_PERSONAL_SPACE_ROOT = join(root, 'personal')
  const key = 'a'.repeat(64)
  const createRuntime = () => new KernelRuntime({
    runtimeId: 'personal-test', isolationKey: 'personal-test',
    profileVersion: 'profile-test', storageRoot: join(root, 'runtime'),
  })
  let runtime = createRuntime()
  try {
    await runtime.start()
    const session = await runtime.createSession({ sessionId: 'conversation', personalConversationKey: key })
    assert.ok(session.capabilityTools.includes('present'))
    assert.ok(session.modelTools.includes('present'))
    assert.equal((await stat(join(root, 'personal', 'conversations', key))).isDirectory(), true)
    await runtime.dispose()
    runtime = createRuntime()
    await runtime.start()
    assert.equal((await runtime.resumeSession('conversation')).sessionId, 'conversation')
  } finally {
    await runtime.dispose().catch(() => {})
    if (previous === undefined) delete process.env.MOVO_PERSONAL_SPACE_ROOT
    else process.env.MOVO_PERSONAL_SPACE_ROOT = previous
    await rm(root, { recursive: true, force: true })
  }
})
