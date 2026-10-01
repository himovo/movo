import { computed, markRaw, reactive, ref } from 'vue'
import { fetchOrgBilling } from '../api/auth'
import { uploadChatDocument, uploadChatImage, type UploadedDocument, type UploadedImage } from '../api/chat'
import { getSession, type ChatMessage, type ChatMessageAuthor, type SessionDetail } from '../api/sessions'
import { fetchChatMessageEvents, startChatStream, ChatStreamHttpError, type ChatStreamHandle } from './useChatStream'
import {
  applyEffectiveUserMessageId,
  bufferPreHeaderEvent,
  createPreHeaderBufferState,
  drainPreHeaderEvents,
  isManualOnlyConflict,
  mergeAuthoritativeMessages,
  shouldIgnoreSessionExecution,
  shouldReleaseToDurableRecovery,
  utf8ByteLength,
  withoutMessages,
  type PreHeaderBufferState,
} from './sessionLiveProjection'
import { getLocale, t } from './i18n'
import { resumeBrowserInterventionTaskUntilSettled } from './tasks/browserInterventionTaskFlow'
import {
  browserInterventionTransition,
  normalizeBrowserIntervention,
} from './browser/browserInterventionProjection'
import type { ExecutionStoreV3 } from '../features/execution-v3/stores/executionStore'
import type { DshTaskChangeSet } from '../platform/types'
import { isExecutionEventV3, type ExecutionEventV3 } from '../features/execution-v3/domain/protocol'
import { ensureMessageExecutionV3 } from '../features/execution-v3/stores/messageExecution'
import { refreshAfterRun } from './chatRuntimeRefresh'
import { applyAssistantContentEvent } from '../features/execution-v3/domain/assistantContent'
import type { BrowserAssistanceHandoff } from './browser/useBrowserWorkspace'
import { stopChatGeneration } from './chatCancellation'
import {
  noteSessionLiveControlFrame,
  noteSessionLiveData,
  startSessionLiveStream,
  type SessionLiveAccessRevokedReason,
  type SessionLiveExecutionEvent,
  type SessionLiveStreamHandle,
} from './useSessionLiveStream'

export type RuntimeDocumentInfo = {
  id?: string
  type: 'pdf' | 'docx' | 'ppt' | 'pptx' | 'md' | 'html' | 'xlsx' | 'presentation_preview_bundle'
  url: string
  filename?: string
  title?: string
  object_path?: string
  signed_url?: string
  content_type?: string
  size?: number
  bundle?: Record<string, any>
}

export type RuntimeImageInfo = {
  object_path?: string
  url?: string
  signed_url?: string
  filename?: string
  content_type?: string
  size?: number
}

export type RuntimeMessage = {
  role: 'user' | 'assistant'
  content: string
  plan?: any
  progress?: { content: string; timestamp?: string }[]
  _id?: string
  _execV3?: ExecutionStoreV3
  _provisionalTextByItem?: Record<string, string>
  _backendSid?: string
  message_id?: string
  /** Message author (todo 28): the viewer's own user_id on optimistic pushes,
   *  the author's user_id preserved from session-GET messages by
   *  normalizeMessages. Absent on legacy/system-shaped messages. */
  user_id?: string
  /** T5: stable server-computed merge identity, consumed verbatim. */
  legacy_key?: string
  /** T5: allocated message sequence; `0` marks a DEGRADED unsequenced row. */
  seq?: number
  /** T5: authoritative user-message author projection; T9 renders this. */
  author?: ChatMessageAuthor | null
  execution_events?: any[]
  documents?: RuntimeDocumentInfo[]
  images?: RuntimeImageInfo[]
  evidence_bundles?: any[]
  evidenceBundles?: any[]
  trigger_source?: string
  scheduled_job_id?: string
  scheduled_run_id?: string
  created_at?: string
  _codeChanges?: DshTaskChangeSet
}

export type PendingRuntimeDocument = {
  file: File
  kind: RuntimeDocumentInfo['type']
}

export type RuntimeIntervention = {
  reason: string
  category: string
  url?: string
  domain?: string
  screenshot?: string
  suspension_id?: string
  run_id?: string
  node_id?: string
  browser_session_id?: string
  tab_id?: string
  resumable?: boolean
  handoff?: BrowserAssistanceHandoff
} | null

export type ChatRuntimePane = {
  key: string
  sessionId: string | null
  messages: RuntimeMessage[]
  running: boolean
  stopping: boolean
  lastActivatedAt: number
  activeStream: ChatStreamHandle | null
  abortController: AbortController | null
  activeAssistantMessageId: string | null
  activeIntervention: RuntimeIntervention
  authResumeController: AbortController | null
  operationId: number
  activeAuthToken: string | null
  executionLocation: 'server' | 'desktop' | 'remote_sandbox'
  runtimePresetId: string
  modelInstanceId: string
  codeProject: { workspace_id: string; git_branch: string; worktree: boolean } | null
  /** T7 access-loss latch: the ONLY writer is markAccessLost; once true it stays true. */
  accessLost: boolean
  /** T7: the typed reason of the latch above, retained for the access-lost notice. */
  accessLostReason: SessionLiveAccessRevokedReason | null
  /** T7: increments on every members.changed; drives header/dialog participant refreshes. */
  membersRevision: number
  /** T7: the single session live SSE stream bound to this pane while it is viewed. */
  liveStream: SessionLiveStreamHandle | null
  /** T7: bumped on every bind/teardown; stale stream callbacks compare it. */
  liveGeneration: number
  /** T7: authoritative identity used to mint snapshot refreshes after invalidations. */
  liveAuth: PaneLiveAuth | null
  /** T7: sequence guard for overlapping authoritative snapshot refreshes. */
  liveRefreshSeq: number
  /** T8/T9: authoritative shared-pane flag from detail.access/participant_count. */
  shared: boolean
  /** T8: true while a local POST holds this pane's turn before its headers. */
  localPostPending: boolean
  /** T8: assistant message_id established by the local POST headers; the pane
   *  ignores session-SSE execution for that id. Separate from a resumed
   *  recovery handle. */
  localPostMessageId: string | null
  /** T8: transient top-of-conversation notice for a manual-only 409; the ONLY
   *  writer is notifySessionBusy. Never appended to `messages`. */
  busyNotice: string | null
  /** T8: monotonic token so a re-trigger resets the auto-dismiss timer. */
  busyNoticeToken: number
  /** T8: pre-header session execution buffer (200 rows / 256 KiB caps). */
  preHeader: PreHeaderBufferState<SessionLiveExecutionEvent>
  /** T8: foreign early-turn execution buffer (200 rows / 256 KiB caps, same
   *  whole-drop policy as preHeader). A foreign frame whose assistant row has
   *  not merged yet waits here instead of being silently dropped; the
   *  snapshot flush applies it in stream order. Never appended to `messages`
   *  directly, so it cannot create a row. */
  pendingForeign: PreHeaderBufferState<SessionLiveExecutionEvent>
  /** T8: session-SSE malformed-frame counter; diagnostics only, never UI. */
  malformedFrameCount: number
}

