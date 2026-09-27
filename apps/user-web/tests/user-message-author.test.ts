import assert from 'node:assert/strict'
import test from 'node:test'
import { resolveAuthorPresentation } from '../src/components/chat/userMessageAuthor'

// T9 contract suite: asserts ONLY the pure helper's return values. Rendered
// alt/aria wording and <img> absence are proven by T12's Playwright capture;
// `npm run typecheck` proves UserMessageAuthor.vue's thin delegation to this helper.

const AVATAR = 'https://cdn.example.com/avatars/u1.png'

test('valid avatar url returns an image presentation with the display name as alt', () => {
  assert.deepEqual(
    resolveAuthorPresentation({ display_name: 'Alice Wang', avatar_url: AVATAR }),
    { kind: 'image', src: AVATAR, alt: 'Alice Wang' },
  )
})

test('valid avatar url without a display name still returns an image presentation', () => {
  assert.deepEqual(
    resolveAuthorPresentation({ display_name: null, avatar_url: AVATAR }),
    { kind: 'image', src: AVATAR, alt: 'User avatar' },
  )
})

test('null avatar url returns deterministic initials plus the display name as aria label', () => {
  assert.deepEqual(
    resolveAuthorPresentation({ display_name: 'Alice Wang', avatar_url: null }),
    { kind: 'initials', text: 'AW', ariaLabel: 'Alice Wang' },
  )
})

test('initials are deterministic across calls and survive extra whitespace', () => {
  const input = { display_name: '  alice   wang  ', avatar_url: null }
  const first = resolveAuthorPresentation(input)
  const second = resolveAuthorPresentation(input)
  assert.deepEqual(first, second)
  assert.deepEqual(first, { kind: 'initials', text: 'AW', ariaLabel: 'alice wang' })
})

test('single-word names return exactly one initial', () => {
  assert.deepEqual(
    resolveAuthorPresentation({ display_name: 'Alice', avatar_url: null }),
    { kind: 'initials', text: 'A', ariaLabel: 'Alice' },
  )
})

test('cjk names return the first character as the initial', () => {
  assert.deepEqual(
    resolveAuthorPresentation({ display_name: '张三', avatar_url: null }),
    { kind: 'initials', text: '张', ariaLabel: '张三' },
  )
})

test('over-long display names are capped at two initials and keep the full aria label', () => {
  const name = 'A Very Long Display Name That Should Never Overflow A Message Row'
  assert.deepEqual(
    resolveAuthorPresentation({ display_name: name, avatar_url: null }),
    { kind: 'initials', text: 'AV', ariaLabel: name },
  )
})

test('null display name returns a question-mark initial and a neutral aria label', () => {
  assert.deepEqual(
    resolveAuthorPresentation({ display_name: null, avatar_url: null }),
    { kind: 'initials', text: '?', ariaLabel: 'User' },
  )
})

test('unsafe avatar urls return initials and never echo the raw value', () => {
  const unsafe = [
    'javascript:alert(1)',
    'data:image/png;base64,AAAA',
    'objects/users/u1/avatar.png',
    '/files/avatar.png',
    'ftp://cdn.example.com/u1.png',
    'https://cdn.example.com/a b.png',
  ]
  for (const avatar_url of unsafe) {
    assert.deepEqual(
      resolveAuthorPresentation({ display_name: 'Alice', avatar_url }),
      { kind: 'initials', text: 'A', ariaLabel: 'Alice' },
    )
  }
})

test('http avatar urls stay valid for local deployments', () => {
  const local = 'http://localhost:8000/avatars/u1.png'
  assert.deepEqual(
    resolveAuthorPresentation({ display_name: 'Alice', avatar_url: local }),
    { kind: 'image', src: local, alt: 'Alice' },
  )
})
