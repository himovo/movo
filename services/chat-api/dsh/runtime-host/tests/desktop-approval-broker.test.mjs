import assert from 'node:assert/strict'
import test from 'node:test'

import { DesktopApprovalBroker } from '../src/desktop-approval-broker.mjs'

function harness() {
  let listener
  const ctx = { on: (name, callback) => {
    assert.equal(name, 'approval/request')
    listener = callback
    return () => { listener = undefined }
  } }
  const events = [{
    type: 'approval/asked',
    data: { id: 'approval-a', toolName: 'bash', callId: 'call-a' },
  }]
  return {
    ctx, events,
    request: () => listener({
      agent: { id: 'session-a', session: { events } },
      toolName: events.at(-1).data.toolName, callId: events.at(-1).data.callId, reason: 'needs wider access',
    }, () => Promise.resolve('delegated')),
  }
}

test('desktop approval broker exposes and resolves the exact native DSH wait', async () => {
  const fixture = harness()
  const broker = new DesktopApprovalBroker(fixture.ctx)
  const waiting = fixture.request()
  await Promise.resolve()
  assert.deepEqual(broker.list('session-a').map(item => ({
    approvalId: item.approvalId, toolName: item.toolName, callId: item.callId,
  })), [{ approvalId: 'approval-a', toolName: 'bash', callId: 'call-a' }])
  assert.equal(broker.decide('session-a', 'approval-a', 'allowed-once').decided, true)
  assert.equal(await waiting, 'allowed-once')
  assert.deepEqual(broker.list('session-a'), [])
  broker.dispose()
})

test('session approval grant answers later matching DSH asks without another UI wait', async () => {
  const fixture = harness()
  const broker = new DesktopApprovalBroker(fixture.ctx)
  const first = fixture.request()
  await Promise.resolve()
  broker.decide('session-a', 'approval-a', 'allowed-once', 'session')
  assert.equal(await first, 'allowed-once')
  fixture.events.push({ type: 'approval/asked', data: { id: 'approval-b', toolName: 'bash', callId: 'call-b' } })
  assert.equal(await fixture.request(), 'allowed-once')
  assert.deepEqual(broker.list('session-a'), [])
  broker.dispose()
})

test('enterprise tools remain owned by the ASKAI enterprise approval bridge', async () => {
  const fixture = harness()
  fixture.events[0].data.toolName = 'crm_write'
  const broker = new DesktopApprovalBroker(fixture.ctx, { excludedTools: ['crm_write'] })
  assert.equal(await fixture.request(), 'delegated')
  broker.dispose()
})
