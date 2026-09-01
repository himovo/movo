import assert from 'node:assert/strict'
import test from 'node:test'

import { normalizeTemporalContext, renderTemporalContext } from '../src/runtime-temporal-context.mjs'

test('trusted temporal context preserves UTC, local time, and IANA timezone', () => {
  const context = normalizeTemporalContext({
    captured_at_utc: '2026-08-15T10:00:00Z',
    user_local_time: '2026-08-15T18:00:00+08:00',
    user_timezone: 'Asia/Shanghai',
  })
  const rendered = renderTemporalContext(context)
  assert.match(rendered, /2026-08-15T10:00:00Z/)
  assert.match(rendered, /2026-08-15T18:00:00\+08:00/)
  assert.match(rendered, /Asia\/Shanghai/)
  assert.match(rendered, /Never invent a calendar date/)
})

test('trusted temporal context rejects invalid timezone and timestamp', () => {
  assert.throws(() => normalizeTemporalContext({
    captured_at_utc: 'not-a-date',
    user_local_time: '2026-08-15T18:00:00+08:00',
    user_timezone: 'Asia/Shanghai',
  }), /ISO 8601/)
  assert.throws(() => normalizeTemporalContext({
    captured_at_utc: '2026-08-15T10:00:00Z',
    user_local_time: '2026-08-15T18:00:00+08:00',
    user_timezone: 'Mars\/Olympus',
  }), /IANA timezone/)
})
