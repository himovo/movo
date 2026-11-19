import assert from 'node:assert/strict'
import test from 'node:test'

import { DesktopApprovalBroker } from '../src/desktop-approval-broker.mjs'

function harness() {
  const listeners = new Map()
  const registrations = new Map()
  const ctx = { on: (name, callback, options) => {
    listeners.set(name, callback)
    registrations.set(name, options)
    return () => { listeners.delete(name) }
  } }
  const events = [{
    type: 'approval/asked',
    data: { id: 'approval-a', toolName: 'bash', callId: 'call-a' },
  }]
  return {
    ctx, events, registrations,
    emit: (event) => listeners.get('session/event')({ id: 'session-a' }, event),
    request: (reason = 'needs wider access') => {
      const event = events.at(-1)
      listeners.get('session/event')({ id: 'session-a' }, event)
      return listeners.get('approval/request')({
      agent: { id: 'session-a' },
      toolName: events.at(-1).data.toolName, callId: events.at(-1).data.callId, reason,
      }, () => Promise.resolve('delegated'))
    },
  }
}

test('desktop approval broker exposes and resolves the exact native DSH wait', async () => {
  const fixture = harness()
  const broker = new DesktopApprovalBroker(fixture.ctx)
  assert.equal(fixture.registrations.get('approval/request')?.global, true)
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
  fixture.emit({ type: 'tool/call', data: { callId: 'call-a', arguments: '{"command":"echo hello"}' } })
  const first = fixture.request()
  await Promise.resolve()
  broker.decide('session-a', 'approval-a', 'allowed-once', 'session')
  assert.equal(await first, 'allowed-once')
  fixture.events.push({ type: 'approval/asked', data: { id: 'approval-b', toolName: 'bash', callId: 'call-b' } })
  fixture.emit({ type: 'tool/call', data: { callId: 'call-b', arguments: '{"command":"echo hello"}' } })
  assert.equal(await fixture.request(), 'allowed-once')
  assert.deepEqual(broker.list('session-a'), [])
  broker.dispose()
})

test('session grant does not approve a different command using the same tool', async () => {
  const fixture = harness()
  const broker = new DesktopApprovalBroker(fixture.ctx)
  fixture.emit({ type: 'tool/call', data: { callId: 'call-a', arguments: '{"command":"echo first"}' } })
  const first = fixture.request()
  await Promise.resolve()
  broker.decide('session-a', 'approval-a', 'allowed-once', 'session')
  assert.equal(await first, 'allowed-once')
  fixture.emit({ type: 'tool/call', data: { callId: 'call-b', arguments: '{"command":"echo second"}' } })
  fixture.events.push({ type: 'approval/asked', data: { id: 'approval-b', toolName: 'bash', callId: 'call-b' } })
  const second = fixture.request()
  await Promise.resolve()
  assert.equal(broker.list('session-a').length, 1)
  broker.decide('session-a', 'approval-b', 'rejected')
  assert.equal(await second, 'rejected')
  broker.dispose()
})

test('automatic reviewer makes an independent one-shot decision', async () => {
  const fixture = harness()
  const reviewed = []
  const broker = new DesktopApprovalBroker(fixture.ctx, {
    automaticReviewer: { review: async request => { reviewed.push(request); return { allowed: true, reason: 'bounded' } } },
  })
  broker.setReviewer('session-a', 'auto_review')
  fixture.emit({ type: 'tool/call', data: { callId: 'call-a', arguments: '{"command":"echo hello"}' } })
  assert.equal(await fixture.request(), 'allowed-once')
  assert.equal(reviewed[0].argumentsJson, '{"command":"echo hello"}')
  assert.deepEqual(broker.list('session-a'), [])
  broker.dispose()
})

test('automatic review falls back to a human after three consecutive denials', async () => {
  const fixture = harness()
  let reviews = 0
  const broker = new DesktopApprovalBroker(fixture.ctx, {
    automaticReviewer: { review: async () => { reviews += 1; return { allowed: false, reason: 'denied' } } },
  })
  broker.setReviewer('session-a', 'auto_review')
  for (let index = 0; index < 3; index += 1) {
    fixture.emit({ type: 'tool/call', data: { callId: 'call-a', arguments: '{"command":"restricted"}' } })
    assert.equal(await fixture.request(), 'rejected')
  }
  fixture.emit({ type: 'tool/call', data: { callId: 'call-a', arguments: '{"command":"restricted"}' } })
  const waiting = fixture.request()
  await Promise.resolve()
  assert.equal(broker.list('session-a').length, 1)
  broker.decide('session-a', 'approval-a', 'rejected')
  assert.equal(await waiting, 'rejected')
  assert.equal(reviews, 3)
  broker.dispose()
})

test('enterprise tools remain owned by the ASKAI enterprise approval bridge', async () => {
  const fixture = harness()
  fixture.events[0].data.toolName = 'crm_write'
  const broker = new DesktopApprovalBroker(fixture.ctx, { excludedTools: ['crm_write'] })
  assert.equal(await fixture.request(), 'delegated')
  broker.dispose()
})