/** T7: caller identity captured at bind time for the invalidation snapshot refresh. */
export type PaneLiveAuth = { userId: string; mainId?: string; authToken?: string | null }

type SendInput = {
  text: string
  images: File[]
  documents: PendingRuntimeDocument[]
  knowledgeQaEnabled: boolean
  selectedSkillId?: string
  modelId?: string
  authToken: string | null
  userId: string | null
  mainId: string | null
  /** T8: authenticated viewer identity for the optimistic user row. */
  viewerAuthor: ChatMessageAuthor | null
  locale: 'zh' | 'en'
  timezone: string
}

type RuntimeCallbacks = {
  onSessionMissing?: (sessionId: string) => void
  onSessionResolved?: (sessionId: string) => void
  onSessionUpdated?: (sessionId: string) => void | Promise<void>
  onQuotaRefresh?: () => void | Promise<void>
  onLoginRequired?: () => void
}

export type ExternalTurnHandle = {
  pane: ChatRuntimePane
  assistant: RuntimeMessage
  apply(event: ExecutionEventV3): boolean
  finish(): void
  setCodeChanges(changes: DshTaskChangeSet): void
}

// T14's active_run.initiator_user_id reaches the wire as a raw dict passthrough;
// the declared SessionDetail.active_run shape predates todo 14. The local
// widening intersection (T22's SessionSharingDetail idiom) reads the initiator
// without touching the api files; the optional field keeps SessionDetail
// assignable.
type SessionRuntimeDetail = SessionDetail & { active_run?: { initiator_user_id?: string } }

const state = reactive({
  panes: [] as ChatRuntimePane[],
  activeKey: '',
  unreadSessionIds: new Set<string>(),
})

let localSeq = 0
let runtimeCallbacks: RuntimeCallbacks = {}
let messageSeq = 0
const MAX_CACHED_PANES = 8

function nextLocalKey() {
  localSeq += 1
  return `local_${Date.now()}_${localSeq}`
}

function nextMessageId() {
  messageSeq += 1
  return `msg_${Date.now()}_${messageSeq}`
}

function ensureMessageId<T extends RuntimeMessage>(msg: T): T {
  if (msg._id) return msg
  return { ...msg, _id: nextMessageId() }
}

function normalizeMessages(raw: ChatMessage[] | RuntimeMessage[] | undefined): RuntimeMessage[] {
  if (!raw?.length) return []
  const result: RuntimeMessage[] = []
  for (const item of raw) {
    const role = item.role === 'user' ? 'user' : 'assistant'
    const msg = ensureMessageId({ ...(item as RuntimeMessage), role, content: item.content || '', user_id: item.user_id })
    result.push(msg)
  }
  return result
}

function createPane(input: { key?: string; sessionId: string | null; messages?: ChatMessage[] | RuntimeMessage[]; running?: boolean }): ChatRuntimePane {
  return {
    key: input.key || nextLocalKey(),
    sessionId: input.sessionId,
    messages: normalizeMessages(input.messages),
    running: Boolean(input.running),
    stopping: false,
    lastActivatedAt: Date.now(),
    activeStream: null,
    abortController: null,
    activeAssistantMessageId: null,
    activeIntervention: null,
    authResumeController: null,
    operationId: 0,
    activeAuthToken: null,
    executionLocation: 'server',
    runtimePresetId: 'askai-enterprise',
    modelInstanceId: '',
    codeProject: null,
    accessLost: false,
    accessLostReason: null,
    membersRevision: 0,
    liveStream: null,
    liveGeneration: 0,
    liveAuth: null,
    liveRefreshSeq: 0,
    shared: false,
    localPostPending: false,
    localPostMessageId: null,
    busyNotice: null,
    busyNoticeToken: 0,
    preHeader: createPreHeaderBufferState<SessionLiveExecutionEvent>(),
    pendingForeign: createPreHeaderBufferState<SessionLiveExecutionEvent>(),
    malformedFrameCount: 0,
  }
}

function findPaneByKey(key: string) {
  return state.panes.find((pane) => pane.key === key) || null
}

function findPaneBySessionId(sessionId: string) {
  return state.panes.find((pane) => pane.sessionId === sessionId) || null
}

function activePane() {
  return findPaneByKey(state.activeKey)
}

function setActivePane(pane: ChatRuntimePane) {
  pane.lastActivatedAt = Date.now()
  state.activeKey = pane.key
  syncPaneLiveStream()
}

function pruneInactivePanes() {
  const activeKey = state.activeKey
  const mustKeep = new Set<string>()
  for (const pane of state.panes) {
    if (pane.running || pane.key === activeKey) {
      mustKeep.add(pane.key)
    }
  }

  const keepBySession = new Set<string>()
  const sessionPanes = state.panes
    .filter((pane) => pane.sessionId)
    .sort((a, b) => b.lastActivatedAt - a.lastActivatedAt)
  for (const pane of sessionPanes.slice(0, MAX_CACHED_PANES)) {
    keepBySession.add(pane.key)
  }

  const kept = state.panes.filter((pane) => mustKeep.has(pane.key) || keepBySession.has(pane.key))
  for (const pane of state.panes) {
    if (!kept.includes(pane)) stopPaneLiveStream(pane)
  }
  state.panes = kept
}

