// Fetch-based SSE client for GET /askai-api/api/sessions/{id}/live.
//
// Protocol rules implemented here (fixed by the session-sharing plan Scope):
// - bearer token only in the Authorization header, never in the URL
// - LF-only frames; `:` comments are heartbeats; multiline `data:` joined with \n
// - same-stream resume via Last-Event-ID; fresh stream after an authoritative
//   reload via ?after=<live_cursor>, and never both
// - control frames (thread.changed / members.changed) end the current response:
//   the client reports them and parks until the caller reopens fresh
// - session.access.revoked is terminal: the cursor is cleared and the client
//   never reconnects on its own
// - transient failures retry with capped exponential backoff; 401/403/404/410
//   and revocation never retry
// T6 deliberately performs no teardown and does not touch the runtime store;
// the single access-loss latch is owned by T7's markAccessLost store action.
//
// allow: SIZE_OK — T6's file set permits exactly one source file; it carries the
// six-event wire contract, the LF-only SSE parser, the reconnect policy and the
// access-loss handoff, which the plan's Scope fixes as one focused composable.

import type { ExecutionEventV3 } from '../features/execution-v3/domain/protocol'
import { isExecutionEventV3 } from '../features/execution-v3/domain/protocol'
import { notifyAuthExpiredFromResponse } from '../api/authExpiry'

export type SessionLiveAccessRevokedReason = 'participant_removed' | 'participant_left'
export type SessionLiveThreadChangedReason = 'cursor_gap' | 'replay_overflow' | 'cursor_invalid'

export interface SessionLiveThreadChangedEvent {
  session_id: string
  revision: string
  last_message_seq: number
  reason?: SessionLiveThreadChangedReason
}

export interface SessionLiveTurnStartedEvent {
  session_id: string
  revision: string
  run_id: string
  message_id: string
  initiator_user_id: string
  status: string
}

export interface SessionLiveExecutionEvent {
  session_id: string
  message_id: string
  event_id: string
  stream_seq: number
  event: ExecutionEventV3
}

export interface SessionLiveTurnCompletedEvent {
  session_id: string
  message_id: string
  run_id: string
  status: string
  revision: string
}

export interface SessionLiveMembersChangedEvent {
  session_id: string
  revision: string
}

export interface SessionLiveAccessRevokedEvent {
  session_id: string
  reason: SessionLiveAccessRevokedReason
}

export interface SessionLiveStreamOptions {
  sessionId: string
  paneKey: string
  authToken?: string | null
  /** Same-stream resume position; sent as Last-Event-ID. Wins over afterCursor. */
  lastEventId?: string | null
  /** Fresh-stream position minted by GET /api/sessions/{id}; sent as ?after=. */
  afterCursor?: string | null
  onThreadChanged?: (event: SessionLiveThreadChangedEvent) => void
  onTurnStarted?: (event: SessionLiveTurnStartedEvent) => void
  onExecution?: (event: SessionLiveExecutionEvent) => void
  onTurnCompleted?: (event: SessionLiveTurnCompletedEvent) => void
  onMembersChanged?: (paneKey: string) => void
  onAccessLost?: (paneKey: string, reason: SessionLiveAccessRevokedReason) => void
  onMalformedFrame?: (rawFrame: string) => void
  onError?: (error: SessionLiveHttpError) => void
  fetchImpl?: typeof fetch
  sleep?: (ms: number) => Promise<void>
  random?: () => number
}

export interface SessionLiveStreamHandle {
  readonly paneKey: string
  /** Cursor of the last ID-carrying frame; null after terminal revocation. */
  cursor(): string | null
  /** Resolves when the stream stop()s, is revoked, or hits a non-retryable error. */
  done: Promise<void>
  /** Abort the in-flight request and release the reader. Idempotent. */
  stop(): void
  /** Drop the stale Last-Event-ID and reopen from an authoritative live_cursor. */
  openFreshStream(afterCursor: string): void
}

