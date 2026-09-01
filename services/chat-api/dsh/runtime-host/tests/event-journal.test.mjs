import assert from 'node:assert/strict'
import test from 'node:test'
import { EventJournal } from '../src/event-journal.mjs'

test('event journal assigns replayable one-based cursors', () => {
  const journal = new EventJournal()
  journal.append('session-a', 'turn/start', { turn: 1 }, 0)
  journal.append('session-a', 'turn/end', { turn: 1 }, 1)

  assert.deepEqual(journal.replay('session-a', 0).map(event => event.cursor), [1, 2])
  assert.deepEqual(journal.replay('session-a', 1).map(event => event.cursor), [2])
  assert.deepEqual(journal.replay('other-session', 0), [])
})

test('reset restores native persisted events without cross-session leakage', () => {
  const journal = new EventJournal()
  journal.append('session-a', 'old', {})
  journal.append('session-b', 'other', {})
  journal.resetFromSession({
    id: 'session-a',
    events: [
      { type: 'user/message', seq: 4, data: { text: 'persisted' } },
      { type: 'assistant/message', seq: 5, data: { text: 'answer' } },
    ],
  })

  assert.deepEqual(journal.replay('session-a', 0).map(event => event.nativeSeq), [4, 5])
  assert.equal(journal.replay('session-b', 0).length, 1)
})

test('subscriber receives replay and future events without polling', () => {
  const journal = new EventJournal()
  journal.append('session-a', 'turn/start', {}, 0)
  const received = []
  const subscription = journal.subscribe('session-a', 0, event => received.push(event))

  assert.deepEqual(subscription.replay.map(event => event.cursor), [1])
  journal.append('session-a', 'assistant/chunk', { text: 'a' }, 1)
  subscription.unsubscribe()
  journal.append('session-a', 'turn/end', {}, 2)

  assert.deepEqual(received.map(event => event.cursor), [2])
})