function clearUnread(sessionId: string | null) {
  if (!sessionId || !state.unreadSessionIds.has(sessionId)) return
  const next = new Set(state.unreadSessionIds)
  next.delete(sessionId)
  state.unreadSessionIds = next
}

// T30: this in-memory set is the OWNER rows' unread mechanism (App.vue's
// sessionIsUnread). Shared rows render from the server's shared_unread field
// via the separate sharedSessions ref and never read this set, so a shared
// id landing here (a shared pane stopping while inactive) cannot render a
// dot there. Never wire sessionIsUnread into the shared dot's condition —
// the set retains the id until clearUnread and would re-render a dot after
// the server cursor has cleared.
function markUnread(sessionId: string) {
  if (!sessionId) return
  const next = new Set(state.unreadSessionIds)
  next.add(sessionId)
  state.unreadSessionIds = next
}

function setPaneRunning(pane: ChatRuntimePane, running: boolean) {
  const wasRunning = pane.running
  pane.running = running
  if (wasRunning && !running && pane.sessionId && pane.key !== state.activeKey) {
    markUnread(pane.sessionId)
  }
  if (!running) pruneInactivePanes()
}

function resolvePaneSession(pane: ChatRuntimePane, sessionId: string, callbacks: RuntimeCallbacks = {}) {
  if (!sessionId) return
  const duplicate = state.panes.find((item) => item !== pane && item.sessionId === sessionId)
  if (duplicate) {
    const keepRunningPane = pane.running || !duplicate.running
    const keeper = keepRunningPane ? pane : duplicate
    const removed = keepRunningPane ? duplicate : pane
    keeper.sessionId = sessionId
    if (pane.modelInstanceId) keeper.modelInstanceId = pane.modelInstanceId
    else if (!keeper.modelInstanceId) keeper.modelInstanceId = duplicate.modelInstanceId
    keeper.lastActivatedAt = Math.max(keeper.lastActivatedAt, removed.lastActivatedAt)
    if (!keeper.messages.length && removed.messages.length) keeper.messages = removed.messages
    if (!keeper.activeStream && removed.activeStream) keeper.activeStream = removed.activeStream
    if (!keeper.abortController && removed.abortController) keeper.abortController = removed.abortController
    if (!keeper.activeAssistantMessageId && removed.activeAssistantMessageId) keeper.activeAssistantMessageId = removed.activeAssistantMessageId
    if (!keeper.activeIntervention && removed.activeIntervention) keeper.activeIntervention = removed.activeIntervention
    if (!keeper.authResumeController && removed.authResumeController) keeper.authResumeController = removed.authResumeController
    if (!keeper.liveAuth && removed.liveAuth) keeper.liveAuth = removed.liveAuth
    if (state.activeKey === removed.key) state.activeKey = keeper.key
    stopPaneLiveStream(removed)
    state.panes = state.panes.filter((item) => item !== removed)
    callbacks.onSessionResolved?.(sessionId)
    if (state.activeKey === keeper.key) startPaneLiveStream(keeper)
    return
  }
  pane.sessionId = sessionId
  callbacks.onSessionResolved?.(sessionId)
  syncPaneLiveStream()
}

function stopPaneLiveStream(pane: ChatRuntimePane) {
  pane.liveGeneration += 1
  const handle = pane.liveStream
  pane.liveStream = null
  handle?.stop()
  noteSessionLiveData(pane.key)
}

function paneLiveCallbackValid(pane: ChatRuntimePane, generation: number, sessionId: string) {
  return findPaneByKey(pane.key) === pane && pane.liveGeneration === generation && pane.sessionId === sessionId
}

async function refreshPaneLiveState(pane: ChatRuntimePane, generation: number, sessionId: string, reopen: boolean) {
  const auth = pane.liveAuth
  if (!auth || !paneLiveCallbackValid(pane, generation, sessionId)) return
  const sequence = pane.liveRefreshSeq + 1
  pane.liveRefreshSeq = sequence
  let detail: SessionRuntimeDetail
  try {
    detail = await getSession(sessionId, auth.userId, auth.mainId, auth.authToken)
  } catch {
    return
  }
  if (!paneLiveCallbackValid(pane, generation, sessionId) || pane.liveRefreshSeq !== sequence) return
  if (detail.execution_location) pane.executionLocation = detail.execution_location
  if (detail.runtime_preset_id) pane.runtimePresetId = detail.runtime_preset_id
  if (detail.model_instance_id !== undefined && detail.model_instance_id !== null) pane.modelInstanceId = detail.model_instance_id
  if (detail.code_project !== undefined) pane.codeProject = detail.code_project
  pane.shared = detail.access === 'shared' || (detail.participant_count ?? 0) > 0
  pane.messages = mergeAuthoritativeMessages(pane.messages, detail.messages || []).messages
  // T8: the snapshot may have materialized rows for early foreign frames;
  // apply them in stream order (event_id-deduped, rows are never created here).
  flushPendingForeignExecutions(pane)
  await refreshAfterRun(runtimeCallbacks, sessionId)
  if (!reopen || !paneLiveCallbackValid(pane, generation, sessionId)) return
  // T6 contract: every control invalidation counts toward the three-frame cap,
  // even when the authoritative payload carries no cursor to reopen from.
  const delay = noteSessionLiveControlFrame(pane.key)
  if (delay > 0) await new Promise<void>((resolve) => { setTimeout(resolve, delay) })
  const handle = pane.liveStream
  const cursor = typeof detail.live_cursor === 'string' && detail.live_cursor ? detail.live_cursor : null
  if (!handle || !cursor) return
  if (pane.liveStream !== handle || !paneLiveCallbackValid(pane, generation, sessionId)) return
  handle.openFreshStream(cursor)
}

