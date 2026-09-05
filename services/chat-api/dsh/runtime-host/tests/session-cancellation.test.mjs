import assert from 'node:assert/strict'
import test from 'node:test'

import { cancelSessionWork } from '../src/session-cancellation.mjs'

test('Session cancellation stops every owned DSH background job before returning', async () => {
  const calls = []
  const agent = {
    cancel: cause => calls.push(['agent.cancel', cause]),
    whenIdle: async () => calls.push(['agent.idle']),
  }
  const ctx = { jobs: {
    list: owner => {
      assert.equal(owner, agent)
      return [{ id: 'bash-1', status: 'running' }, { id: 'bash-2', status: 'completed' }]
    },
    kill: (id, owner, cause) => { calls.push(['jobs.kill', id, owner, cause]); return 'requested' },
    wait: async id => ({ id, status: 'killed', detail: 'SIGTERM' }),
  } }
  const result = await cancelSessionWork(ctx, agent, 'user_cancelled')
  assert.equal(result.jobsPending, false)
  assert.equal(result.turnPending, false)
  assert.deepEqual(result.jobs, [{ id: 'bash-1', status: 'killed', detail: 'SIGTERM' }])
  assert.equal(calls[0][0], 'jobs.kill')
  assert.equal(calls[1][0], 'agent.cancel')
  assert.equal(calls[2][0], 'agent.idle')
})

test('Session cancellation reports a turn that did not settle before the deadline', async () => {
  const agent = {
    cancel: () => undefined,
    whenIdle: () => new Promise(() => undefined),
  }
  const ctx = { jobs: {
    list: () => [],
    kill: () => undefined,
    wait: async () => undefined,
  } }
  const result = await cancelSessionWork(ctx, agent, 'user_cancelled', 5)
  assert.equal(result.turnPending, true)
})
