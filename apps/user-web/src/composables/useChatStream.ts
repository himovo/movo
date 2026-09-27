// Thin wrapper around POST /chat/completions that pumps NDJSON lines into a callback.

import type { ExecutionEventV3 } from '../features/execution-v3/domain/protocol'
import { notifyAuthExpiredFromResponse } from '../api/authExpiry'
import { createStreamReadiness } from './tasks/streamReadiness'
import { isChatStreamAccessRevokedEvent, type ChatStreamAccessRevokedEvent } from './sessionLiveProjection'

export {
  CHAT_STREAM_ACCESS_REVOKED, isChatStreamAccessRevokedEvent,
  type ChatStreamAccessRevokedEvent, type ChatStreamAccessRevokedReason,
} from './sessionLiveProjection'

/** Server contract on POST /chat/completions 409: a concurrent run holds the session. */
export const SESSION_ALREADY_RUNNING = 'session_already_running'

/** Server contract on POST /chat/completions 409: the client user-message id was rejected. */
export const USER_MESSAGE_ID_CONFLICT = 'user_message_id_conflict'

/**
 * Non-OK chat-completions response. `code` is the parsed FastAPI dict-detail
 * error code; consumers distinguish server contracts on status + code, never
 * on the display message.
 */
export class ChatStreamHttpError extends Error {
  status: number
  code: string | null

  constructor(status: number, code: string | null, message: string) {
    super(message)
    this.name = 'ChatStreamHttpError'
    this.status = status
    this.code = code
  }
}

export interface ChatStreamRequest {
  messages: any[]
  modelId?: string
  output_spec?: Record<string, any>
  knowledgeQaEnabled?: boolean
  knowledgeBaseIds?: string[]
  timezone?: string
}

export interface ChatStreamHandle {
  /** Backend session id (returned via X-Session-Id header on stream start) */
  sessionId: string | null
  /** Per-turn message id (returned via X-Message-Id header on stream start) */
  messageId: string | null
  /** Effective user-message id: the X-User-Message-Id response header when the
   *  server returned one, otherwise the requested opts.userMessageId. Optional
   *  because non-chat resume handles (taskResume) never send the header. */
  userMessageId?: string | null
  /** Resolves after response headers are available, including failed requests. */
  ready: Promise<void>
  /** Promise that resolves when the stream finishes (or aborts cleanly) */
  done: Promise<void>
  /** Aborts the local fetch (does NOT inform backend; call cancelChat() for that) */
  abort: () => void
}

