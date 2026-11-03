import assert from 'node:assert/strict'
import test from 'node:test'
import { appendUrlQueryParameter } from './urlQuery.ts'

test('appends an encoded query parameter', () => {
  assert.equal(
    appendUrlQueryParameter('/admin-api/avatar.png', 'v', '2026-11-03 12:00'),
    '/admin-api/avatar.png?v=2026-11-03%2012%3A00',
  )
})

test('preserves existing query parameters', () => {
  assert.equal(
    appendUrlQueryParameter('https://cdn.example/avatar.png?size=small', 'v', '2'),
    'https://cdn.example/avatar.png?size=small&v=2',
  )
})

test('inserts the query parameter before the URL fragment', () => {
  assert.equal(
    appendUrlQueryParameter('/admin-api/avatar.svg#profile', 'v', '2'),
    '/admin-api/avatar.svg?v=2#profile',
  )
})

test('does not add a redundant separator after an empty query', () => {
  assert.equal(
    appendUrlQueryParameter('/admin-api/avatar.png?', 'v', '2'),
    '/admin-api/avatar.png?v=2',
  )
})
