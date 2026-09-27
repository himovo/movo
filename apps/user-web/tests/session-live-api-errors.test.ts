import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { createRequire } from 'node:module'
import { resolve } from 'node:path'
import test from 'node:test'

import { AUTH_EXPIRED_EVENT } from '../src/api/authExpiry'
import type { ChatMessage } from '../src/api/sessions'
import { resolveAuthorPresentation } from '../src/components/chat/userMessageAuthor'
import {
  mergeAuthoritativeMessages,
  type ProjectionMessage,
} from '../src/composables/sessionLiveProjection'
import { ChatStreamHttpError, startChatStream } from '../src/composables/useChatStream'
import { SessionLiveHttpError, startSessionLiveStream } from '../src/composables/useSessionLiveStream'
import type { RuntimeMessage } from '../src/composables/useChatRuntimeStore'

// ── T11 contract suite — the THIRD owned suite (plan L170-L175) ────────────
// Scope is EXACTLY the row's three areas:
//   1. exhaustive API error-code handling (ChatStreamHttpError + SessionLiveHttpError)
//   2. avatar URL fallback at the API/projection boundary
//   3. transport-to-notice mapping
// T6's SSE framing matrix and T8's merge/pre-header/manual-only-409 ownership
// are deliberately NOT re-tested here.
//
// RED-FIRST: `T11_STALE=1` runs the STALE-FIXTURE cases at the bottom (skipped
// by default). They apply the same assertion predicates to pre-extension
// fixtures and MUST fail; that failure transcript is the T11 failure evidence,
// while the default run is the green half.

// The store harness needs a require shim before its axios CJS chain loads.
;(globalThis as { require?: unknown }).require = createRequire(import.meta.url)

const STALE = process.env.T11_STALE === '1'
const staleTest = STALE ? test : test.skip
const encoder = new TextEncoder()

function encode(text: string): Uint8Array {
  return encoder.encode(text)
}

type FetchStep = Response | Error | (() => Response | Promise<Response>)

interface FetchCall {
  url: string
  headers: Record<string, string>
  signal: AbortSignal | null
}

function scriptedFetch(steps: FetchStep[]) {
  const calls: FetchCall[] = []
  const impl = (async (input: any, init?: RequestInit) => {
    const headers: Record<string, string> = {}
    const raw = init?.headers as Record<string, string> | undefined
    if (raw) for (const [key, value] of Object.entries(raw)) headers[key] = String(value)
    calls.push({ url: String(input), headers, signal: (init?.signal as AbortSignal) || null })
    const step = steps.shift()
    if (step instanceof Error) throw step
    if (step === undefined) return new Promise<Response>(() => undefined)
    return typeof step === 'function' ? await step() : step
  }) as typeof fetch
  return { impl, calls }
}