export function startChatStream(
  body: ChatStreamRequest,
  onEvent: (ev: ExecutionEventV3) => void,
  opts: {
    authToken?: string | null
    /** Sent as X-User-Message-Id so the server can key the user row to this id. */
    userMessageId?: string
    onSessionId?: (sid: string) => void
    onMessageId?: (mid: string) => void
    onUserMessageId?: (mid: string) => void
    onAccessRevoked?: (event: ChatStreamAccessRevokedEvent) => void
  } = {},
): ChatStreamHandle {
  const ctrl = new AbortController()
  const readiness = createStreamReadiness()
  const handle: ChatStreamHandle = {
    sessionId: null,
    messageId: null,
    userMessageId: opts.userMessageId || null,
    ready: readiness.ready,
    done: Promise.resolve(),
    abort: () => ctrl.abort(),
  }

  handle.done = (async () => {
    try {
      const headers: Record<string, string> = { 'Content-Type': 'application/json' }
      if (opts.authToken) headers.Authorization = `Bearer ${opts.authToken}`
      if (opts.userMessageId) headers['X-User-Message-Id'] = opts.userMessageId
      const resp = await fetch('/askai-api/api/chat/completions', {
        method: 'POST',
        headers,
        body: JSON.stringify(body),
        signal: ctrl.signal,
      })
      notifyAuthExpiredFromResponse(resp, Boolean(opts.authToken))
      if (!resp.ok) {
        let errorMessage = `Request failed: ${resp.status}`
        let errorCode: string | null = null
        try {
          const contentType = resp.headers.get('content-type') || ''
          if (contentType.includes('application/json')) {
            const payload = await resp.json()
            const detail = payload?.detail
            if (typeof detail === 'string' && detail.trim()) {
              errorMessage = detail.trim()
            } else if (detail?.message) {
              errorMessage = String(detail.message)
              if (typeof detail.code === 'string' && detail.code.trim()) errorCode = detail.code
            } else if (payload?.message) {
              errorMessage = String(payload.message)
              if (typeof payload?.code === 'string' && payload.code.trim()) errorCode = payload.code
            }
          } else {
            const text = (await resp.text()).trim()
            if (text) errorMessage = text
          }
        } catch {
          // Ignore parse failures and keep the status-based fallback.
        }
        throw new ChatStreamHttpError(resp.status, errorCode, errorMessage)
      }
      const sid = resp.headers.get('X-Session-Id')
      if (sid) {
        handle.sessionId = sid
        opts.onSessionId?.(sid)
      }
      const mid = resp.headers.get('X-Message-Id')
      if (mid) {
        handle.messageId = mid
        opts.onMessageId?.(mid)
      }
      const umid = resp.headers.get('X-User-Message-Id') || opts.userMessageId || null
      if (umid) {
        handle.userMessageId = umid
        opts.onUserMessageId?.(umid)
      }
      readiness.settle()
      if (!resp.body) throw new Error('No response body')

      const reader = resp.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''
      let accessRevoked = false
      const pumpLine = (raw: string) => {
        const s = raw.trim()
        if (!s || accessRevoked) return
        let parsed: unknown
        try {
          parsed = JSON.parse(s)
        } catch {
          console.warn('[chat-stream] bad line', s)
          return
        }
        if (isChatStreamAccessRevokedEvent(parsed)) {
          accessRevoked = true
          opts.onAccessRevoked?.(parsed)
          return
        }
        try {
          onEvent(parsed as ExecutionEventV3)
        } catch (e) {
          console.warn('[chat-stream] bad line', s)
        }
      }
      while (!accessRevoked) {
        const { done, value } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop() || ''
        for (const line of lines) {
          pumpLine(line)
          if (accessRevoked) break
        }
      }
      if (accessRevoked) {
        // Terminal line already seen: close our side of the reader without
        // cancelling the backend run (the server EOFs right after it).
        try {
          reader.releaseLock()
        } catch {
          /* the reader is already released */
        }
      } else if (buffer.trim()) {
        pumpLine(buffer)
      }
    } finally {
      readiness.settle()
    }
  })()

  return handle
}

export async function cancelChat(sessionId: string, authToken?: string | null): Promise<boolean> {
  if (!sessionId) return false
  try {
    const resp = await fetch('/askai-api/api/chat/cancel', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(authToken ? { Authorization: `Bearer ${authToken}` } : {}),
      },
      body: JSON.stringify({ session_id: sessionId }),
      keepalive: true,
    })
    if (!resp.ok) return false
    const payload = await resp.json().catch(() => null)
    return payload?.code === 0
  } catch {
    return false
  }
}

export async function fetchChatMessageEvents(
  messageId: string,
  after: number,
  opts: { authToken?: string | null } = {},
): Promise<{
  events: ExecutionEventV3[]
  next_index: number
  next_cursor: number
  status: string
  live: boolean
}> {
  const headers: Record<string, string> = {}
  if (opts.authToken) headers.Authorization = `Bearer ${opts.authToken}`
  const query = new URLSearchParams({ after_cursor: String(Math.max(0, after || 0)) })
  const resp = await fetch(`/askai-api/api/chat/messages/${encodeURIComponent(messageId)}/events?${query.toString()}`, {
    method: 'GET',
    headers,
  })
  notifyAuthExpiredFromResponse(resp, Boolean(opts.authToken))
  if (!resp.ok) throw new Error(`Recover failed: ${resp.status}`)
  const payload = await resp.json()
  const data = payload?.data || {}
  return {
    events: Array.isArray(data.events) ? data.events : [],
    next_index: typeof data.next_index === 'number' ? data.next_index : after,
    next_cursor: typeof data.next_cursor === 'number'
      ? data.next_cursor
      : (typeof data.next_index === 'number' ? data.next_index : after),
    status: String(data.status || 'live'),
    live: Boolean(data.live),
  }
}

export async function resolvePermission(
  sessionId: string,
  requestId: string,
  decision: 'allow' | 'deny' | 'always_allow',
  extras: { reason?: string; updated_args?: Record<string, any> } = {},
): Promise<void> {
  await fetch('/askai-api/api/chat/permission', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      session_id: sessionId,
      request_id: requestId,
      decision,
      reason: extras.reason || '',
      updated_args: extras.updated_args || {},
    }),
  }).catch(() => { })
}