/** Capped exponential reconnect schedule: 1s, 2s, 4s, 8s, then 15s. */
export const SESSION_LIVE_RECONNECT_SCHEDULE_MS = [1000, 2000, 4000, 8000, 15_000] as const
/** Control-frame responses a pane may reopen past immediately. */
export const SESSION_LIVE_CONTROL_FRAME_CAP = 3
const RECONNECT_JITTER_RATIO = 0.2
const LIVE_PATH = '/askai-api/api/sessions'
const RETRYABLE_STATUS_FLOOR = 500
const THREAD_CHANGED_REASONS: readonly SessionLiveThreadChangedReason[] = [
  'cursor_gap',
  'replay_overflow',
  'cursor_invalid',
]

/** Delay before the next reconnect attempt; base schedule plus bounded jitter. */
export function sessionLiveReconnectDelayMs(attempt: number, random: () => number = Math.random): number {
  const index = Math.min(Math.max(Math.trunc(attempt) || 0, 0), SESSION_LIVE_RECONNECT_SCHEDULE_MS.length - 1)
  const jitter = (random() * 2 - 1) * RECONNECT_JITTER_RATIO
  return Math.round(SESSION_LIVE_RECONNECT_SCHEDULE_MS[index] * (1 + jitter))
}

const controlFrameStreaks = new Map<string, number>()

/**
 * T6-owned consecutive-control-frame counter. T7's control-frame handler is
 * the sole caller; the stream client itself never calls it. Returns the delay
 * in ms that must elapse before the next reopen, 0 meaning immediate.
 */
export function noteSessionLiveControlFrame(paneKey: string, random: () => number = Math.random): number {
  const streak = (controlFrameStreaks.get(paneKey) || 0) + 1
  controlFrameStreaks.set(paneKey, streak)
  if (streak <= SESSION_LIVE_CONTROL_FRAME_CAP) return 0
  return sessionLiveReconnectDelayMs(streak - SESSION_LIVE_CONTROL_FRAME_CAP - 1, random)
}

/** Reset a pane's control-frame streak after forward progress or teardown. */
export function noteSessionLiveData(paneKey: string): void {
  controlFrameStreaks.delete(paneKey)
}

export class SessionLiveHttpError extends Error {
  status: number
  constructor(status: number, message?: string) {
    super(message || `Session live request failed with status ${status}`)
    this.name = 'SessionLiveHttpError'
    this.status = status
  }
}

const asText = (value: string | null | undefined): string | null => {
  const trimmed = typeof value === 'string' ? value.trim() : ''
  return trimmed ? trimmed : null
}

const pickStrings = <K extends string>(source: Record<string, any>, keys: readonly K[]): Record<K, string> | null => {
  const picked = {} as Record<K, string>
  for (const key of keys) {
    const value = source[key]
    if (typeof value !== 'string' || value.length === 0) return null
    picked[key] = value
  }
  return picked
}

