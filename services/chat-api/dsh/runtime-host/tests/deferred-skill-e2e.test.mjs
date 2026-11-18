import assert from 'node:assert/strict'
import { mkdtemp, rm } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import test from 'node:test'
import { KernelRuntime } from '../src/kernel-runtime.mjs'
import { modelProfile, ndjson, sendText, waitFor, withModelServer } from './support/runtime-admission.mjs'

test('native DSH skill tool loads a mixed plugin only on invocation with conversation history', async () => {
  const root = await mkdtemp(join(tmpdir(), 'movo-deferred-skill-'))
  let calls = 0
  let modelCalls = 0
  try {
    await withModelServer((request, response) => {
      request.resume()
      ndjson(response, modelCalls++ === 0 ? [
        { type: 'tool-call', id: 'skill-call', name: 'skill', arguments: '{"name":"fixture-review"}' },
        { type: 'finish', reason: { kind: 'tool-calls' } },
      ] : [{ type: 'text-delta', text: 'DONE' }, { type: 'finish', reason: { kind: 'stop' } }])
    }, async url => {
      const runtime = new KernelRuntime({
        runtimeId: 'deferred-skill', isolationKey: 'deferred-skill',
        profileVersion: 'runtime-admission-v1', storageRoot: root,
        modelProfile: modelProfile(url, {
          runtimePlacement: 'enterprise-host', subjectUserId: 'user', deferredPlugins: [{
            installation_id: 'fixture', name: 'mixed', commands: [{ name: 'inspect' }],
            skills: [{ name: 'fixture-review', description: 'Review', userInvocable: true, modelInvocable: true }],
          }],
        }),
        invokeDeferredTool: async (plugin, name, args, execution) => {
          calls++
          assert.equal(plugin.name, 'mixed')
          assert.equal(name, 'fixture-review')
          assert.equal(execution.operation, 'skill')
          assert.ok(execution.context.seed.some(event => event.type === 'user/message'))
          return { name, description: 'Review', content: 'DEFERRED_SKILL_BODY', provider: 'fixture',
            source: 'fixture', invocation: { userInvocable: true, modelInvocable: true } }
        },
      })
      try {
        await runtime.start()
        await runtime.createSession({ sessionId: 'skill-session' })
        assert.equal(calls, 0)
        await sendText(runtime, 'skill-session', 'Review this')
        await waitFor(() => runtime.events('skill-session', -1).some(event => event.nativeType === 'turn/end'), 'Skill did not finish')
        assert.equal(calls, 1)
        assert.ok(JSON.stringify(runtime.events('skill-session', -1)).includes('DEFERRED_SKILL_BODY'))
      } finally { await runtime.dispose() }
    })
  } finally { await rm(root, { recursive: true, force: true }) }
})