/**
 * T8 removed-member 404: a 401/404/410 close carries no revocable frame, so
 * the pane probes readability exactly once — an unreadable session latches
 * access loss, a readable one reopens fresh. Never loops, never toasts; the
 * transport owns reconnect.
 */
async function handlePaneLiveStreamError(
  pane: ChatRuntimePane,
  generation: number,
  sessionId: string,
  status: number,
) {
  if (!paneLiveCallbackValid(pane, generation, sessionId)) return
  if (status !== 401 && status !== 404 && status !== 410) return
  const auth = pane.liveAuth
  if (!auth) return
  let detail: SessionRuntimeDetail | null = null
  try {
    detail = await getSession(sessionId, auth.userId, auth.mainId, auth.authToken)
  } catch {
    detail = null
  }
  if (!paneLiveCallbackValid(pane, generation, sessionId)) return
  if (!detail) {
    markAccessLost(pane.key, 'participant_removed')
    return
  }
  const handle = pane.liveStream
  if (!handle) return
  const cursor = typeof detail.live_cursor === 'string' && detail.live_cursor ? detail.live_cursor : null
  if (cursor) {
    handle.openFreshStream(cursor)
    return
  }
  // Readable but cursorless: cold re-attach instead of parking on the dead handle.
  stopPaneLiveStream(pane)
  startPaneLiveStream(pane)
}

function startPaneLiveStream(pane: ChatRuntimePane) {
  if (pane.liveStream) return
  if (!pane.sessionId || !pane.liveAuth || pane.accessLost) return
  if (pane.key !== state.activeKey) return
  const sessionId = pane.sessionId
  const generation = pane.liveGeneration + 1
  pane.liveGeneration = generation
  // T8: the transport settles after a terminal HTTP error, so at most one
  // onError fires per close; the flag guards even that single call.
  let errorSuspicionFired = false
  const refresh = (reopen: boolean) => {
    void refreshPaneLiveState(pane, generation, sessionId, reopen).catch(() => undefined)
  }
  const liveProgress = () => {
    if (!paneLiveCallbackValid(pane, generation, sessionId)) return false
    noteSessionLiveData(pane.key)
    return true
  }
  const handle = startSessionLiveStream({
    sessionId,
    paneKey: pane.key,
    authToken: pane.liveAuth.authToken,
    onThreadChanged: () => { refresh(true) },
    onMembersChanged: (paneKey) => {
      // members.changed is a CONTROL frame: it counts toward the cap (inside
      // the control-frame refresh) and must not reset the streak via liveProgress.
      if (!paneLiveCallbackValid(pane, generation, sessionId)) return
      notifyMembersChanged(paneKey)
      refresh(true)
    },
    onTurnStarted: () => { if (liveProgress()) refresh(false) },
    onExecution: (event) => { if (liveProgress()) consumeSessionExecution(pane, event) },
    onTurnCompleted: () => { if (liveProgress()) refresh(false) },
    onAccessLost: (paneKey, reason) => markAccessLost(paneKey, reason),
    // T8: malformed frames count diagnostics only — no UI surface.
    onMalformedFrame: () => { pane.malformedFrameCount += 1 },
    onError: (error) => {
      if (errorSuspicionFired) return
      errorSuspicionFired = true
      void handlePaneLiveStreamError(pane, generation, sessionId, error.status).catch(() => undefined)
    },
  })
  pane.liveStream = markRaw(handle)
}

function syncPaneLiveStream() {
  const active = activePane()
  for (const pane of state.panes) {
    if (pane !== active && pane.liveStream) stopPaneLiveStream(pane)
  }
  if (active) startPaneLiveStream(active)
}

/** T7: bump the pane's membersRevision on members.changed; never a fetch. */
function notifyMembersChanged(paneKey: string) {
  const pane = findPaneByKey(paneKey)
  if (pane) pane.membersRevision += 1
}

/** T7: pane-scoped counter by session id for the single-instance header call site. */
function membersRevisionFor(sessionId: string | null): number {
  if (!sessionId) return 0
  const pane = findPaneBySessionId(sessionId)
  return pane ? pane.membersRevision : 0
}

/**
 * T7 access-loss latch — the ONLY writer of `accessLost`. Exactly once per pane
 * key it aborts the session SSE stream, the local POST handle, and the recovery
 * controller; later calls for the same key are no-ops that never touch an
 * already-aborted handle. T8's POST path calls this same action; T10 only reads
 * the flag.
 */
function markAccessLost(paneKey: string, reason: SessionLiveAccessRevokedReason) {
  const pane = findPaneByKey(paneKey)
  if (!pane || pane.accessLost) return
  pane.accessLost = true
  pane.accessLostReason = reason
  stopPaneLiveStream(pane)
  pane.activeStream?.abort()
  pane.activeStream = null
  pane.abortController?.abort()
  pane.abortController = null
  pane.authResumeController?.abort()
  pane.authResumeController = null
}

function ensureExecV3(msg: RuntimeMessage): ExecutionStoreV3 {
  return ensureMessageExecutionV3(msg)
}

/** Apply one V3 event to a message row; false when it was a duplicate. */
function applyExecutionEventToMessage(
  pane: ChatRuntimePane,
  msg: RuntimeMessage,
  ev: ExecutionEventV3,
): boolean {
  if (!isExecutionEventV3(ev)) return false
  const store = ensureExecV3(msg)
  const before = store.state.rawEvents.length
  store.applyEvent(ev)
  if (store.state.rawEvents.length === before) return false
  applyAssistantContentEvent(msg, ev)
  const transition = browserInterventionTransition(ev)
  if (transition.kind === 'cleared') pane.activeIntervention = null
  if (transition.kind === 'activated') pane.activeIntervention = transition.intervention
  return true
}

/** T8 ownership: session-SSE execution is buffered until the local POST's
 *  headers exist, then foreign frames are consumed while the POST's own
 *  frames (same message_id) stay ignored. A foreign frame whose assistant
 *  row has not merged yet waits in pendingForeign for the snapshot flush
 *  instead of being silently dropped. */
