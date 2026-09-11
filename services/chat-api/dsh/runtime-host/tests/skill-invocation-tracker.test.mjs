import assert from 'node:assert/strict'
import test from 'node:test'

import { SkillInvocationTracker } from '../src/skill-invocation-tracker.mjs'

const profile = { skills: [{
  name: 'generic-capability-a1', source_id: 'skill-7', display_name: 'Generic capability',
  source_scope: 'personal',
}] }
const invocation = {
  type: 'user/message',
  data: { source: { kind: 'skill-invocation', name: 'generic-capability-a1' } },
}

test('classifies a confirmed DSH invocation as automatic by default', () => {
  const tracker = new SkillInvocationTracker(profile)
  assert.deepEqual(tracker.observe('session-a', invocation), {
    sourceId: 'skill-7', displayName: 'Generic capability', sourceScope: 'personal',
    selectionMode: 'automatic',
  })
})

test('classifies the DSH skill tool call as an automatic invocation', () => {
  const tracker = new SkillInvocationTracker(profile)
  assert.deepEqual(tracker.observe('session-a', {
    type: 'tool/call',
    data: { name: 'skill', arguments: '{"name":"generic-capability-a1"}' },
  }), {
    sourceId: 'skill-7', displayName: 'Generic capability', sourceScope: 'personal',
    selectionMode: 'automatic',
  })
  assert.equal(tracker.current('session-a'), 'generic-capability-a1')
})

test('emits a Skill only once when DSH exposes multiple invocation events in one turn', () => {
  const tracker = new SkillInvocationTracker(profile)
  tracker.observe('session-a', {
    type: 'tool/call', data: { name: 'skill', arguments: { name: 'generic-capability-a1' } },
  })
  assert.equal(tracker.observe('session-a', invocation), undefined)
  tracker.observe('session-a', { type: 'turn/end', data: {} })
  assert.equal(tracker.current('session-a'), undefined)
  assert.equal(tracker.observe('session-a', invocation)?.selectionMode, 'automatic')
})

test('classifies only the expected confirmed invocation as manual', () => {
  const tracker = new SkillInvocationTracker(profile)
  tracker.expectManual('session-a', 'generic-capability-a1')
  assert.equal(tracker.observe('session-a', { type: 'step/start', data: {} }), undefined)
  assert.equal(tracker.observe('session-b', invocation)?.selectionMode, 'automatic')
  assert.equal(tracker.observe('session-a', invocation)?.selectionMode, 'manual')
  assert.equal(tracker.observe('session-a', invocation), undefined)
})

test('does not expose invocations outside the immutable Runtime Profile', () => {
  const tracker = new SkillInvocationTracker(profile)
  assert.equal(tracker.observe('session-a', {
    type: 'user/message', data: { source: { kind: 'skill-invocation', name: 'unknown-skill' } },
  }), undefined)
})
