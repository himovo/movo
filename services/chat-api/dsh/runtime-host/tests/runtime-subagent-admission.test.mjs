import assert from 'node:assert/strict'
import { mkdtemp, rm } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import test from 'node:test'

import { KernelRuntime } from '../src/kernel-runtime.mjs'
import {
  modelProfile,
  ndjson,
  requestBody,
  sendText,
  waitFor,
  withModelServer,
} from './support/runtime-admission.mjs'

test('runtime delegates to a DSH subagent and returns the child result to MOVO', async () => {
  const root = await mkdtemp(join(tmpdir(), 'askai-runtime-subagent-admission-'))
  const calls = []
  try {
    await withModelServer(async (request, response) => {
      const body = await requestBody(request)
      calls.push(body)
      const transcript = JSON.stringify(body.messages)
      if (transcript.includes('CHILD_TASK_MARKER') && !transcript.includes('CHILD_RESULT_MARKER')) {
        return ndjson(response, [
          { type: 'text-delta', text: 'CHILD_RESULT_MARKER' },
          { type: 'finish', reason: { kind: 'stop' } },
        ])
      }
      if (transcript.includes('CHILD_RESULT_MARKER')) {
        return ndjson(response, [
          { type: 'text-delta', text: 'PARENT_RECEIVED_CHILD_RESULT' },
          { type: 'finish', reason: { kind: 'stop' } },
        ])
      }
      return ndjson(response, [
        {
          type: 'tool-call', id: 'delegate-child', name: 'subagent',
          arguments: JSON.stringify({
            description: 'Verify child execution',
            prompt: 'CHILD_TASK_MARKER: reply with CHILD_RESULT_MARKER.',
            run_in_background: false,
          }),
        },
        { type: 'finish', reason: { kind: 'tool-calls' } },
      ])
    }, async baseUrl => {
      const profile = modelProfile(`${baseUrl}/model`)
      const runtime = new KernelRuntime({
        runtimeId: 'runtime-subagent-admission', isolationKey: 'tenant:runtime-subagent-admission',
        profileVersion: profile.profileVersion, storageRoot: root, modelProfile: profile,
      })
      try {
        await runtime.start()
        const session = await runtime.createSession({ sessionId: 'parent', presetId: 'code', cwd: root })
        assert.ok(session.modelTools.includes('subagent'))
        sendText(runtime, 'parent', 'Delegate this verification.')
        await waitFor(
          () => runtime.events('parent', -1).some(event => event.nativeType === 'turn/end'),
          'parent did not finish after subagent execution',
          15_000,
        )
        await waitFor(() => calls.length >= 3, 'subagent result did not resume the parent', 15_000)
        assert.ok(calls.some(call => JSON.stringify(call.messages).includes('CHILD_TASK_MARKER')))
        assert.ok(calls.some(call => JSON.stringify(call.messages).includes('CHILD_RESULT_MARKER')))
        assert.ok(runtime.events('parent', -1).some(event => (
          event.nativeType === 'assistant/message'
          && JSON.stringify(event.data).includes('PARENT_RECEIVED_CHILD_RESULT')
        )))
      } finally {
        await runtime.dispose()
      }
    })
  } finally {
    await rm(root, { recursive: true, force: true })
  }
})
