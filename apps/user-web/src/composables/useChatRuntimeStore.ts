import { computed, reactive, ref } from 'vue'
import { fetchOrgBilling } from '../api/auth'
import { uploadChatDocument, uploadChatImage, type UploadedDocument, type UploadedImage } from '../api/chat'
import { getSession, type ChatMessage, type SessionDetail } from '../api/sessions'
import { cancelChat, fetchChatMessageEvents, startChatStream, type ChatStreamHandle } from './useChatStream'
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
  codeProject: { workspace_id: string; git_branch: string; worktree: boolean } | null
}

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

const state = reactive({
  panes: [] as ChatRuntimePane[],
  activeKey: '',
  unreadSessionIds: new Set<string>(),
})

let localSeq = 0
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
    const msg = ensureMessageId({ ...(item as RuntimeMessage), role, content: item.content || '' })
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
    codeProject: null,
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

  state.panes = state.panes.filter((pane) => mustKeep.has(pane.key) || keepBySession.has(pane.key))
}

function clearUnread(sessionId: string | null) {
  if (!sessionId || !state.unreadSessionIds.has(sessionId)) return
  const next = new Set(state.unreadSessionIds)
  next.delete(sessionId)
  state.unreadSessionIds = next
}

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
    keeper.lastActivatedAt = Math.max(keeper.lastActivatedAt, removed.lastActivatedAt)
    if (!keeper.messages.length && removed.messages.length) keeper.messages = removed.messages
    if (!keeper.activeStream && removed.activeStream) keeper.activeStream = removed.activeStream
    if (!keeper.abortController && removed.abortController) keeper.abortController = removed.abortController
    if (!keeper.activeAssistantMessageId && removed.activeAssistantMessageId) keeper.activeAssistantMessageId = removed.activeAssistantMessageId
    if (!keeper.activeIntervention && removed.activeIntervention) keeper.activeIntervention = removed.activeIntervention
    if (!keeper.authResumeController && removed.authResumeController) keeper.authResumeController = removed.authResumeController
    if (state.activeKey === removed.key) state.activeKey = keeper.key
    state.panes = state.panes.filter((item) => item !== removed)
    callbacks.onSessionResolved?.(sessionId)
    return
  }
  pane.sessionId = sessionId
  callbacks.onSessionResolved?.(sessionId)
}

function ensureExecV3(msg: RuntimeMessage): ExecutionStoreV3 {
  return ensureMessageExecutionV3(msg)
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
  let uploadedImages: UploadedImage[] = []
  let uploadedDocuments: RuntimeDocumentInfo[] = []
  try {
    const quota = await fetchOrgBilling(input.authToken)
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

  const userMessage: RuntimeMessage = {
    _id: nextMessageId(),
    role: 'user',
    content: text,
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
    const store = ensureExecV3(msg)
    const before = store.state.rawEvents.length
    store.applyEvent(ev)
    if (
      options.fromBackend &&
      (ev.type === 'run.completed' || ev.type === 'run.failed' || ev.type === 'run.cancelled')
    ) {
      backendTerminalReceived = true
    }
    const accepted = store.state.rawEvents.length > before
    if (accepted && options.fromBackend) {
      const sequence = Number(ev.stream_seq_end || ev.stream_seq || 0)
      backendEventCursor = sequence > 0 ? Math.max(backendEventCursor, sequence) : backendEventCursor + 1
    }
    if (!accepted) return
    applyAssistantContentEvent(msg, ev)
    const transition = browserInterventionTransition(ev)
    if (transition.kind === 'cleared') pane.activeIntervention = null
    if (transition.kind === 'activated') pane.activeIntervention = transition.intervention
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
        onSessionId: (sid) => {
          assistantMsg._backendSid = sid
          resolvePaneSession(pane, sid, callbacks)
        },
        onMessageId: (mid) => {
          assistantMsg.message_id = mid
        },
      },
    )
    activeHandle = handle
    pane.activeStream = handle
    ctrl.signal.addEventListener('abort', () => handle.abort())
    await handle.done
    if (!ctrl.signal.aborted && !backendTerminalReceived) {
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
    if (error?.name !== 'AbortError') {
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
  if (!pane) return
  pane.authResumeController?.abort()
  pane.authResumeController = null
  const handle = pane.activeStream
  const activeAssistant =
    (pane.activeAssistantMessageId ? pane.messages.find((m) => m._id === pane.activeAssistantMessageId) : null) ||
    [...pane.messages].reverse().find((m) => m.role === 'assistant')
  const backendSessionId = handle?.sessionId || activeAssistant?._backendSid || pane.sessionId || ''
  if (activeAssistant) {
    if (!String(activeAssistant.content || '').trim()) {
      activeAssistant.content = t('ui.generation_stopped')
    }
    const cancelEventId = 'cancel_' + Math.random().toString(36).slice(2)
    ensureExecV3(activeAssistant).applyEvent({
      v: 3,
      event_id: cancelEventId,
      id: cancelEventId,
      ts: Date.now(),
      type: 'run.cancelled',
      revision: 1,
      payload: {
        reason: 'user_cancelled',
        message: t('ui.generation_stopped'),
      },
    } as ExecutionEventV3)
  }
  if (backendSessionId) {
    await Promise.race([
      cancelChat(backendSessionId, pane.activeAuthToken),
      new Promise<boolean>((resolve) => setTimeout(() => resolve(false), 1200)),
    ])
  }
  handle?.abort()
  pane.abortController?.abort()
  pane.activeStream = null
  pane.abortController = null
  setPaneRunning(pane, false)
}

export function useChatRuntimeStore(callbacks: RuntimeCallbacks = {}) {
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
      setActivePane(existing)
      return existing
    }
    const detail: SessionDetail = await getSession(sessionId, userId, mainId, authToken)
    const pane = createPane({
      key: `session_${detail.id}`,
      sessionId: detail.id,
      messages: detail.messages || [],
    })
    pane.executionLocation = detail.execution_location || 'server'
    pane.runtimePresetId = detail.runtime_preset_id || 'askai-enterprise'
    pane.codeProject = detail.code_project || null
    state.panes = [...state.panes, pane]
    setActivePane(pane)
    pruneInactivePanes()
    if (detail.active_run?.message_id && authToken) {
      const assistant = [...pane.messages].reverse().find(
        (item) => item.role === 'assistant' && item.message_id === detail.active_run?.message_id,
      )
      if (assistant) {
        const restoredStore = ensureExecV3(assistant)
        pane.activeIntervention = normalizeBrowserIntervention(restoredStore.state.intervention)
        const controller = new AbortController()
        pane.abortController = controller
        pane.activeAssistantMessageId = assistant._id || null
        setPaneRunning(pane, true)
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
    findPaneBySessionId(sessionId)?.authResumeController?.abort()
    state.panes = state.panes.filter((pane) => pane.sessionId !== sessionId)
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
