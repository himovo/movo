/**
 * T8: pure projection rules shared by the runtime store and the POST transport.
 *
 * Merge identity is T5's server-computed `legacy_key`, consumed VERBATIM:
 * `message:{message_id}` when a non-empty id exists, otherwise the endpoint's
 * key. The browser never synthesizes a key and never collapses two rows that
 * carry different keys — not even when both lack `message_id` and `seq`.
 *
 * Ordering is by `seq` ONLY when every row carries a distinct allocated `seq`
 * (allocation starts at 1). A row reported as `seq: 0` is a T5 DEGRADED
 * unsequenced row, so the server's response order is authoritative and this
 * module returns the rows exactly as received — an ascending sort by `seq`
 * already reproduces it.
 */

/** Terminal NDJSON line the POST stream emits before EOF on access loss. */
export const CHAT_STREAM_ACCESS_REVOKED = 'session.access.revoked'

/** Same two-member union the session-SSE `session.access.revoked` frame carries. */
export type ChatStreamAccessRevokedReason = 'participant_removed' | 'participant_left'

/** Typed terminal POST event; recognized BEFORE the ExecutionEventV3 cast. */
export interface ChatStreamAccessRevokedEvent {
  type: typeof CHAT_STREAM_ACCESS_REVOKED
  session_id: string
  reason: ChatStreamAccessRevokedReason
}

export function isChatStreamAccessRevokedEvent(value: unknown): value is ChatStreamAccessRevokedEvent {
  if (!value || typeof value !== 'object') return false
  const candidate = value as { type?: unknown; session_id?: unknown; reason?: unknown }
  return candidate.type === CHAT_STREAM_ACCESS_REVOKED &&
    typeof candidate.session_id === 'string' &&
    (candidate.reason === 'participant_removed' || candidate.reason === 'participant_left')
}

export type LiveMessageAuthor = {
  user_id: string
  display_name: string | null
  avatar_url: string | null
}

export type MergeKeyedMessage = {
  message_id?: string | null
  legacy_key?: string | null
}

export type SequencedMessage = {
  seq?: number | null
}

export type ProjectionMessage = MergeKeyedMessage & SequencedMessage & {
  role?: string
  content?: string
  user_id?: string
  author?: LiveMessageAuthor | null
}

/** Server-computed fallback identity, consumed as given; null when the row
 *  carries none, in which case it is never matched against another row. */
export function messageMergeKey(message: MergeKeyedMessage): string | null {
  const id = message.message_id
  if (typeof id === 'string' && id.length > 0) return `message:${id}`
  const legacy = message.legacy_key
  if (typeof legacy === 'string' && legacy.length > 0) return legacy
  return null
}

/** True when every row carries a distinct `seq` allocated from 1 upward. */
export function hasFullyAllocatedSeq(rows: readonly SequencedMessage[]): boolean {
  if (rows.length === 0) return true
  const seen = new Set<number>()
  for (const row of rows) {
    const seq = row.seq
    if (typeof seq !== 'number' || !Number.isInteger(seq) || seq < 1) return false
    if (seen.has(seq)) return false
    seen.add(seq)
  }
  return true
}

/** Distributed rows are ordered by `seq`; a degraded response keeps the
 *  server's order verbatim (the client MUST NOT re-sort it). */
export function orderAuthoritativeMessages<T extends SequencedMessage>(rows: readonly T[]): T[] {
  if (!hasFullyAllocatedSeq(rows)) return rows.slice()
  return rows.slice().sort((left, right) => Number(left.seq) - Number(right.seq))
}

export type AuthoritativeMergeResult<T> = {
  messages: T[]
  /** Merge keys matched to an existing runtime row, in authoritative order. */
  matchedKeys: string[]
  /** Merge keys of authoritative rows appended because no runtime row matched. */
  appendedKeys: string[]
  /** Existing rows the snapshot did not mention, kept verbatim in place. */
  preservedCount: number
}

function mergeRuntimeRow<T extends ProjectionMessage & { _id?: string }>(
  existing: T,
  incoming: ProjectionMessage,
): T {
  const next = { ...(existing as Record<string, unknown>), ...(incoming as Record<string, unknown>) }
  if (existing._id !== undefined) next._id = existing._id
  // The durable execution store is runtime state, not snapshot state: a
  // snapshot must never discard accumulated execution events.
  if ((existing as Record<string, unknown>)._execV3 !== undefined) {
    next._execV3 = (existing as Record<string, unknown>)._execV3
  }
  const existingContent = typeof existing.content === 'string' ? existing.content : ''
  const incomingContent = typeof incoming.content === 'string' ? incoming.content : ''
  if (!incomingContent && existingContent) next.content = existingContent
  return next as T
}

/**
 * Reconcile one authoritative snapshot into the runtime rows.
 *
 * Matched rows are replaced IN PLACE (their position, `_id`, and `_execV3`
 * survive); authoritative rows without a match are appended in authoritative
 * order; runtime-only rows the snapshot does not mention are preserved. Rows
 * without any merge key are appended as distinct rows and can never collapse
 * into one another.
 */