function consumeSessionExecution(pane: ChatRuntimePane, frame: SessionLiveExecutionEvent) {
  if (pane.localPostPending && !pane.localPostMessageId) {
    bufferPreHeaderEvent(pane.preHeader, frame, utf8ByteLength(JSON.stringify(frame)))
    return
  }
  if (shouldIgnoreSessionExecution(pane.localPostMessageId, frame.message_id)) return
  const target = pane.messages.find(
    (msg) => msg.role === 'assistant' && msg.message_id === frame.message_id,
  )
  if (target) {
    applyExecutionEventToMessage(pane, target, frame.event)
    return
  }
  bufferPreHeaderEvent(pane.pendingForeign, frame, utf8ByteLength(JSON.stringify(frame)))
}

/** T8: apply buffered foreign frames to rows the snapshot just merged, in
 *  stream order. Still-rowless frames are dropped with containment (no UI);
 *  `messages` itself is never touched, so no duplicate row can appear. */
function flushPendingForeignExecutions(pane: ChatRuntimePane) {
  for (const frame of drainPreHeaderEvents(pane.pendingForeign, pane.localPostMessageId)) {
    const target = pane.messages.find(
      (msg) => msg.role === 'assistant' && msg.message_id === frame.message_id,
    )
    if (target) applyExecutionEventToMessage(pane, target, frame.event)
  }
}

/** T8: header arrived — adopt local-POST ownership and flush the pre-header
 *  buffer, consuming only the foreign frames. */
function adoptLocalPostMessageId(pane: ChatRuntimePane, messageId: string) {
  pane.localPostMessageId = messageId
  for (const frame of drainPreHeaderEvents(pane.preHeader, messageId)) {
    const target = pane.messages.find(
      (msg) => msg.role === 'assistant' && msg.message_id === frame.message_id,
    )
    if (target) applyExecutionEventToMessage(pane, target, frame.event)
  }
}

async function uploadImages(userId: string, files: File[], authToken?: string | null): Promise<UploadedImage[]> {
  const uploaded: UploadedImage[] = []
  for (const file of files) {
    uploaded.push(await uploadChatImage(userId, file, authToken))
  }
  return uploaded
}

async function uploadDocuments(userId: string, docs: PendingRuntimeDocument[], authToken?: string | null): Promise<RuntimeDocumentInfo[]> {
  const uploaded: RuntimeDocumentInfo[] = []
  for (const item of docs) {
    const result: UploadedDocument = await uploadChatDocument(userId, item.file, authToken)
    uploaded.push({
      type: item.kind,
      url: result.url || result.signed_url || '',
      filename: result.filename || item.file.name,
      title: result.filename || item.file.name,
      object_path: result.object_path,
      signed_url: result.signed_url,
      content_type: result.content_type,
      size: result.size,
    })
  }
  return uploaded
}

function resetPanePreview(pane: ChatRuntimePane) {
  pane.activeIntervention = null
}

const SESSION_BUSY_NOTICE_MS = 5000

// T8: a manual-only 409 is surfaced as a transient top-of-conversation notice
// owned by the pane itself — never a thread message, never an error bubble,
// never a retry or queue. The token makes a re-trigger restart the timer so the
// notice cannot dismiss early under a newer trigger.
function notifySessionBusy(pane: ChatRuntimePane, code: string | null) {
  pane.busyNotice = code === 'session_already_running'
    ? t('app.chat.session_busy_notice')
    : t('app.sidebar.session_running')
  pane.busyNoticeToken += 1
  const token = pane.busyNoticeToken
  window.setTimeout(() => {
    if (pane.busyNoticeToken === token) pane.busyNotice = null
  }, SESSION_BUSY_NOTICE_MS)
}