function jsonResponse(status: number, payload: unknown): Response {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

function openSseResponse(initial: string): Response {
  return new Response(
    new ReadableStream<Uint8Array>({
      start(controller) {
        controller.enqueue(encode(initial))
      },
    }),
    { status: 200, headers: { 'Content-Type': 'text/event-stream' } },
  )
}

async function withFetch<T>(impl: typeof fetch, run: () => Promise<T>): Promise<T> {
  const previous = globalThis.fetch
  ;(globalThis as { fetch?: typeof fetch }).fetch = impl
  try {
    return await run()
  } finally {
    ;(globalThis as { fetch?: typeof fetch }).fetch = previous
  }
}

async function until(predicate: () => boolean, label: string, tries = 400): Promise<void> {
  for (let attempt = 0; attempt < tries; attempt += 1) {
    if (predicate()) return
    await new Promise<void>((settle) => setTimeout(settle, 1))
  }
  assert.fail(`timed out waiting for ${label}`)
}

async function settleTicks(count = 4): Promise<void> {
  for (let tick = 0; tick < count; tick += 1) await new Promise<void>((settle) => setTimeout(settle, 0))
}

// ---------------------------------------------------------------------------
// 1) API error-code handling — POST /chat/completions catalog
// ---------------------------------------------------------------------------

interface ChatErrorShape {
  label: string
  status: number
  contentType: string
  body: string
  message: string
  code: string | null
}

const CHAT_ERROR_SHAPES: ChatErrorShape[] = [
  {
    label: 'FastAPI dict detail {message, code}',
    status: 404,
    contentType: 'application/json',
    body: JSON.stringify({ detail: { message: 'session gone', code: 'session_not_found' } }),
    message: 'session gone',
    code: 'session_not_found',
  },
  {
    label: 'legacy plain-string detail',
    status: 403,
    contentType: 'application/json',
    body: JSON.stringify({ detail: 'forbidden' }),
    message: 'forbidden',
    code: null,
  },
  {
    label: 'top-level {message, code} without detail',
    status: 422,
    contentType: 'application/json',
    body: JSON.stringify({ message: 'bad body', code: 'validation_error' }),
    message: 'bad body',
    code: 'validation_error',
  },
  {
    label: 'dict detail without a code',
    status: 500,
    contentType: 'application/json',
    body: JSON.stringify({ detail: { message: 'boom' } }),
    message: 'boom',
    code: null,
  },
  {
    label: 'dict detail with a whitespace-only code',
    status: 500,
    contentType: 'application/json',
    body: JSON.stringify({ detail: { message: 'boom', code: '   ' } }),
    message: 'boom',
    code: null,
  },
  {
    label: 'non-JSON text body',
    status: 502,
    contentType: 'text/plain',
    body: 'gateway down',
    message: 'gateway down',
    code: null,
  },
  {
    label: 'malformed JSON',
    status: 500,
    contentType: 'application/json',
    body: '{not json',
    message: 'Request failed: 500',
    code: null,
  },
  {
    label: 'empty JSON object',
    status: 503,
    contentType: 'application/json',
    body: '{}',
    message: 'Request failed: 503',
    code: null,
  },
]

for (const shape of CHAT_ERROR_SHAPES) {
  test(`chat-completions error shape "${shape.label}" yields one typed error with the catalog code`, async () => {
    const script = scriptedFetch([
      new Response(shape.body, { status: shape.status, headers: { 'Content-Type': shape.contentType } }),
    ])
    await withFetch(script.impl, async () => {
      let delivered = 0
      const handle = startChatStream({ messages: [] }, () => { delivered += 1 }, {})
      const rejection = handle.done.then(() => null, (error: unknown) => error)
      await handle.ready
      const error = await rejection
      assert.ok(error instanceof ChatStreamHttpError, 'a non-OK response rejects with the typed error')
      assert.equal(error.name, 'ChatStreamHttpError')
      assert.equal(error.status, shape.status, 'the HTTP status is preserved verbatim')
      assert.equal(error.code, shape.code, 'the parsed FastAPI code is the only machine-readable contract')
      assert.equal(error.message, shape.message, 'the display message never replaces the code')
      assert.equal(delivered, 0, 'a failed handshake delivers no execution event')
      assert.equal(script.calls.length, 1, 'the POST transport never retries on its own')
    })
  })
}

const CHAT_STATUS_CATALOG = [400, 401, 403, 404, 408, 410, 422, 429, 500, 502, 503]

for (const status of CHAT_STATUS_CATALOG) {
  test(`chat-completions status ${status} is terminal with exactly one attempt`, async () => {
    const script = scriptedFetch([
      jsonResponse(status, { detail: { message: `status ${status}`, code: `code_${status}` } }),
    ])
    await withFetch(script.impl, async () => {
      const handle = startChatStream({ messages: [] }, () => undefined, {})
      const rejection = handle.done.then(() => null, (error: unknown) => error)
      await handle.ready
      const error = await rejection
      assert.ok(error instanceof ChatStreamHttpError)
      assert.equal(error.status, status)
      assert.equal(error.code, `code_${status}`, 'every catalog status surfaces its parsed code')
      assert.equal(script.calls.length, 1, 'no status in the catalog triggers a retry loop')
      assert.equal(handle.sessionId, null)
      assert.equal(handle.messageId, null)
    })
  })
}

test('a 401 POST raises exactly one auth-expired notice; anonymous or non-401 failures raise none', async () => {
  const previousWindow = (globalThis as { window?: unknown }).window
  // Node-native EventTarget stands in for the browser window the notice targets.
  const sink = new EventTarget()
  ;(globalThis as { window?: unknown }).window = sink
  try {
    let expired = 0
    sink.addEventListener(AUTH_EXPIRED_EVENT, () => { expired += 1 })

    const authed = scriptedFetch([jsonResponse(401, { detail: { message: 'expired', code: 'token_expired' } })])
    await withFetch(authed.impl, async () => {
      const handle = startChatStream({ messages: [] }, () => undefined, { authToken: 'token-1' })
      await handle.done.catch(() => undefined)
    })
    assert.equal(expired, 1, 'a 401 on an authenticated POST maps to the auth-expired notice once')

    const anonymous = scriptedFetch([jsonResponse(401, { detail: 'expired' })])
    await withFetch(anonymous.impl, async () => {
      const handle = startChatStream({ messages: [] }, () => undefined, {})
      await handle.done.catch(() => undefined)
    })
    assert.equal(expired, 1, 'an anonymous 401 never dispatches the auth notice')

    const forbidden = scriptedFetch([jsonResponse(403, { detail: 'forbidden' })])
    await withFetch(forbidden.impl, async () => {
      const handle = startChatStream({ messages: [] }, () => undefined, { authToken: 'token-1' })
      await handle.done.catch(() => undefined)
    })
    assert.equal(expired, 1, 'a non-401 failure never dispatches the auth notice')
  } finally {
    if (previousWindow === undefined) delete (globalThis as { window?: unknown }).window
    else (globalThis as { window?: unknown }).window = previousWindow
  }
})

// ---------------------------------------------------------------------------
// 1b) API error-code handling — GET /sessions/{id}/live catalog
// ---------------------------------------------------------------------------

test('SessionLiveHttpError carries its name, status, and deterministic default message', () => {
  const defaulted = new SessionLiveHttpError(429)
  assert.ok(defaulted instanceof Error)
  assert.equal(defaulted.name, 'SessionLiveHttpError')
  assert.equal(defaulted.status, 429)
  assert.equal(defaulted.message, 'Session live request failed with status 429')
  const explicit = new SessionLiveHttpError(500, 'upstream boom')
  assert.equal(explicit.status, 500)
  assert.equal(explicit.message, 'upstream boom')
})

// 401/403/404/410 terminality is T6's; these are the remaining catalog rows.
const TERMINAL_SESSION_LIVE_STATUSES = [400, 408, 422, 429]
const RETRYABLE_SESSION_LIVE_STATUSES = [500, 502, 503, 504]

for (const status of TERMINAL_SESSION_LIVE_STATUSES) {
  test(`session-SSE status ${status} stops once with a typed error and no access-loss notice`, async () => {
    const script = scriptedFetch([new Response('denied', { status })])
    const errors: SessionLiveHttpError[] = []
    const losses: string[] = []
    const sleeps: number[] = []
    const handle = startSessionLiveStream({
      sessionId: 'sess-1',
      paneKey: 'pane-1',
      authToken: 'token-1',
      fetchImpl: script.impl,
      sleep: async (ms) => { sleeps.push(ms) },
      random: () => 0.5,
      onError: (error) => errors.push(error),
      onAccessLost: (_paneKey, reason) => losses.push(reason),
    })
    await handle.done
    assert.equal(script.calls.length, 1, 'a status below the retryable floor never reconnects')
    assert.deepEqual(sleeps, [], 'a terminal status never enters backoff')
    assert.equal(errors.length, 1, 'exactly one typed terminal error')
    assert.ok(errors[0] instanceof SessionLiveHttpError)
    assert.equal(errors[0].status, status)
    assert.deepEqual(losses, [], 'a terminal HTTP error is never mapped to access loss')
    assert.equal(handle.cursor(), null)
  })
}

for (const status of RETRYABLE_SESSION_LIVE_STATUSES) {
  test(`session-SSE status ${status} reconnects with backoff and recovers without an error notice`, async () => {
    const script = scriptedFetch([new Response('upstream', { status }), openSseResponse(': heartbeat\n\n')])
    const errors: SessionLiveHttpError[] = []
    const sleeps: number[] = []
    const handle = startSessionLiveStream({
      sessionId: 'sess-1',
      paneKey: 'pane-1',
      fetchImpl: script.impl,
      sleep: async (ms) => { sleeps.push(ms) },
      random: () => 0.5,
      onError: (error) => errors.push(error),
    })
    await until(() => script.calls.length === 2, `status ${status} reconnect`)
    assert.deepEqual(sleeps, [1000], 'the first reconnect uses the 1s base delay')
    assert.deepEqual(errors, [], 'a retryable status surfaces no error notice')
    assert.equal(handle.cursor(), null, 'a failed handshake advances no cursor')
    handle.stop()
    await handle.done
  })
}

// ---------------------------------------------------------------------------
// 2) Avatar URL fallback at the API/projection boundary
// ---------------------------------------------------------------------------

type ServerRow = ProjectionMessage & RuntimeMessage

// Server-shaped GET /sessions/{id} rows: the T5/T8 author projection is the
// only carrier of avatar identity for shared conversations.
const SERVER_SNAPSHOT: ServerRow[] = [
  {
    role: 'user', content: 'unsafe', message_id: 'm-1', legacy_key: 'message:m-1', seq: 1,
    author: { user_id: 'u-1', display_name: 'Jesse', avatar_url: 'javascript:alert(1)' },
  },
  {
    role: 'user', content: 'relative', message_id: 'm-2', legacy_key: 'message:m-2', seq: 2,
    author: { user_id: 'u-2', display_name: 'Nina', avatar_url: 'objects/users/u2/avatar.png' },
  },
  {
    role: 'user', content: 'null avatar', message_id: 'm-3', legacy_key: 'message:m-3', seq: 3,
    author: { user_id: 'u-3', display_name: 'Ada', avatar_url: null },
  },
  {
    role: 'user', content: 'safe', message_id: 'm-4', legacy_key: 'message:m-4', seq: 4,
    author: { user_id: 'u-4', display_name: 'Sam', avatar_url: 'https://cdn.example.com/sam.png' },
  },
  {
    role: 'user', content: 'legacy row', message_id: 'm-5', legacy_key: 'legacy:user:0', seq: 5,
    author: null,
  },
  {
    role: 'assistant', content: 'reply', message_id: 'm-6', legacy_key: 'message:m-6', seq: 6,
  },
]

test('server-shaped user-message authors project into safe presentations through the API merge', () => {
  const projected = mergeAuthoritativeMessages<ServerRow>([], SERVER_SNAPSHOT).messages
  const byId = (messageId: string): ServerRow => {
    const row = projected.find((message) => message.message_id === messageId)
    assert.ok(row, `projected row ${messageId} is missing`)
    return row
  }

  const unsafe = byId('m-1')
  assert.deepEqual(
    unsafe.author,
    { user_id: 'u-1', display_name: 'Jesse', avatar_url: 'javascript:alert(1)' },
    'the projection carries the server author identity verbatim for the presentation boundary to degrade',
  )
  const unsafePresentation = resolveAuthorPresentation(unsafe.author)
  assert.deepEqual(unsafePresentation, { kind: 'initials', text: 'J', ariaLabel: 'Jesse' })
  assert.ok(!('src' in unsafePresentation), 'an unsafe avatar_url never becomes an image source')

  assert.deepEqual(
    resolveAuthorPresentation(byId('m-2').author),
    { kind: 'initials', text: 'N', ariaLabel: 'Nina' },
    'a relative object path degrades to initials',
  )
  assert.deepEqual(
    resolveAuthorPresentation(byId('m-3').author),
    { kind: 'initials', text: 'A', ariaLabel: 'Ada' },
    'a null avatar_url degrades to initials',
  )
  assert.deepEqual(
    resolveAuthorPresentation(byId('m-4').author),
    { kind: 'image', src: 'https://cdn.example.com/sam.png', alt: 'Sam' },
    'an absolute https avatar_url is the only image kind',
  )

  assert.equal(byId('m-5').author, null, 'a null server author stays null; no identity is fabricated')
  assert.equal(byId('m-6').author, undefined, 'assistant rows never gain an author projection')
})

// ---------------------------------------------------------------------------
// 3) Transport-to-notice mapping
// ---------------------------------------------------------------------------

interface AdapterConfig {
  url?: string
}

async function loadRuntimeWithQuota() {
  const axiosModule = (await import('axios')).default
  ;(axiosModule.defaults as unknown as {
    adapter?: (config: AdapterConfig) => Promise<unknown>
  }).adapter = async (config) => {
    const url = String(config.url || '')
    if (!url.includes('/quota/me')) {
      throw new Error(`unexpected axios call in the T11 store harness: ${url}`)
    }
    return {
      data: { code: 0, data: { remainingPoints: 100, spaceType: 'personal' } },
      status: 200,
      statusText: 'OK',
      headers: {},
      config,
      request: null,
    }
  }
  const { useChatRuntimeStore } = await import('../src/composables/useChatRuntimeStore')
  return useChatRuntimeStore({})
}

test('a non-409 POST failure stops the run with one local failure notice and zero retries', async () => {
  const unhandled: unknown[] = []
  const capture = (reason: unknown) => { unhandled.push(reason) }
  process.on('unhandledRejection', capture)
  const script = scriptedFetch([
    jsonResponse(500, { detail: { message: 'backend exploded', code: 'chat_stream_failed' } }),
  ])
  const runtime = await loadRuntimeWithQuota()
  try {
    await withFetch(script.impl, async () => {
      runtime.reset()
      const pane = runtime.startLocalSession()
      await runtime.sendMessage(pane.key, {
        text: 'hello',
        images: [],
        documents: [],
        knowledgeQaEnabled: false,
        authToken: 'token-1',
        userId: 'user-1',
        mainId: 'main-1',
        viewerAuthor: { user_id: 'user-1', display_name: 'Viewer', avatar_url: null },
        locale: 'en',
        timezone: 'UTC',
      })
      await settleTicks(4)

      assert.equal(script.calls.length, 1, 'exactly one POST attempt: no automatic retry loop')
      assert.equal(pane.running, false, 'the run stops on a non-retryable POST failure')
      const assistant = pane.messages.find((message) => message.role === 'assistant')
      const failures = (assistant?._execV3?.state.rawEvents || []).filter((event) => event.type === 'item.failed')
      assert.equal(failures.length, 1, 'exactly one local failure notice event')
      assert.equal(
        (failures[0] as { payload?: { message?: string } }).payload?.message,
        'backend exploded',
        'the notice carries the transport error message',
      )
      assert.equal(
        pane.messages.filter((message) => message.role === 'user').length,
        1,
        'the generic failure path keeps the bubbles (the manual-only 409 removal is T8-owned)',
      )
      assert.equal(pane.messages.filter((message) => message.role === 'assistant').length, 1)
    })
  } finally {
    runtime.reset()
    process.off('unhandledRejection', capture)
  }
  assert.deepEqual(unhandled, [], 'the failed POST never leaks an unhandled rejection')
})

test('the access-loss notice matrix maps each revoked reason to its intended notice (T10 consumption)', () => {
  // The headless harness has no .vue loader, so App.vue's notice switch is
  // pinned by its source-level contract — the same pattern T6's threading test
  // uses. Rendered wording remains T12's browser proof.
  const app = readFileSync(resolve(process.cwd(), 'src/App.vue'), 'utf8')
  assert.match(app, /case 'participant_left':\s*\n\s*return t\('session\.share\.left'\)/,
    'participant_left reuses the existing share-left notice')
  assert.match(app, /case 'participant_removed':\s*\n\s*case null:\s*\n\s*return generic/,
    'a removal or an untyped latch gets the generic access-lost notice')
  assert.match(app, /const _exhaustive: never = reason/,
    'the reason matrix is exhaustive; a future reason fails typecheck')
  assert.match(app, /filter\(\(pane\) => pane\.accessLost\)\.map\(\(pane\) => pane\.key\)/,
    'the notice is driven only by the settled access-loss latch')
  assert.match(app, /if \(accessLostHandledPanes\.has\(paneKey\)\) continue/,
    'each pane key is handled at most once (no notice loop)')
  assert.match(app, /shareToast\.warning\(accessLostNoticeMessage\(accessLostReason\)\)/,
    'the latch reason is the only input to the notice mapping')
})

// ---------------------------------------------------------------------------
// RED-FIRST stale fixtures (T11_STALE=1). Skipped by default; each case applies
// the suite's own assertion predicate to a pre-extension fixture and MUST fail.
// ---------------------------------------------------------------------------

staleTest('STALE error mapping: a legacy plain-detail payload must still carry the catalog code', async () => {
  const script = scriptedFetch([
    jsonResponse(409, { detail: 'session already running' }),
  ])
  await withFetch(script.impl, async () => {
    const handle = startChatStream({ messages: [] }, () => undefined, {})
    const error = await handle.done.then(() => null, (reason: unknown) => reason)
    assert.ok(error instanceof ChatStreamHttpError)
    assert.equal(error.code, 'session_already_running')
  })
})

staleTest('STALE avatar projection: a pre-T8 payload without author breaks the identity contract', () => {
  const staleRow: ServerRow = {
    role: 'user', content: 'hello', message_id: 'm-stale', legacy_key: 'message:m-stale', seq: 1,
  }
  const projected = mergeAuthoritativeMessages<ServerRow>([], [staleRow]).messages
  assert.deepEqual(projected[0].author, {
    user_id: 'u-1', display_name: 'Jesse', avatar_url: 'javascript:alert(1)',
  })
})

staleTest('STALE unsafe fallback: an image presentation that keeps an unsafe src must be rejected', () => {
  const stalePresentation = { kind: 'image' as const, src: 'javascript:alert(1)', alt: 'Jesse' }
  assert.ok(
    !('src' in stalePresentation) || !stalePresentation.src.toLowerCase().startsWith('javascript:'),
    'an unsafe avatar_url never becomes an image source',
  )
})