export function mergeAuthoritativeMessages<T extends ProjectionMessage & { _id?: string }>(
  existing: readonly T[],
  incoming: readonly ProjectionMessage[],
): AuthoritativeMergeResult<T> {
  const ordered = orderAuthoritativeMessages(incoming)
  // Keep the first row per merge key: a re-keyed optimistic row can collide
  // with a row an earlier snapshot appended.
  const base: T[] = []
  const baseIndexByKey = new Map<string, number>()
  existing.forEach((row) => {
    const key = messageMergeKey(row)
    if (key !== null) {
      if (baseIndexByKey.has(key)) return
      baseIndexByKey.set(key, base.length)
    }
    base.push(row)
  })
  const mergedByIndex = new Map<number, T>()
  const matchedKeys: string[] = []
  const appended: T[] = []
  const appendedKeys: string[] = []
  for (const row of ordered) {
    const key = messageMergeKey(row)
    const index = key === null ? undefined : baseIndexByKey.get(key)
    if (key !== null && index !== undefined) {
      mergedByIndex.set(index, mergeRuntimeRow(base[index], row))
      matchedKeys.push(key)
    } else {
      appended.push(row as T)
      appendedKeys.push(key ?? '')
    }
  }
  const messages: T[] = []
  let preservedCount = 0
  base.forEach((row, index) => {
    const merged = mergedByIndex.get(index)
    if (merged) {
      messages.push(merged)
    } else {
      messages.push(row)
      preservedCount += 1
    }
  })
  messages.push(...appended)
  return { messages, matchedKeys, appendedKeys, preservedCount }
}

/** Map the effective user-message id onto the optimistic row so the next
 *  authoritative snapshot matches it by `message:{id}` instead of appending
 *  a duplicate bubble. Returns true when the row was re-keyed. */
export function applyEffectiveUserMessageId(
  row: { message_id?: string | null },
  effectiveId: string | null | undefined,
): boolean {
  if (!effectiveId || row.message_id === effectiveId) return false
  row.message_id = effectiveId
  return true
}

/** Data rows the runtime must drop after a 409 conflict. */
export function withoutMessages<T extends { _id?: string }>(
  messages: readonly T[],
  ids: ReadonlyArray<string | undefined>,
): T[] {
  const drop = new Set(ids.filter((id): id is string => typeof id === 'string' && id.length > 0))
  return messages.filter((message) => !message._id || !drop.has(message._id))
}

/** True for the 409 codes the client must treat as manual-only (no retry, no
 *  queueing): a concurrent run, or a rejected client user-message id. */
export function isManualOnlyConflict(code: string | null | undefined): boolean {
  return code === 'session_already_running' || code === 'user_message_id_conflict'
}

/** A local POST releases ownership into the durable recovery path unless
 *  access was revoked or the pane was destroyed. */
export function shouldReleaseToDurableRecovery(state: {
  accessLost: boolean
  paneAlive: boolean
  aborted: boolean
}): boolean {
  return !state.accessLost && state.paneAlive && !state.aborted
}

export const PRE_HEADER_BUFFER_MAX_ROWS = 200
export const PRE_HEADER_BUFFER_MAX_BYTES = 262144

export type PreHeaderBufferState<T> = {
  rows: T[]
  bytes: number
  overflowed: boolean
}

export function createPreHeaderBufferState<T>(): PreHeaderBufferState<T> {
  return { rows: [], bytes: 0, overflowed: false }
}

export function utf8ByteLength(value: string): number {
  return new TextEncoder().encode(value).length
}

/**
 * Buffer a session execution frame while a local POST is pending without its
 * header. Crossing either cap empties the whole buffer: a partial buffer can
 * no longer distinguish the local POST's frames from foreign ones, so the
 * durable recovery path reconciles instead.
 */
export function bufferPreHeaderEvent<T>(
  state: PreHeaderBufferState<T>,
  event: T,
  byteLength: number,
): void {
  if (state.overflowed) return
  if (
    state.rows.length + 1 > PRE_HEADER_BUFFER_MAX_ROWS ||
    state.bytes + byteLength > PRE_HEADER_BUFFER_MAX_BYTES
  ) {
    state.rows = []
    state.bytes = 0
    state.overflowed = true
    return
  }
  state.rows.push(event)
  state.bytes += byteLength
}

/** Flush once the local assistant `message_id` is known: the local POST's own
 *  frames are dropped, every foreign frame is returned for consumption. An
 *  overflowed buffer resolves to [] (durable recovery reconciles it). */
export function drainPreHeaderEvents<T extends { message_id?: string | null }>(
  state: PreHeaderBufferState<T>,
  localAssistantMessageId: string | null,
): T[] {
  const rows = state.overflowed ? [] : state.rows
  state.rows = []
  state.bytes = 0
  state.overflowed = false
  if (!localAssistantMessageId) return rows
  return rows.filter((row) => row.message_id !== localAssistantMessageId)
}

/** The pane that owns the local POST ignores session-SSE execution for that
 *  turn while other panes consume it. */
export function shouldIgnoreSessionExecution(
  localPostMessageId: string | null | undefined,
  messageId: string | null | undefined,
): boolean {
  return Boolean(localPostMessageId && messageId === localPostMessageId)
}