async function sendMessage(key: string, input: SendInput, callbacks: RuntimeCallbacks = {}) {
  const pane = findPaneByKey(key)
  if (!pane) return
  pane.authResumeController?.abort()
  pane.authResumeController = null
  if (pane.running) {
    await stopGeneration(key)
    return
  }

  const text = input.text.trim()
  const hasImages = input.images.length > 0
  const hasDocuments = input.documents.length > 0
  const hasSelectedSkill = !!input.selectedSkillId
  if (!text && !hasImages && !hasDocuments && !hasSelectedSkill) return
  if (!input.authToken || !input.userId || !input.mainId || input.mainId === 'default') {
    callbacks.onLoginRequired?.()
    return
  }

  pane.operationId += 1
  const operationId = pane.operationId
  setPaneRunning(pane, true)
  pane.activeAuthToken = input.authToken
  pane.liveAuth = { userId: input.userId, mainId: input.mainId, authToken: input.authToken }
  let uploadedImages: UploadedImage[] = []
  let uploadedDocuments: RuntimeDocumentInfo[] = []
  try {
    const quota = await fetchOrgBilling(input.authToken)
    if (pane.operationId !== operationId) return
    const remaining = Number(quota.data?.remainingPoints || 0)
    if (!quota.ok || remaining <= 0) {
      const isEnterprise = quota.data?.spaceType === 'enterprise'
      pane.messages.push({
        _id: nextMessageId(),
        role: 'assistant',
        content: isEnterprise
          ? '当前企业分派额度已用尽，请联系企业管理员调整额度。'
          : '个人赠送额度已用尽，请升级或切换到有可用额度的空间。',
      })
      setPaneRunning(pane, false)
      return
    }

    uploadedImages = await uploadImages(input.userId, input.images, input.authToken)
    if (pane.operationId !== operationId) return
    uploadedDocuments = await uploadDocuments(input.userId, input.documents, input.authToken)
  } catch (uploadErr) {
    pane.messages.push({
      _id: nextMessageId(),
      role: 'assistant',
      content: `[Error: ${input.locale === 'zh' ? '附件上传失败' : 'Failed to upload attachments'}: ${uploadErr}]`,
    })
    setPaneRunning(pane, false)
    pane.activeAuthToken = null
    return
  }
  if (pane.operationId !== operationId) return

  const viewerAuthor: ChatMessageAuthor = input.viewerAuthor ?? {
    user_id: input.userId || '',
    display_name: null,
    avatar_url: null,
  }
  const localPostUserMessageId = nextMessageId()
  const userMessage: RuntimeMessage = {
    _id: nextMessageId(),
    message_id: localPostUserMessageId,
    role: 'user',
    content: text,
    user_id: viewerAuthor.user_id || input.userId || undefined,
    author: viewerAuthor,
    images: uploadedImages as RuntimeImageInfo[],
    documents: uploadedDocuments,
    created_at: new Date().toISOString(),
  }
  pane.messages.push(userMessage)

  const assistantMsg: RuntimeMessage = {
    _id: nextMessageId(),
    role: 'assistant',
    content: '',
  }
  pane.messages.push(assistantMsg)
  pane.activeAssistantMessageId = assistantMsg._id || null
  ensureExecV3(assistantMsg).reset()
  resetPanePreview(pane)

  const ctrl = new AbortController()
  pane.abortController = ctrl
  let activeHandle: ChatStreamHandle | null = null
  let backendEventCursor = 0
  let backendTerminalReceived = false

  const applyAssistantEvent = (ev: ExecutionEventV3, options: { fromBackend?: boolean } = {}) => {
    const msg = pane.messages.find((item) => item._id === assistantMsg._id)
    if (!msg || !isExecutionEventV3(ev)) return
    if (
      options.fromBackend &&
      (ev.type === 'run.completed' || ev.type === 'run.failed' || ev.type === 'run.cancelled')
    ) {
      backendTerminalReceived = true
    }
    const accepted = applyExecutionEventToMessage(pane, msg, ev)
    if (accepted && options.fromBackend) {
      const sequence = Number(ev.stream_seq_end || ev.stream_seq || 0)
      backendEventCursor = sequence > 0 ? Math.max(backendEventCursor, sequence) : backendEventCursor + 1
    }
  }

  const recoverDisconnectedStream = async (showRecoveryEvent = true): Promise<boolean> => {
    const messageId = assistantMsg.message_id || activeHandle?.messageId || ''
    if (!messageId) return false
    if (showRecoveryEvent) {
      applyAssistantEvent({
        v: 3,
        event_id: `recover_${messageId}`,
        id: `recover_${messageId}`,
        ts: Date.now(),
        type: 'item.completed',
        item_kind: 'commentary',
        item_id: `recover_${messageId}`,
        revision: 1,
        payload: {
          message: input.locale === 'zh' ? '连接中断，正在恢复进度' : 'Connection interrupted, recovering progress',
        },
      })
    }
    let after = backendEventCursor
    while (!ctrl.signal.aborted) {
      try {
        const recovered = await fetchChatMessageEvents(messageId, after, { authToken: input.authToken })
        for (const ev of recovered.events) applyAssistantEvent(ev, { fromBackend: true })
        after = recovered.next_cursor
        backendEventCursor = recovered.next_cursor
        if (!recovered.live && recovered.status !== 'live') return true
      } catch {
        // The recovery endpoint can be unavailable during the same network outage.
      }
      await new Promise((resolve) => setTimeout(resolve, 2000))
    }
    return false
  }

  pane.localPostPending = true
  pane.localPostMessageId = null
  pane.preHeader = createPreHeaderBufferState<SessionLiveExecutionEvent>()
  try {
    const handle = startChatStream(
      {
        modelId: input.modelId || undefined,
        knowledgeQaEnabled: input.knowledgeQaEnabled,
        timezone: input.timezone,
        messages: pane.messages.slice(0, -1).map((m) => ({
          role: m.role,
          content: m.content,
          images: m.images || [],
          documents: m.documents || [],
        })),
        output_spec: {
          user_id: input.userId || undefined,
          main_id: input.mainId || undefined,
          task_id: pane.sessionId || undefined,
          selected_skill_id: input.selectedSkillId || undefined,
          manual_skill_selected: Boolean(input.selectedSkillId) || undefined,
        },
      },
      (ev) => {
        applyAssistantEvent(ev, { fromBackend: true })
      },
      {
        authToken: input.authToken,
        userMessageId: localPostUserMessageId,
        onSessionId: (sid) => {
          if (input.modelId) pane.modelInstanceId = input.modelId
          assistantMsg._backendSid = sid
          resolvePaneSession(pane, sid, callbacks)
        },
        onMessageId: (mid) => {
          assistantMsg.message_id = mid
          adoptLocalPostMessageId(pane, mid)
        },
        onUserMessageId: (mid) => {
          applyEffectiveUserMessageId(userMessage, mid)
        },
        onAccessRevoked: (event) => {
          markAccessLost(pane.key, event.reason)
        },
      },
    )
    activeHandle = handle
    pane.activeStream = handle
    ctrl.signal.addEventListener('abort', () => handle.abort())
    await handle.done
    if (!backendTerminalReceived && shouldReleaseToDurableRecovery({
      accessLost: pane.accessLost,
      paneAlive: findPaneByKey(pane.key) === pane,
      aborted: ctrl.signal.aborted,
    })) {
      // A proxy may close a streaming response cleanly. Verify the backend run
      // reached a terminal state instead of treating EOF as task completion.
      await recoverDisconnectedStream(true)
    }
    if (pane.sessionId && input.userId && input.authToken) {
      await resumeBrowserInterventionTaskUntilSettled({
        userId: input.userId,
        sessionId: pane.sessionId,
        authToken: input.authToken,
        modelId: input.modelId || undefined,
        locale: input.locale,
        signal: ctrl.signal,
        getIntervention: () => pane.activeIntervention,
        getMessages: () => pane.messages.slice(0, -1).map((m) => ({
          role: m.role,
          content: m.content,
          images: m.images || [],
          documents: m.documents || [],
        })),
        setWaitController: (controller) => { pane.authResumeController = controller },
        setRunning: (running) => setPaneRunning(pane, running),
        setActiveHandle: (resumed) => {
          activeHandle = resumed
          pane.activeStream = resumed
        },
        clearIntervention: () => { pane.activeIntervention = null },
        onEvent: (ev) => applyAssistantEvent(ev, { fromBackend: true }),
        onMessageId: (mid) => {
          backendEventCursor = 0
          backendTerminalReceived = false
          assistantMsg.message_id = mid
        },
      })
    }
  } catch (error: any) {
    if (error instanceof ChatStreamHttpError && error.status === 409 && isManualOnlyConflict(error.code)) {
      // Manual-only 409 (concurrent run or rejected user-message id): remove
      // BOTH optimistic bubbles, show the transient top-of-conversation notice,
      // and leave the composer enabled for a later retry — never an error
      // bubble, never an automatic retry, never a queue.
      pane.messages = withoutMessages(pane.messages, [userMessage._id, assistantMsg._id])
      notifySessionBusy(pane, error.code)
    } else if (error?.name !== 'AbortError') {
      const recovered = await recoverDisconnectedStream().catch(() => false)
      if (!recovered && !ctrl.signal.aborted) {
        const errText = String(error?.message || error || (input.locale === 'zh' ? '请求失败' : 'Request failed'))
        const localErrorId = 'err_' + Math.random().toString(36).slice(2)
        ensureExecV3(assistantMsg).applyEvent({
          v: 3,
          event_id: localErrorId,
          id: localErrorId,
          ts: Date.now(),
          type: 'item.failed',
          item_kind: 'error',
          item_id: 'local_error',
          revision: 1,
          payload: { message: errText },
        } as ExecutionEventV3)
      }
    }
  } finally {
    if (pane.operationId !== operationId) return
    pane.localPostPending = false
    pane.localPostMessageId = null
    pane.preHeader = createPreHeaderBufferState<SessionLiveExecutionEvent>()
    // Transport completion owns the running flag. Clear it before any optional
    // refresh callback so a slow or failed sidebar/billing request can never
    // leave the composer stuck in its loading state.
    pane.activeStream = null
    pane.abortController = null
    pane.activeAssistantMessageId = null
    if (pane.authResumeController?.signal.aborted) pane.authResumeController = null
    setPaneRunning(pane, false)

    const artifacts = assistantMsg._execV3?.state.artifacts || []
    const docs: RuntimeDocumentInfo[] = artifacts.map((a) => ({
      type: a.kind as RuntimeDocumentInfo['type'],
      url: a.url || '',
      signed_url: a.signed_url,
      object_path: a.object_path,
      filename: a.filename,
      title: a.title,
      content_type: a.content_type,
      size: a.size,
      bundle: a.bundle,
    }))
    if (docs.length) assistantMsg.documents = docs
    assistantMsg.execution_events = assistantMsg._execV3?.state.rawEvents || undefined
    assistantMsg.evidence_bundles = assistantMsg._execV3?.state.evidenceBundles || undefined

    const resolvedSessionId = assistantMsg._backendSid || pane.sessionId
    await refreshAfterRun(callbacks, resolvedSessionId)
  }
}

