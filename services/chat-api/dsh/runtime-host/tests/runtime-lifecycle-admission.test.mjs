import assert from 'node:assert/strict'
import { mkdtemp, rm } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import test from 'node:test'

import { KernelRuntime } from '../src/kernel-runtime.mjs'
import { sendText, waitFor } from './support/runtime-admission.mjs'

function runtime(root) {
  return new KernelRuntime({
    runtimeId: 'runtime-lifecycle-admission',
    isolationKey: 'tenant:runtime-lifecycle-admission',
    profileVersion: 'runtime-admission-v1',
    storageRoot: root,
  })
}

function turnEnds(runtime, sessionId) {
  return runtime.events(sessionId, -1).filter(event => event.nativeType === 'turn/end').length
}

test('runtime creates, stops, resumes execution, and survives a Host-level reopen', async () => {
  const root = await mkdtemp(join(tmpdir(), 'askai-runtime-lifecycle-admission-'))
  const first = runtime(root)
  try {
    await first.start()
    const created = await first.createSession({ sessionId: 'lifecycle' })
    assert.equal(created.status, 'idle')

    sendText(first, 'lifecycle', '[slow] cancel this turn')
    await waitFor(
      () => first.events('lifecycle', -1).some(event => (
        event.nativeType === 'agent/status' && event.data.status === 'running'
      )),
      'Session never entered a working state',
    )
    const cancelled = await first.cancel('lifecycle', 'user_cancelled')
    assert.equal(cancelled.turnPending, false)
    assert.equal(cancelled.jobsPending, false)

    sendText(first, 'lifecycle', 'run after stop')
    await waitFor(() => turnEnds(first, 'lifecycle') >= 2, 'Session did not accept a turn after stop')
    assert.ok(first.events('lifecycle', -1).some(event => (
      event.nativeType === 'assistant/message'
      && JSON.stringify(event.data).includes('run after stop')
    )))

    await first.disposeSession('lifecycle')
    const resumed = await first.resumeSession('lifecycle', 5000)
    assert.equal(resumed.status, 'idle')
    assert.ok(first.events('lifecycle', 5000).length > 0)
    assert.ok(first.events('lifecycle', 5000).every(event => event.cursor > 5000))
    sendText(first, 'lifecycle', 'run after reopen')
    await waitFor(() => turnEnds(first, 'lifecycle') >= 3, 'reopened Session did not execute')
  } finally {
    await first.dispose()
    await rm(root, { recursive: true, force: true })
  }
})