export function startSessionLiveStream(options: SessionLiveStreamOptions): SessionLiveStreamHandle {
  const fetchImpl: typeof fetch = options.fetchImpl || ((input: any, init?: any) => fetch(input, init))
  const sleep = options.sleep || ((ms: number) => new Promise<void>((resolve) => setTimeout(resolve, ms)))
  const random = options.random || Math.random
  const paneKey = options.paneKey

  let stopped = false
  let revoked = false
  let loopActive = false
  let reopenRequested = false
  let reader: ReadableStreamDefaultReader<Uint8Array> | null = null
  let controller: AbortController | null = null
  let lastEventId = asText(options.lastEventId)
  // Last-Event-ID always wins when both positions are supplied.
  let afterCursor = lastEventId === null ? asText(options.afterCursor) : null
  let failureStreak = 0
  let sawProgress = false

  let settleDone: () => void = () => undefined
  const done = new Promise<void>((resolve) => { settleDone = resolve })
  let releaseStopped: () => void = () => undefined
  const stoppedSignal = new Promise<void>((resolve) => { releaseStopped = resolve })

  const releaseReader = () => {
    const active = reader
    reader = null
    if (active) void active.cancel().catch(() => undefined)
  }

  const stop = () => {
    if (stopped) return
    stopped = true
    controller?.abort()
    releaseReader()
    releaseStopped()
    settleDone()
  }

  const waitBeforeRetry = async () => {
    const delay = sessionLiveReconnectDelayMs(failureStreak, random)
    failureStreak += 1
    await Promise.race([sleep(delay), stoppedSignal])
  }

  const buildUrl = () => {
    const base = `${LIVE_PATH}/${encodeURIComponent(options.sessionId)}/live`
    return afterCursor === null ? base : `${base}?after=${encodeURIComponent(afterCursor)}`
  }

  const buildHeaders = (): Record<string, string> => {
    const headers: Record<string, string> = { Accept: 'text/event-stream' }
    if (options.authToken) headers.Authorization = `Bearer ${options.authToken}`
    if (afterCursor === null && lastEventId !== null) headers['Last-Event-ID'] = lastEventId
    return headers
  }

  const readFrames = async (body: ReadableStream<Uint8Array>): Promise<'eof' | 'control' | 'revoked'> => {
    const activeReader = body.getReader()
    reader = activeReader
    const decoder = new TextDecoder()
    let buffer = ''
    let eventName: string | null = null
    let frameId: string | null = null
    let dataLines: string[] = []
    let rawLines: string[] = []
    let outcome: 'eof' | 'control' | 'revoked' = 'eof'

    const resetFrame = () => {
      eventName = null
      frameId = null
      dataLines = []
      rawLines = []
    }

    const malformed = (raw: string) => { options.onMalformedFrame?.(raw) }

    const dispatch = (): 'continue' | 'control' | 'revoked' => {
      const name = eventName
      const id = frameId
      const data = dataLines.join('\n')
      const raw = rawLines.join('\n')
      resetFrame()
      if (name === null && id === null && data === '') return 'continue'
      let payload: Record<string, any> | null = null
      if (data !== '') {
        try {
          const parsed = JSON.parse(data)
          if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) payload = parsed
        } catch { payload = null }
      }
      if (name === null || payload === null) { malformed(raw); return 'continue' }
      switch (name) {
        case 'turn.started': {
          if (id === null) break
          const fields = pickStrings(payload, ['session_id', 'revision', 'run_id', 'message_id', 'initiator_user_id', 'status'])
          if (!fields) break
          lastEventId = id
          sawProgress = true
          options.onTurnStarted?.(fields)
          return 'continue'
        }
        case 'execution': {
          const fields = pickStrings(payload, ['session_id', 'message_id', 'event_id'])
          const streamSeq = payload.stream_seq
          if (id === null || !fields || typeof streamSeq !== 'number' || !isExecutionEventV3(payload.event)) break
          lastEventId = id
          sawProgress = true
          options.onExecution?.({ session_id: fields.session_id, message_id: fields.message_id, event_id: fields.event_id, stream_seq: streamSeq, event: payload.event })
          return 'continue'
        }
        case 'turn.completed': {
          if (id === null) break
          const fields = pickStrings(payload, ['session_id', 'message_id', 'run_id', 'status', 'revision'])
          if (!fields) break
          lastEventId = id
          sawProgress = true
          options.onTurnCompleted?.(fields)
          return 'continue'
        }
        case 'thread.changed': {
          const fields = pickStrings(payload, ['session_id', 'revision'])
          const lastSeq = payload.last_message_seq
          const reason = payload.reason
          if (!fields || typeof lastSeq !== 'number') break
          if (reason !== undefined && !THREAD_CHANGED_REASONS.includes(reason)) break
          const event: SessionLiveThreadChangedEvent = { session_id: fields.session_id, revision: fields.revision, last_message_seq: lastSeq }
          if (reason !== undefined) event.reason = reason
          options.onThreadChanged?.(event)
          return 'control'
        }
        case 'members.changed': {
          if (!pickStrings(payload, ['session_id', 'revision'])) break
          options.onMembersChanged?.(paneKey)
          return 'control'
        }
        case 'session.access.revoked': {
          const fields = pickStrings(payload, ['session_id'])
          const reason = payload.reason
          if (!fields || (reason !== 'participant_removed' && reason !== 'participant_left')) break
          lastEventId = null
          sawProgress = false
          options.onAccessLost?.(paneKey, reason)
          return 'revoked'
        }
        default:
          break
      }
      malformed(raw)
      return 'continue'
    }

    const processLine = (line: string): 'continue' | 'control' | 'revoked' => {
      if (line === '') return dispatch()
      if (line.startsWith(':')) { sawProgress = true; return 'continue' }
      const colon = line.indexOf(':')
      const field = colon === -1 ? line : line.slice(0, colon)
      let value = colon === -1 ? '' : line.slice(colon + 1)
      if (value.startsWith(' ')) value = value.slice(1)
      rawLines.push(line)
      if (field === 'event') eventName = value
      else if (field === 'id') frameId = value || null
      else if (field === 'data') dataLines.push(value)
      return 'continue'
    }

    try {
      while (true) {
        const chunk = await activeReader.read()
        if (chunk.done) break
        if (chunk.value) buffer += decoder.decode(chunk.value, { stream: true })
        let newline = buffer.indexOf('\n')
        while (newline !== -1) {
          const line = buffer.slice(0, newline)
          buffer = buffer.slice(newline + 1)
          const result = processLine(line)
          if (result !== 'continue') { outcome = result; break }
          newline = buffer.indexOf('\n')
        }
        if (outcome !== 'eof') break
      }
      buffer += decoder.decode()
    } finally {
      if (reader === activeReader) reader = null
      try { await activeReader.cancel() } catch { /* reader already cancelled */ }
      try { activeReader.releaseLock() } catch { /* lock already released */ }
    }
    return outcome
  }

  const pump = async () => {
    if (loopActive || stopped || revoked) return
    loopActive = true
    try {
      while (!stopped && !revoked) {
        reopenRequested = false
        const ctrl = new AbortController()
        controller = ctrl
        let response: Response
        try {
          response = await fetchImpl(buildUrl(), { method: 'GET', headers: buildHeaders(), signal: ctrl.signal })
        } catch {
          controller = null
          if (stopped) break
          await waitBeforeRetry()
          continue
        }
        notifyAuthExpiredFromResponse(response, Boolean(options.authToken))
        if (!response.ok) {
          controller = null
          if (response.status >= RETRYABLE_STATUS_FLOOR) {
            await waitBeforeRetry()
            continue
          }
          options.onError?.(new SessionLiveHttpError(response.status))
          settleDone()
          break
        }
        if (!response.body) {
          controller = null
          await waitBeforeRetry()
          continue
        }
        afterCursor = null
        const outcome = await readFrames(response.body)
        controller = null
        if (sawProgress) {
          failureStreak = 0
          sawProgress = false
        }
        if (outcome === 'revoked') {
          revoked = true
          settleDone()
          break
        }
        if (outcome === 'control') break
        if (stopped) break
        if (reopenRequested) continue
        await waitBeforeRetry()
      }
    } finally {
      loopActive = false
    }
  }

  const openFreshStream = (after: string) => {
    const next = asText(after)
    if (stopped || revoked || next === null) return
    lastEventId = null
    afterCursor = next
    failureStreak = 0
    reopenRequested = true
    if (loopActive) {
      controller?.abort()
      releaseReader()
      return
    }
    void pump()
  }

  void pump()

  return {
    paneKey,
    cursor: () => lastEventId,
    done,
    stop,
    openFreshStream,
  }
}