async function stopGeneration(key: string) {
  const pane = findPaneByKey(key)
  if (!pane) return false
  return await stopChatGeneration(pane, (running) => setPaneRunning(pane, running))
}

export function useChatRuntimeStore(callbacks: RuntimeCallbacks = {}) {
  runtimeCallbacks = callbacks
  const panes = computed(() => state.panes)
  const activeChatKey = computed(() => state.activeKey)
  const activeChatPane = computed(() => activePane())
  const runningSessionIds = computed(() => {
    const ids = new Set<string>()
    for (const pane of state.panes) {
      if (pane.running && pane.sessionId) ids.add(pane.sessionId)
    }
    return ids
  })
  const unreadSessionIdSet = computed(() => state.unreadSessionIds)
  const currentSessionId = computed(() => activePane()?.sessionId || null)

  function reset() {
    for (const pane of state.panes) {
      stopPaneLiveStream(pane)
      pane.activeStream?.abort()
      pane.abortController?.abort()
      pane.authResumeController?.abort()
    }
    state.panes = []
    state.activeKey = ''
    state.unreadSessionIds = new Set()
  }

  function startLocalSession() {
    const pane = createPane({ sessionId: null })
    state.panes = [...state.panes, pane]
    setActivePane(pane)
    pruneInactivePanes()
    return pane
  }

  async function selectSession(sessionId: string, userId: string, mainId?: string, authToken?: string | null) {
    clearUnread(sessionId)
    const existing = findPaneBySessionId(sessionId)
    if (existing) {
      existing.liveAuth = { userId, mainId, authToken }
      setActivePane(existing)
      return existing
    }
    const detail: SessionRuntimeDetail = await getSession(sessionId, userId, mainId, authToken)
    const pane = createPane({
      key: `session_${detail.id}`,
      sessionId: detail.id,
      messages: detail.messages || [],
    })
    pane.executionLocation = detail.execution_location || 'server'
    pane.runtimePresetId = detail.runtime_preset_id || 'askai-enterprise'
    pane.modelInstanceId = detail.model_instance_id || ''
    pane.codeProject = detail.code_project || null
    pane.shared = detail.access === 'shared' || (detail.participant_count ?? 0) > 0
    pane.liveAuth = { userId, mainId, authToken }
    state.panes = [...state.panes, pane]
    setActivePane(pane)
    pruneInactivePanes()
    if (detail.active_run?.message_id && authToken) {
      const assistant = [...pane.messages].reverse().find(
        (item) => item.role === 'assistant' && item.message_id === detail.active_run?.message_id,
      )
      if (assistant) {
        // Todo 29: the stop control is the composer's running button, shown
        // only while the pane runs. A foreign run — another member's, or a
        // legacy run with no recorded initiator — must not offer stop: the
        // server denies cancel for every non-initiator (403
        // session_cancel_initiator_required; fail-closed for legacy rows).
        // The poll below still follows the run's progress for every viewer.
        const runInitiatorUserId = detail.active_run.initiator_user_id || ''
        const restoredStore = ensureExecV3(assistant)
        pane.activeIntervention = normalizeBrowserIntervention(restoredStore.state.intervention)
        const controller = new AbortController()
        pane.abortController = controller
        pane.activeAssistantMessageId = assistant._id || null
        if (runInitiatorUserId === userId) setPaneRunning(pane, true)
        void (async () => {
          const store = restoredStore
          store.resumeLive()
          let cursor = Math.max(0, ...store.state.rawEvents.map((event) => Number(event.stream_seq_end || event.stream_seq || 0)))
          try {
            try {
              while (!controller.signal.aborted) {
                const recovered = await fetchChatMessageEvents(detail.active_run!.message_id, cursor, { authToken })
                for (const event of recovered.events) {
                  if (!isExecutionEventV3(event)) continue
                  store.applyEvent(event)
                  applyAssistantContentEvent(assistant, event)
                  const transition = browserInterventionTransition(event)
                  if (transition.kind === 'cleared') pane.activeIntervention = null
                  if (transition.kind === 'activated') pane.activeIntervention = transition.intervention
                }
                cursor = recovered.next_cursor
                if (!recovered.live && recovered.status !== 'live') break
                await new Promise((resolve) => setTimeout(resolve, 2000))
              }
            } catch {
              // Sidebar polling and a future re-open provide another recovery path.
            }
            if (pane.activeIntervention) {
              await resumeBrowserInterventionTaskUntilSettled({
                userId,
                sessionId: detail.id,
                authToken,
                locale: getLocale(),
                signal: controller.signal,
                getIntervention: () => pane.activeIntervention,
                getMessages: () => pane.messages,
                setWaitController: (waitController) => { pane.authResumeController = waitController },
                setRunning: (running) => setPaneRunning(pane, running),
                setActiveHandle: (handle) => { pane.activeStream = handle },
                clearIntervention: () => { pane.activeIntervention = null },
                onEvent: (event) => {
                  store.applyEvent(event)
                  applyAssistantContentEvent(assistant, event)
                  const transition = browserInterventionTransition(event)
                  if (transition.kind === 'cleared') pane.activeIntervention = null
                  if (transition.kind === 'activated') pane.activeIntervention = transition.intervention
                },
                onMessageId: (messageId) => { assistant.message_id = messageId },
              })
            }
          } finally {
            if (pane.abortController === controller) pane.abortController = null
            pane.activeAssistantMessageId = null
            setPaneRunning(pane, false)
            await refreshAfterRun(callbacks, pane.sessionId)
          }
        })()
      }
    }
    return pane
  }

function removeSession(sessionId: string) {
  const pane = findPaneBySessionId(sessionId)
  if (pane) stopPaneLiveStream(pane)
  pane?.authResumeController?.abort()
  state.panes = state.panes.filter((item) => item.sessionId !== sessionId)
  clearUnread(sessionId)
  if (currentSessionId.value === sessionId) {
    startLocalSession()
  }
}

  function sessionIsRunning(sessionId: string) {
    return runningSessionIds.value.has(sessionId)
  }

  function sessionIsUnread(sessionId: string) {
    return unreadSessionIdSet.value.has(sessionId)
  }

  function clearPaneIntervention(key: string) {
    const pane = findPaneByKey(key)
    if (pane) pane.activeIntervention = null
  }

  function setPanePreviewExpanded(_key: string, _expanded: boolean) {
    // Kept as an API boundary for future sidecar persistence; current expansion
    // remains local to ChatWindow because it is visual-only state.
  }

  /**
   * Renderer-neutral boundary for a Runtime owned by the desktop main process.
   * It deliberately reuses the authoritative message and V3 execution stores;
   * local Code must not grow a second chat/timeline implementation.
   */
  function beginExternalTurn(key: string, text: string, sessionId: string): ExternalTurnHandle {
    const pane = findPaneByKey(key)
    if (!pane) throw new Error('chat pane is unavailable')
    if (pane.running) throw new Error('chat pane already has an active turn')
    resolvePaneSession(pane, sessionId, callbacks)
    pane.executionLocation = 'desktop'
    pane.runtimePresetId = 'code'
    const user: RuntimeMessage = {
      _id: nextMessageId(), role: 'user', content: text, created_at: new Date().toISOString(),
    }
    const assistant: RuntimeMessage = { _id: nextMessageId(), role: 'assistant', content: '' }
    pane.messages.push(user, assistant)
    pane.activeAssistantMessageId = assistant._id || null
    ensureExecV3(assistant).reset()
    resetPanePreview(pane)
    setPaneRunning(pane, true)
    return {
      pane,
      assistant,
      apply(event: ExecutionEventV3) {
        if (!isExecutionEventV3(event)) return false
        const store = ensureExecV3(assistant)
        const before = store.state.rawEvents.length
        store.applyEvent(event)
        if (store.state.rawEvents.length === before) return false
        applyAssistantContentEvent(assistant, event)
        return true
      },
      finish() {
        pane.activeAssistantMessageId = null
        setPaneRunning(pane, false)
        void refreshAfterRun(callbacks, pane.sessionId)
      },
      setCodeChanges(changes: DshTaskChangeSet) {
        const target = pane.messages.find(message => message._id === assistant._id)
        if (target) target._codeChanges = changes
      },
    }
  }

  return {
    panes,
    activeChatKey,
    activeChatPane,
    currentSessionId,
    runningSessionIds,
    unreadSessionIdSet,
    reset,
    startLocalSession,
    selectSession,
    removeSession,
    markAccessLost,
    notifyMembersChanged,
    membersRevisionFor,
    sessionIsRunning,
    sessionIsUnread,
    clearUnread,
    clearPaneIntervention,
    setPanePreviewExpanded,
    beginExternalTurn,
    sendMessage: (key: string, input: SendInput) => sendMessage(key, input, callbacks),
    stopGeneration,
  }
}
