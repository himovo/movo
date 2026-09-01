import assert from 'node:assert/strict'
import test from 'node:test'
import {
  sessionActivityTime,
  sortSessionsByRecentActivity,
} from '../src/utils/sessionOrdering'

test('orders conversations by their latest message instead of metadata updates', () => {
  const ordered = sortSessionsByRecentActivity([
    {
      id: 'renamed-recently',
      created_at: '2026-08-20T08:00:00Z',
      updated_at: '2026-08-21T10:00:00Z',
      last_message_at: '2026-08-20T09:00:00Z',
    },
    {
      id: 'latest-message',
      created_at: '2026-08-20T08:00:00Z',
      updated_at: '2026-08-21T09:00:00Z',
      last_message_at: '2026-08-21T09:00:00Z',
    },
  ])

  assert.deepEqual(ordered.map((item) => item.id), ['latest-message', 'renamed-recently'])
})

test('falls back to update and creation timestamps for empty or legacy conversations', () => {
  const empty = { id: 'empty', created_at: '2026-08-21T08:00:00Z', updated_at: '2026-08-21T10:00:00Z' }
  const legacy = { id: 'legacy', created_at: '2026-08-21T09:00:00Z' }

  assert.equal(sessionActivityTime(empty), Date.parse('2026-08-21T10:00:00Z'))
  assert.deepEqual(sortSessionsByRecentActivity([legacy, empty]).map((item) => item.id), ['empty', 'legacy'])
})
