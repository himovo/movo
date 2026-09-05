<script setup lang="ts">
import { computed, defineAsyncComponent, ref, nextTick, onMounted, onUpdated, onBeforeUnmount, watch } from 'vue'
import { renderDocument, renderPresentationPptx, signDocument, fetchBlueprintJson } from '../api/documents'
import BrowserWorkspace from './browser/BrowserWorkspace.vue'
import LocalBrowserInterventionPrompt from './execution/LocalBrowserInterventionPrompt.vue'
import ToolApprovalPrompt from './execution/ToolApprovalPrompt.vue'
import DshCodeApprovalList from './code/DshCodeApprovalList.vue'
import CodeHistoryReadOnlyNotice from './code/CodeHistoryReadOnlyNotice.vue'
import CodeTaskChangeCard from './code/CodeTaskChangeCard.vue'
import CodeDraftContextBar from './code/CodeDraftContextBar.vue'
import ChatComposer from './chat/ChatComposer.vue'
import AssistantMarkdown from './chat/AssistantMarkdown.vue'
import type { PendingDocument } from './chat/types'
import { useAuthoritativeMessages } from './chat/useAuthoritativeMessages'
import { promptGuideCategories, promptGuideUiIcons, type PromptGuideConfigTarget, type PromptGuideItem } from './chat/promptGuideConfig'
import PresentationEditor from './PresentationEditor.vue'
import ExecutionViewV3 from '../features/execution-v3/components/ExecutionViewV3.vue'
import ArtifactList from './execution/ArtifactList.vue'
import EvidenceDrawer from './execution/EvidenceDrawer.vue'
import KnowledgeSourceViewer from './execution/KnowledgeSourceViewer.vue'
import UserMessageActions from './chat/UserMessageActions.vue'
import type { ArtifactItem, EvidenceBundleItem, EvidenceSourceItem } from '../features/execution-v3/domain/delivery'
import { evidenceSourceStats } from '../features/execution-v3/domain/evidenceSourceGroups'
import { resolvePermission } from '../composables/useChatStream'
import { useDshToolApprovals } from '../composables/useDshToolApprovals'
import { mergeEvidenceBundles } from '../composables/evidenceBundles'
import { t, useLocale } from '../composables/i18n'
import { formatAppTime } from '../composables/appTimezone'
import { useChatModels } from '../composables/useChatModels'
import { useBrowserWorkspace } from '../composables/browser/useBrowserWorkspace'
import type { ExecutionStoreV3 } from '../features/execution-v3/stores/executionStore'
import { ensureMessageExecutionV3 } from '../features/execution-v3/stores/messageExecution'
import { downloadResourceUrl, openPreviewResource, saveBlobDownload } from '../utils/desktopResources'
import { normalizeAssistantContent, renderAssistantMarkdown, sanitizeMermaid } from '../utils/assistantMarkdown'
import type { DshCodeSession, DshExecutionEvent, DshPendingApproval, DshTaskChangeSet, DshWorkspace } from '../platform/types'
import { capabilities } from '../platform'
import type { DesktopToolLauncherKind, DesktopToolTab } from './desktop/desktopToolTabs'
import type { AgentPolicySnapshot } from '../api/auth'
import { resolveArtifactIcon, resolveArtifactPresentation } from '../registries'
import { resolveArtifactKind } from '../features/execution-v3/domain/artifactKind'
import { authenticatedJsonHeaders } from '../api/authHeaders'

type ProjectPanelMode = 'changes' | 'files' | 'terminal' | 'file' | 'diff'
const ProjectWorkspacePanel = defineAsyncComponent(() => import('./code/ProjectWorkspacePanel.vue'))

// Architecture boundary:
// ChatWindow is the chat shell only. New chat-facing capabilities must be
// integrated through focused child components or composables, then wired here
// through props/events/slots. Do not add feature-specific business logic,
// static configuration, upload/stream orchestration, or large UI blocks directly
// to this file.

const props = defineProps<{
  initialMessage?: string
  initialMessages?: Message[]
  sessionId?: string
  userId?: string
  mainId?: string
  authToken?: string
  active: boolean
  running?: boolean
  stopping?: boolean
  codeWorkspace?: DshWorkspace | null
  codeSession?: DshCodeSession | null
  codeEvents?: DshExecutionEvent[]
  codeApprovals?: DshPendingApproval[]
  codeApprovalBusy?: Record<string, boolean>
  codeError?: string
  codeWorkspaceBusy?: boolean
  codeWorktree?: boolean
  codeSourceRef?: string
  codeHistoryReadOnly?: boolean
  codeHistoryLocation?: 'desktop' | 'remote_sandbox'
  codeHistoryProject?: { workspace_id: string; git_branch: string; worktree: boolean } | null
  desktopWorkspaceRequest?: number
  desktopBrowserRequest?: number
  desktopToolTabs?: DesktopToolTab[]
  desktopActiveTool?: string | null
  desktopAvailableTools?: DesktopToolLauncherKind[]
  desktopCodeReviewPath?: string
  desktopCodeReviewChanges?: DshTaskChangeSet | null
  desktopCodeFilePath?: string
  agentPolicy?: AgentPolicySnapshot
  activeIntervention?: {
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
    handoff?: import('../composables/browser/useBrowserWorkspace').BrowserAssistanceHandoff
  } | null
}>()

const { locale } = useLocale()
const allowCode = computed(() => props.agentPolicy?.capabilities.code_generation !== false)
const allowBrowser = computed(() => props.agentPolicy?.capabilities.browser_automation !== false)
const allowKnowledge = computed(() => props.agentPolicy?.capabilities.internal_knowledge !== false)
const allowContent = computed(() => props.agentPolicy?.capabilities.content_generation !== false)
const allowSkills = computed(() => {
  const policy = props.agentPolicy
  return !policy || policy.skillAccessMode === 'all' || policy.skillIds.length > 0
})
const allowTools = computed(() => {
  const policy = props.agentPolicy
  return !policy || policy.toolAccessMode === 'all' || policy.toolIds.length > 0
})
const emit = defineEmits<{
  (e: 'open-skills'): void
  (e: 'open-tools'): void
  (e: 'send', payload: { text: string; images: File[]; documents: PendingDocument[]; knowledgeQaEnabled: boolean; selectedSkillId?: string; modelId?: string }): void
  (e: 'stop'): void
  (e: 'clear-intervention'): void
  (e: 'approval-decided'): void
  (e: 'choose-code-workspace', modelId?: string): void
  (e: 'clear-code-workspace'): void
  (e: 'code-worktree', enabled: boolean): void
  (e: 'code-source-ref', fullRef: string): void
  (e: 'code-branch-updated', branch: string): void
  (e: 'code-approval', approvalId: string, decision: 'approved' | 'rejected', scope: 'once' | 'session'): void
  (e: 'close-code-panel'): void
  (e: 'select-desktop-tool', id: string): void
  (e: 'close-desktop-tool', id: string): void
  (e: 'open-desktop-tool', kind: DesktopToolLauncherKind): void
  (e: 'open-desktop-file-tab', path: string): void
  (e: 'open-desktop-diff-tab', path: string, changes?: DshTaskChangeSet): void
  (e: 'code-workspace-change'): void
  (e: 'review-code-changes', changes: DshTaskChangeSet, path?: string): void
  (e: 'open-code-file', path: string): void
  (e: 'schedule-message', payload: { prompt: string; sessionId?: string }): void
}>()

interface Message {
  role: 'user' | 'assistant'
  content: string
  _id?: string
  _execV3?: ExecutionStoreV3
  /** Backend chat session id captured from streaming response header */
  _backendSid?: string
  /** Stable id for this assistant turn; used to bind persisted exec log */
  message_id?: string
  /** Persisted V3 events returned by GET /sessions/{id} for replay. */
  execution_events?: unknown[]
  trigger_source?: string
  scheduled_job_id?: string
  scheduled_run_id?: string
  created_at?: string
  _codeChanges?: DshTaskChangeSet
  evidence_bundles?: any[]
  evidenceBundles?: any[]
  documents?: DocumentInfo[]
  images?: ImageInfo[]
  // Legacy fields kept for compatibility with persisted messages but no
  // longer driven by the live stream.
  progress?: { content: string; timestamp?: string; kind?: string; url?: string }[]
  currentStatus?: string
  plan?: any
}

function ensureExecV3(msg: Message): ExecutionStoreV3 {
  return ensureMessageExecutionV3(msg)
}

function artifactStore(msg: Message): ExecutionStoreV3 { return ensureExecV3(msg) }

const activeEvidenceBundle = ref<EvidenceBundleItem | null>(null)
const activeKnowledgeSourceBundle = ref<EvidenceBundleItem | null>(null)
const evidenceDrawerOpen = ref(false)
const knowledgeSourceViewerOpen = ref(false)

function latestEvidenceBundle(msg: Message): EvidenceBundleItem | null {
  const bundles = ensureExecV3(msg).state.evidenceBundles
  return mergeEvidenceBundles(bundles)
}

function shouldShowEvidenceTrigger(idx: number, msg: Message): boolean {
  if (!latestEvidenceBundle(msg)) return false
  if (!String(msg.content || '').trim()) return false
  if (isAssistantGenerating(idx, msg)) return false
  return true
}

function evidenceTriggerText(bundle: EvidenceBundleItem): string {
  const stats = evidenceSourceStats(bundle.sources)
  if (locale.value === 'zh') {
    if (stats.fragments) return `查看依据 · ${stats.total} 个来源 / ${stats.fragments} 个片段`
    return stats.total ? `查看依据 · ${stats.total} 个来源` : '查看依据'
  }
  if (stats.fragments) return `View sources · ${stats.total} sources / ${stats.fragments} excerpts`
  return stats.total ? `View sources · ${stats.total}` : 'View sources'
}

function evidenceTriggerTextForMessage(msg: Message): string {
  const bundle = latestEvidenceBundle(msg)
  return bundle ? evidenceTriggerText(bundle) : t('evidence.view')
}

function openEvidenceDrawer(bundle: EvidenceBundleItem) {
  activeEvidenceBundle.value = bundle
  evidenceDrawerOpen.value = true
}

function openLatestEvidenceDrawer(msg: Message) {
  const bundle = latestEvidenceBundle(msg)
  if (bundle) openEvidenceDrawer(bundle)
}

function closeEvidenceDrawer() {
  evidenceDrawerOpen.value = false
}

function closeKnowledgeSourceViewer() {
  knowledgeSourceViewerOpen.value = false
  activeKnowledgeSourceBundle.value = null
}

function openKnowledgeSourceFromDrawer(source: EvidenceSourceItem) {
  const bundle = activeEvidenceBundle.value
  if (!bundle) return
  if (!source.document_id || !source.chunk_id) return
  activeKnowledgeSourceBundle.value = {
    ...bundle,
    id: `${bundle.id}_${source.id || source.chunk_id}_${Date.now()}`,
    sources: bundle.sources.filter((item) => (
      item.document_id === source.document_id && Boolean(item.chunk_id)
    )),
  }
  knowledgeSourceViewerOpen.value = true
}

interface DocumentInfo {
  id?: string
  type: 'pdf' | 'doc' | 'docx' | 'xls' | 'xlsx' | 'ppt' | 'pptx' | 'md' | 'html' | 'presentation_preview_bundle' | 'generic'
  url: string
  filename?: string
  title?: string
  object_path?: string
  signed_url?: string
  content_type?: string
  size?: number
  bundle?: Record<string, any>
}

interface ImageInfo {
  object_path?: string
  url?: string
  signed_url?: string
  filename?: string
  content_type?: string
  size?: number
}

const defaultGreeting = props.initialMessage || 'Hello! I am your AI Agent. How can I help you today?'

// The runtime store is the sole message owner. Keeping a local copied array
// caused new-session runs to remain on the welcome screen while the parent was
// already streaming events into a different array.
const messages = useAuthoritativeMessages<Message>(() => props.initialMessages)
const displayMessages = computed(() => {
  const result: Message[] = []
  const greeting = defaultGreeting.trim()
  let hasGreeting = false
  for (const msg of messages.value) {
    const content = msg.content?.trim() || ''
    if (msg.role === 'assistant' && content === greeting) {
      if (hasGreeting) continue
      hasGreeting = true
    }
    const prev = result[result.length - 1]
    if (
      prev &&
      prev.role === msg.role &&
      prev.role === 'assistant' &&
      (prev.content?.trim() || '') === content
    ) {
      continue
    }
    result.push(msg)
  }
  return result
})

const imagePreviewOpen = ref(false)
const imagePreviewSrc = ref('')
const imagePreviewAlt = ref('preview')
const isLoading = ref(false)
watch(
  () => props.running,
  (running) => {
    isLoading.value = Boolean(running)
  },
  { immediate: true },
)
const messagesContainer = ref<HTMLElement | null>(null)
const composerContainer = ref<HTMLElement | null>(null)
const composerRef = ref<InstanceType<typeof ChatComposer> | null>(null)
const msgElements = ref<Record<string, HTMLElement>>({})
const showScrollButton = ref(false)
const isProgrammaticScroll = ref(false)
const activeDocument = ref<DocumentInfo | null>(null)
const documentEditorOpen = ref(false)
// Presentation editor (Fabric.js)
const presentationEditorOpen = ref(false)
const presentationBlueprint = ref<any>(null)

const {
  chatModels,
  selectedModelId,
  modelLoadError,
  modelSelectorLabel,
  loadChatModels,
  selectChatModel,
} = useChatModels({
  getMainId: () => props.mainId || 'default',
  getLocale: () => locale.value,
})
watch(() => props.desktopWorkspaceRequest, (value, previous) => {
  if (props.active && value && value !== previous) emit('choose-code-workspace', selectedModelId.value)
})
watch(() => props.desktopBrowserRequest, (value, previous) => {
  if (props.active && value && value !== previous) isPreviewExpanded.value = true
})
const presentationBlueprintPath = ref('')
const presentationEditorMsg = ref<Message | null>(null)
const documentEditorContent = ref('')
const documentEditorLoading = ref(false)
const documentEditorMessageIndex = ref<number | null>(null)
const {
  activeIntervention,
  isPreviewExpanded,
  openForIntervention: openBrowserForLogin,
  completeLocalIntervention: handleLocalInterventionDone,
  reset: resetBrowserWorkspace,
} = useBrowserWorkspace({
  getUserId: () => props.userId,
  getSessionId: () => props.sessionId,
  getIntervention: () => props.activeIntervention,
  onClearIntervention: () => emit('clear-intervention'),
})
const desktopActiveTab = computed(() => (props.desktopToolTabs || []).find(tab => tab.id === props.desktopActiveTool) || null)
watch(() => desktopActiveTab.value?.kind, kind => {
  isPreviewExpanded.value = kind === 'browser'
})
const desktopCodePanelMode = computed<ProjectPanelMode | null>(() => {
  const mode = desktopActiveTab.value?.kind
  return mode === 'changes' || mode === 'files' || mode === 'terminal' || mode === 'file' || mode === 'diff' ? mode : null
})
const hasDesktopCodeTabs = computed(() => (props.desktopToolTabs || []).some(tab => tab.kind !== 'browser'))
function openBrowserForIntervention(): void {
  openBrowserForLogin()
  emit('open-desktop-tool', 'browser')
}
const debugEnabled = typeof window !== 'undefined' && window.location.search.includes('debug=1')
const stickyDebugEnabled = typeof window !== 'undefined' && window.location.search.includes('sticky_debug=1')

// Sticky-top state management
const stickyState = ref<'UNLOCKED' | 'LOCKED' | 'MANUAL_SCROLL'>('UNLOCKED')
const stickyUserMsgId = ref<string | null>(null)
const stickyAssistantMsgId = ref<string | null>(null)
const stickySpacerHeight = ref(0)
const scrollLockUntil = ref(0)
const stickyNeedsInitialAlign = ref(false)
const stickyHoldUntil = ref(0)
const userScrollIntentUntil = ref(0)
let scrollTimeout: ReturnType<typeof setTimeout> | null = null
let stickyFollowRaf: number | null = null
let layoutRaf: number | null = null
let layoutObserver: ResizeObserver | null = null
const stickyTurnMinHeightPx = ref(0)
const isNewSessionView = computed(() => displayMessages.value.length === 0)

const activePromptGuideKey = ref<string | null>(null)
const promptGuideNotice = ref<{
  title: string
  description: string
  target: PromptGuideConfigTarget
} | null>(null)
let promptGuideCloseTimer: ReturnType<typeof setTimeout> | null = null

const visiblePromptGuideCategories = computed(() => promptGuideCategories.filter((category) => {
  if (category.key === 'content') return allowContent.value
  if (category.key === 'internal') return allowKnowledge.value
  if (category.key === 'systems') return allowTools.value
  return true
}))
const activePromptGuideCategory = computed(() => (
  visiblePromptGuideCategories.value.find((item) => item.key === activePromptGuideKey.value) || null
))

function selectPromptGuideCategory(key: string) {
  cancelPromptGuideClose()
  activePromptGuideKey.value = key
  const category = visiblePromptGuideCategories.value.find((item) => item.key === key)
  if (!category) return
  promptGuideNotice.value = category?.requiresConfig
    ? {
      title: category.configTitle || '需要先配置',
      description: category.configDescription || '配置完成后才能稳定使用这类能力。',
      target: category.configTarget || 'tools',
    }
    : null
}

function closePromptGuide() {
  cancelPromptGuideClose()
  activePromptGuideKey.value = null
  promptGuideNotice.value = null
}

function cancelPromptGuideClose() {
  if (promptGuideCloseTimer) {
    clearTimeout(promptGuideCloseTimer)
    promptGuideCloseTimer = null
  }
}

function schedulePromptGuideClose() {
  cancelPromptGuideClose()
  promptGuideCloseTimer = setTimeout(() => {
    activePromptGuideKey.value = null
    promptGuideNotice.value = null
    promptGuideCloseTimer = null
  }, 220)
}

async function usePromptGuideItem(item: PromptGuideItem) {
  if (!item.available) {
    promptGuideNotice.value = {
      title: item.configTitle || t('需要先配置'),
      description: item.configDescription || t('配置完成后才能使用这个能力。'),
      target: item.configTarget || 'tools',
    }
    return
  }
  if (!item.prompt) return
  promptGuideNotice.value = null
  if (activePromptGuideCategory.value?.key === 'internal') {
    composerRef.value?.enableKnowledgeQa()
  }
  await composerRef.value?.setTextAndFocus(t(item.prompt))
}

function openPromptGuideConfig(target: PromptGuideConfigTarget) {
  if (target === 'skills') emit('open-skills')
  else emit('open-tools')
}

function stickyLog(...args: any[]) {
  if (!stickyDebugEnabled) return
  console.log('[Sticky]', ...args)
}

function markUserScrollIntent() {
  userScrollIntentUntil.value = Date.now() + 1200
}

function recomputeStickyTurnMinHeight() {
  if (layoutRaf !== null) cancelAnimationFrame(layoutRaf)
  layoutRaf = requestAnimationFrame(() => {
    layoutRaf = null
    if (!messagesContainer.value) return
    const containerTop = messagesContainer.value.getBoundingClientRect().top
    const composerHeight = composerContainer.value?.getBoundingClientRect().height || 0
    const viewportHeight = window.innerHeight || document.documentElement.clientHeight || 0
    const bottomGap = 12
    const available = Math.max(0, Math.floor(viewportHeight - containerTop - composerHeight - bottomGap))
    stickyTurnMinHeightPx.value = available
  })
}

function stopStickyFollow() {
  if (stickyFollowRaf !== null) {
    cancelAnimationFrame(stickyFollowRaf)
    stickyFollowRaf = null
  }
}

function startStickyFollow() {
  // no-op: keep for compatibility during refactor
  stopStickyFollow()
}

function findLatestUserAssistantPair(): { userId: string; assistantId: string | null } | null {
  for (let i = messages.value.length - 1; i >= 0; i -= 1) {
    const m = messages.value[i]
    if (m.role !== 'user' || !m._id) continue
    const next = messages.value[i + 1]
    const assistantId = next && next.role === 'assistant' ? (next._id || null) : null
    return { userId: m._id, assistantId }
  }
  return null
}

function activateStickyForLatestRunningTurn() {
  if (!isLoading.value) return
  const pair = findLatestUserAssistantPair()
  if (!pair?.assistantId) return
  if (stickyState.value === 'LOCKED' && stickyUserMsgId.value === pair.userId && stickyAssistantMsgId.value === pair.assistantId) {
    return
  }
  stickyState.value = 'LOCKED'
  scrollLockUntil.value = Date.now() + 1500
  stickyHoldUntil.value = Date.now() + 1200
  stickyUserMsgId.value = pair.userId
  stickyAssistantMsgId.value = pair.assistantId
  stickyNeedsInitialAlign.value = true
  nextTick(() => {
    void alignStickyAnchorWithRetry(10)
  })
}

function ensureStickyAnchorBound(): boolean {
  if (stickyState.value !== 'LOCKED') return false
  const currentUserId = stickyUserMsgId.value
  if (currentUserId && msgElements.value[currentUserId]) return true
  const pair = findLatestUserAssistantPair()
  if (!pair) return false
  stickyUserMsgId.value = pair.userId
  stickyAssistantMsgId.value = pair.assistantId
  stickyNeedsInitialAlign.value = true
  stickyLog('rebind sticky anchor', pair)
  return !!msgElements.value[pair.userId]
}

function getDocPresentation(doc: DocumentInfo) {
  return resolveArtifactPresentation({ ...doc, kind: doc.type })
}

const debugStats = computed(() => {
  const lastMessage = messages.value[messages.value.length - 1]
  const lastDisplay = displayMessages.value[displayMessages.value.length - 1]
  return {
    messagesCount: messages.value.length,
    displayCount: displayMessages.value.length,
    lastMessageContent: lastMessage?.content || '',
    lastDisplayContent: lastDisplay?.content || '',
  }
})

function toTimeLabel(value?: string) {
  return formatAppTime(value, '')
}

function isAssistantGenerating(idx: number, msg: Message): boolean {
  return !!isLoading.value && msg.role === 'assistant' && idx === displayMessages.value.length - 1
}

// Breathing dot is obsolete: the Timeline now owns the "live thinking" row
// with its own animated indicator + ticking duration, so no second spinner
// is needed. Kept as a no-op stub to avoid touching every call site.
function shouldShowBreathingLoading(_idx: number, _msg: Message): boolean {
  return false
}

function onPermissionResolve(msg: Message, requestId: string, decision: 'allow' | 'deny' | 'always_allow') {
  const sid = msg._backendSid
  if (!sid) return
  resolvePermission(sid, requestId, decision)
}

const approvalControl = useDshToolApprovals({
  messages: displayMessages,
  sessionId: () => props.sessionId,
  authToken: () => props.authToken,
  running: () => Boolean(props.running),
  onDecided: () => emit('approval-decided'),
})
const activeDshApprovals = approvalControl.active
const approvalBusy = approvalControl.busy
const approvalErrors = approvalControl.errors

function artifactToDocumentInfo(a: ArtifactItem): DocumentInfo {
  return {
    id: a.id,
    type: resolveArtifactKind(a) as DocumentInfo['type'],
    url: a.url || '',
    signed_url: a.signed_url,
    object_path: a.object_path,
    filename: a.filename,
    title: a.title,
    content_type: a.content_type,
    size: a.size,
    bundle: a.bundle,
  }
}

function normalizeDocumentType(type?: string): DocumentInfo['type'] {
  return (type === 'markdown' ? 'md' : type || 'generic') as DocumentInfo['type']
}

function documentToArtifact(doc: DocumentInfo): ArtifactItem {
  return {
    id: doc.id || doc.object_path || doc.url || `${doc.type}_${Date.now()}`,
    ts: Date.now(),
    kind: doc.type,
    url: doc.url,
    signed_url: doc.signed_url,
    object_path: doc.object_path,
    filename: doc.filename,
    title: doc.title,
    content_type: doc.content_type,
    size: doc.size,
    bundle: doc.bundle,
  }
}

function sameDocumentIdentity(a: DocumentInfo, b?: DocumentInfo | null): boolean {
  if (!b) return false
  return (
    (!!a.id && a.id === b.id) ||
    (!!a.object_path && a.object_path === b.object_path) ||
    (!!a.url && a.url === b.url) ||
    (a.type === b.type && !!a.filename && a.filename === b.filename && a.title === b.title)
  )
}

function upsertMessageDocument(msg: Message, previous: DocumentInfo | null, next: DocumentInfo) {
  if (!msg.documents) msg.documents = []
  const index = msg.documents.findIndex((doc) => sameDocumentIdentity(doc, previous) || sameDocumentIdentity(doc, next))
  if (index >= 0) {
    msg.documents[index] = { ...msg.documents[index], ...next }
  } else {
    msg.documents.push(next)
  }
}

function upsertExecutionArtifact(msg: Message, previous: DocumentInfo | null, next: DocumentInfo) {
  const store = artifactStore(msg)
  const nextArtifact = documentToArtifact(next)
  const index = store.state.artifacts.findIndex((artifact) => {
    const doc = artifactToDocumentInfo(artifact)
    return sameDocumentIdentity(doc, previous) || sameDocumentIdentity(doc, next)
  })
  if (index >= 0) {
    store.state.artifacts[index] = { ...store.state.artifacts[index], ...nextArtifact }
  } else {
    store.state.artifacts.push(nextArtifact)
  }
}

function upsertDocumentEverywhere(msg: Message, previous: DocumentInfo | null, next: DocumentInfo) {
  upsertMessageDocument(msg, previous, next)
  if (next.type !== 'md') {
    upsertExecutionArtifact(msg, previous, next)
  }
}

function findMarkdownDocument(msg: Message): DocumentInfo | null {
  const fromDocuments = (msg.documents || []).find((d) => d.type === 'md')
  if (fromDocuments) return fromDocuments
  const artifact = artifactStore(msg).state.artifacts.find((a: ArtifactItem) => {
    const kind = String(a.kind || '').toLowerCase()
    return kind === 'md' || kind === 'markdown'
  })
  return artifact ? artifactToDocumentInfo(artifact) : null
}

function toRenderableDocumentFormat(type: DocumentInfo['type']): 'pdf' | 'docx' | 'ppt' | 'pptx' | 'md' | null {
  if (type === 'pdf' || type === 'docx' || type === 'ppt' || type === 'pptx' || type === 'md') return type
  return null
}

function onArtifactOpen(a: ArtifactItem, msg: Message, idx: number) {
  return openDocumentEditor(artifactToDocumentInfo(a), msg, idx)
}
function onArtifactEditPresentation(a: ArtifactItem, msg: Message) {
  return openPresentationEditor(artifactToDocumentInfo(a), msg)
}
function onArtifactExportPresentation(a: ArtifactItem, msg: Message) {
  return confirmPresentationPreview(artifactToDocumentInfo(a), msg)
}
function onArtifactPreviewHtml(a: ArtifactItem) {
  return openHtmlPreview(artifactToDocumentInfo(a))
}
function onArtifactDownload(a: ArtifactItem) {
  return downloadDocument(artifactToDocumentInfo(a))
}


function getDisplayDocuments(docs?: DocumentInfo[]) {
  const list = docs || []
  const hasPreviewBundle = list.some((d) => d.type === 'presentation_preview_bundle')
  if (hasPreviewBundle) {
    return list.filter((d) => d.type === 'presentation_preview_bundle')
  }
  const hasNonMd = list.some((d) => d.type !== 'md')
  if (hasNonMd) {
    return list.filter((d) => d.type !== 'md')
  }
  return list
}

function openImagePreview(src?: string, alt?: string) {
  if (!src) return
  imagePreviewSrc.value = src
  imagePreviewAlt.value = alt || 'preview'
  imagePreviewOpen.value = true
}

function closeImagePreview() {
  imagePreviewOpen.value = false
  imagePreviewSrc.value = ''
}

watch(
  () => debugStats.value,
  (stats) => {
    if (!debugEnabled) return
    console.log('[chat-debug]', stats)
  },
  { deep: true }
)

watch(
  () => {
    const lastAssistant = [...messages.value].reverse().find((m) => m.role === 'assistant')
    return lastAssistant?.content || ''
  },
  (content) => {
    if (!debugEnabled || !content) return
    const normalized = normalizeAssistantContent(content)
    const html = renderAssistantMarkdown(content)
    console.log('[chat-debug] assistant-raw', JSON.stringify(content))
    console.log('[chat-debug] assistant-normalized', JSON.stringify(normalized))
    console.log('[chat-debug] assistant-html', html)
  }
)

// Watch AI content changes to update spacer height
watch(
  () => {
    if (stickyState.value !== 'LOCKED' || !stickyAssistantMsgId.value) return null
    const aiMsg = messages.value.find((m) => m._id === stickyAssistantMsgId.value)
    return aiMsg?.content || ''
  },
  () => {
    if (stickyState.value === 'LOCKED') {
      nextTick(() => updateSpacerHeight())
    }
  }
)

async function openDocumentEditor(doc: DocumentInfo, msg: Message, _renderIndex: number) {
  if (doc.type === 'presentation_preview_bundle') {
    await openPresentationEditor(doc, msg)
    return
  }
  if (doc.type === 'html') {
    const targetUrl = await resolveDocumentOpenUrl(doc)
    if (targetUrl) {
      await openPreviewResource(targetUrl)
    }
    return
  }
  const msgIndex = messages.value.findIndex((m) => m._id === msg._id && m.role === msg.role)
  if (msgIndex < 0) return
  activeDocument.value = doc
  documentEditorContent.value = ''
  const mdDoc = doc.type === 'md'
    ? doc
    : findMarkdownDocument(msg)
  if (mdDoc?.object_path) {
    try {
      if (debugEnabled) {
        console.log('[doc-editor] fetching markdown', mdDoc.object_path)
      }
      const resp = await fetch('/askai-api/api/documents/fetch', {
        method: 'POST',
        headers: authenticatedJsonHeaders(),
        body: JSON.stringify({
          user_id: props.userId || 'anonymous',
          object_path: mdDoc.object_path,
        }),
      })
      if (debugEnabled) {
        console.log('[doc-editor] fetch status', resp.status)
      }
      if (resp.ok) {
        documentEditorContent.value = await resp.text()
        if (debugEnabled) {
          console.log('[doc-editor] markdown length', documentEditorContent.value.length)
        }
      }
    } catch {
      // ignore and fallback to message content
    }
  }
  if (!documentEditorContent.value) {
    documentEditorContent.value = msg.content || ''
  }
  if (documentEditorContent.value) {
    try {
      const renewResp = await fetch('/askai-api/api/documents/refresh-markdown-urls', {
        method: 'POST',
        headers: authenticatedJsonHeaders(),
        body: JSON.stringify({
          user_id: props.userId || 'anonymous',
          content: documentEditorContent.value,
        }),
      })
      if (renewResp.ok) {
        documentEditorContent.value = await renewResp.text()
      }
    } catch {
      // ignore and keep original content
    }
  }
  documentEditorMessageIndex.value = msgIndex
  documentEditorOpen.value = true
}

function closeDocumentEditor() {
  documentEditorOpen.value = false
  activeDocument.value = null
  documentEditorMessageIndex.value = null
}

async function openPresentationEditor(doc: DocumentInfo, msg: Message) {
  const blueprintPath = String(
    doc.bundle?.preview_metadata?.blueprint_artifact_path ||
    doc.bundle?.deck_ir_artifact?.object_path ||
    ''
  ).trim()
  if (!blueprintPath) {
    // Fallback: open HTML preview in new tab
    const targetUrl = await resolveDocumentOpenUrl(doc)
    if (targetUrl) await openPreviewResource(targetUrl)
    return
  }
  try {
    const resp = await fetch('/askai-api/api/documents/fetch', {
      method: 'POST',
      headers: authenticatedJsonHeaders(),
      body: JSON.stringify({
        user_id: props.userId || 'anonymous',
        object_path: blueprintPath,
      }),
    })
    if (!resp.ok) throw new Error('fetch failed')
    const text = await resp.text()
    presentationBlueprint.value = JSON.parse(text)
    presentationBlueprintPath.value = blueprintPath
    presentationEditorMsg.value = msg
    presentationEditorOpen.value = true
  } catch (err) {
    console.error('Failed to load blueprint:', err)
    // Fallback to HTML preview
    const targetUrl = await resolveDocumentOpenUrl(doc)
    if (targetUrl) await openPreviewResource(targetUrl)
  }
}

async function openHtmlPreview(doc: DocumentInfo) {
  const targetUrl = await resolveDocumentOpenUrl(doc)
  if (targetUrl) await openPreviewResource(targetUrl)
}

function closePresentationEditor() {
  presentationEditorOpen.value = false
  presentationBlueprint.value = null
  presentationBlueprintPath.value = ''
  presentationEditorMsg.value = null
}

function onPresentationExported(result: any) {
  if (!result || !presentationEditorMsg.value) return
  const msg = presentationEditorMsg.value
  if (!msg.documents) msg.documents = []
  const exists = msg.documents.some((item) =>
    (result.object_path && item.object_path === result.object_path) ||
    (result.url && item.url === result.url)
  )
  if (!exists) {
    msg.documents.push(result as DocumentInfo)
  }
}

function getDocumentObjectPath(doc: DocumentInfo): string {
  return String(
    doc.object_path ||
    doc.bundle?.html_preview?.object_path ||
    ''
  ).trim()
}

async function resolveDocumentOpenUrl(doc: DocumentInfo): Promise<string> {
  const objectPath = getDocumentObjectPath(doc)
  if (objectPath) {
    try {
      const result = await signDocument({
        user_id: props.userId || 'anonymous',
        object_path: objectPath,
      })
      const signed = String(result?.url || '').trim()
      if (signed) {
        doc.signed_url = signed
        if (doc.type === 'presentation_preview_bundle' && doc.bundle?.html_preview) {
          doc.bundle.html_preview.url = signed
        }
        return signed
      }
    } catch {
      // fallback to existing url
    }
  }
  return String(doc.signed_url || doc.url || doc.bundle?.html_preview?.url || '').trim()
}

async function downloadDocument(doc: DocumentInfo) {
  if (doc.type === 'presentation_preview_bundle' || doc.type === 'html') {
    const targetUrl = await resolveDocumentOpenUrl(doc)
    if (targetUrl) {
      await openPreviewResource(targetUrl)
    }
    return
  }
  if (!doc.url && !doc.object_path) return
  const filename = doc.filename || doc.title || 'document'
  if (doc.object_path) {
    try {
      const resp = await fetch('/askai-api/api/documents/fetch', {
        method: 'POST',
        headers: authenticatedJsonHeaders(),
        body: JSON.stringify({
          user_id: props.userId || 'anonymous',
          object_path: doc.object_path,
        }),
      })
      if (resp.ok) {
        const blob = await resp.blob()
        await saveBlobDownload(blob, filename)
        return
      }
    } catch {
      // fallback to existing url
    }
  }
  if (doc.url) {
    await downloadResourceUrl(doc.url, filename)
  }
}

async function confirmPresentationPreview(doc: DocumentInfo, msg: Message) {
  const blueprintPath = String(
    doc.bundle?.preview_metadata?.blueprint_artifact_path ||
    doc.bundle?.deck_ir_artifact?.object_path ||
    ''
  ).trim()

  let result: any = null
  if (blueprintPath) {
    result = await renderPresentationPptx({
      user_id: props.userId || 'anonymous',
      blueprint_object_path: blueprintPath,
      filename: `${doc.title || 'presentation'}.pptx`,
      title: doc.title || 'PPT',
    })
  } else {
    // No blueprint available — nothing to render.
    return
  }

  if (!result) return
  if (!msg.documents) msg.documents = []
  const exists = msg.documents.some((item) =>
    (result.object_path && item.object_path === result.object_path) ||
    (result.url && item.url === result.url)
  )
  if (!exists) {
    msg.documents.push(result as DocumentInfo)
  }
}

async function regenerateDocument() {
  if (!activeDocument.value) return
  if (documentEditorMessageIndex.value === null) return
  const content = documentEditorContent.value.trim()
  if (!content) return
  documentEditorLoading.value = true
  try {
    const previousDocument = { ...activeDocument.value }
    const msg = messages.value[documentEditorMessageIndex.value]
    if (!msg) return
    const renderFormat = toRenderableDocumentFormat(activeDocument.value.type)
    if (!renderFormat) return
    const previousMarkdown = activeDocument.value.type !== 'md' ? findMarkdownDocument(msg) : null
    const result = await renderDocument({
      user_id: props.userId || 'anonymous',
      content,
      format: renderFormat,
      filename: activeDocument.value.filename,
      title: activeDocument.value.title,
    })
    if (result) {
      let nextMarkdown: DocumentInfo | null = null
      if (activeDocument.value.type !== 'md') {
        const markdownResult = await renderDocument({
          user_id: props.userId || 'anonymous',
          content,
          format: 'md',
          filename: `${activeDocument.value.title || activeDocument.value.filename || 'document'}.md`,
          title: activeDocument.value.title,
        })
        if (!markdownResult?.object_path) throw new Error('markdown render failed')
        nextMarkdown = {
          ...(previousMarkdown || {}),
          ...markdownResult,
          id: markdownResult.object_path || markdownResult.url || previousMarkdown?.id,
          type: 'md',
          signed_url: markdownResult.url || '',
          url: markdownResult.url || '',
        } as DocumentInfo
      }
      const nextDocument = {
        ...activeDocument.value,
        ...result,
        id: result.object_path || result.url || activeDocument.value.id,
        type: normalizeDocumentType(result.type || activeDocument.value.type),
        signed_url: result.url || '',
        url: result.url || '',
      } as DocumentInfo
      upsertDocumentEverywhere(msg, previousDocument, nextDocument)
      activeDocument.value = nextDocument
      if (nextMarkdown) {
        upsertDocumentEverywhere(msg, previousMarkdown, nextMarkdown)
      }
    }
  } finally {
    documentEditorLoading.value = false
  }
}

// Ensure refs are stored in order
function setMsgRef(el: any, msgId: string) {
  if (!msgId) return
  if (el) {
    msgElements.value[msgId] = el as HTMLElement
  } else {
    delete msgElements.value[msgId]
  }
}

// Scroll handling
function handleScroll() {
  if (!messagesContainer.value) return
  if (isProgrammaticScroll.value) return
  const container = messagesContainer.value
  const remainingScroll = container.scrollHeight - (container.scrollTop + container.clientHeight)
  
  const stickyAssistantMsg =
    stickyAssistantMsgId.value
      ? displayMessages.value.find((m) => m._id === stickyAssistantMsgId.value)
      : null
  const stickyAssistantHasRenderableContent = !!(
    stickyAssistantMsg &&
    (
      (stickyAssistantMsg.content && stickyAssistantMsg.content.trim().length > 0) ||
      (stickyAssistantMsg.documents && stickyAssistantMsg.documents.length > 0) ||
      (stickyAssistantMsg.progress && stickyAssistantMsg.progress.length > 0)
    )
  )
  
  if (stickyState.value === 'LOCKED') {
    // In LOCKED mode, arrow visibility must be based ONLY on current assistant real content,
    // not on scrollHeight (which includes min-height shell).
    if (!stickyAssistantHasRenderableContent) {
      showScrollButton.value = false
    } else if (stickyAssistantMsgId.value) {
      const stickyAssistantEl = msgElements.value[stickyAssistantMsgId.value]
      if (stickyAssistantEl) {
        const containerRect = container.getBoundingClientRect()
        const contentProbe =
          (stickyAssistantEl.querySelector('.assistant-content') as HTMLElement | null)
          || (stickyAssistantEl.querySelector('.assistant-loading-breathe') as HTMLElement | null)
          || (stickyAssistantEl.firstElementChild as HTMLElement | null)
          || stickyAssistantEl
        const probeRect = contentProbe.getBoundingClientRect()
        showScrollButton.value = probeRect.bottom > (containerRect.bottom + 16)
      } else {
        showScrollButton.value = false
      }
    } else {
      showScrollButton.value = false
    }
  } else {
    // Normal mode.
    showScrollButton.value = remainingScroll > 16
    const lastMsgId = displayMessages.value[displayMessages.value.length - 1]?._id
    const lastMsg = lastMsgId ? msgElements.value[lastMsgId] : null
    if (lastMsg && remainingScroll <= 1) {
      const rect = lastMsg.getBoundingClientRect()
      const containerRect = container.getBoundingClientRect()
      const isLastMsgVisible = rect.top < containerRect.bottom && rect.bottom > containerRect.top
      showScrollButton.value = !isLastMsgVisible
    }
  }
  
  // Detect user manual scrolling in LOCKED state
  if (stickyState.value === 'LOCKED') {
    if (scrollTimeout) clearTimeout(scrollTimeout)
    scrollTimeout = setTimeout(() => {
      // Sticky state may have changed while timer was waiting.
      if (stickyState.value !== 'LOCKED') return
      // If within lock period, ignore this scroll event
      if (Date.now() < scrollLockUntil.value) {
        stickyLog('Scroll ignored due to lock')
        return
      }
      // Only user-driven scroll should unlock sticky mode.
      if (Date.now() > userScrollIntentUntil.value) {
        stickyLog('Scroll ignored (no user intent)')
        return
      }
      
      stickyLog('Detected manual scroll, unlock to MANUAL_SCROLL')
      stickyState.value = 'MANUAL_SCROLL'
    }, 100)
  }
}

// Sticky-top helper functions
function unlockSticky() {
  stopStickyFollow()
  if (scrollTimeout) {
    clearTimeout(scrollTimeout)
    scrollTimeout = null
  }
  stickyLog('unlockSticky', {
    state: stickyState.value,
    userId: stickyUserMsgId.value,
    assistantId: stickyAssistantMsgId.value,
  })
  stickyState.value = 'UNLOCKED'
  stickySpacerHeight.value = 0
  stickyUserMsgId.value = null
  stickyAssistantMsgId.value = null
  userScrollIntentUntil.value = 0
}

function updateSpacerHeight() {
  if (stickyState.value !== 'LOCKED' || !stickyUserMsgId.value) return
  ensureStickyAnchorBound()
  
  const userMsgEl = msgElements.value[stickyUserMsgId.value]
  const aiMsgEl = stickyAssistantMsgId.value ? msgElements.value[stickyAssistantMsgId.value] : undefined
  
  if (!userMsgEl || !messagesContainer.value) {
    stickyLog('updateSpacerHeight skipped', {
      hasUserEl: !!userMsgEl,
      hasContainer: !!messagesContainer.value,
      userId: stickyUserMsgId.value,
      assistantId: stickyAssistantMsgId.value,
    })
    return
  }
  
  const viewportHeight = messagesContainer.value.clientHeight
  const userMsgHeight = userMsgEl.offsetHeight
  const aiMsgHeight = aiMsgEl?.offsetHeight || 0
  
  // 如果AI回复已经超过可视区域,解锁并滚动到底部
  if (aiMsgHeight >= viewportHeight - userMsgHeight - 100) {
    // Content has reached the lower viewport bound.
    // Keep sticky state, but collapse spacer to zero instead of unlocking immediately.
    // This avoids "flash unlock" before users can perceive sticky-top behavior.
    stickySpacerHeight.value = 0
    stickyLog('ai exceeds viewport, collapse spacer', {
      aiMsgHeight,
      viewportHeight,
      userMsgHeight,
    })
    return
  }
  
  // 否则调整占位块高度
  const newHeight = Math.max(0, viewportHeight - userMsgHeight - aiMsgHeight - 60)
  stickySpacerHeight.value = newHeight
}

function scrollToUserMessage(): boolean {
  if (!stickyUserMsgId.value) {
    stickyLog('scrollToUserMessage failed: missing stickyUserMsgId')
    return false
  }
  ensureStickyAnchorBound()
  const userMsgEl = msgElements.value[stickyUserMsgId.value]
  if (!userMsgEl || !messagesContainer.value) {
    stickyLog('scrollToUserMessage failed: missing el/container', {
      hasUserEl: !!userMsgEl,
      hasContainer: !!messagesContainer.value,
      userId: stickyUserMsgId.value,
    })
    return false
  }
  
  // Set lock for 1 second
  scrollLockUntil.value = Date.now() + 1000
  
  const targetTop = Math.max(0, userMsgEl.offsetTop - 8)
  isProgrammaticScroll.value = true
  messagesContainer.value.scrollTop = targetTop
  requestAnimationFrame(() => {
    isProgrammaticScroll.value = false
  })
  return true
}

async function alignStickyAnchorWithRetry(maxTries = 8) {
  stickyLog('alignStickyAnchorWithRetry start', {
    maxTries,
    state: stickyState.value,
    userId: stickyUserMsgId.value,
    assistantId: stickyAssistantMsgId.value,
  })
  for (let i = 0; i < maxTries; i += 1) {
    await nextTick()
    const ok = scrollToUserMessage()
    if (ok) {
      updateSpacerHeight()
      stickyNeedsInitialAlign.value = false
      stickyLog('alignStickyAnchorWithRetry success', { attempt: i + 1 })
      return true
    }
    stickyLog('alignStickyAnchorWithRetry retry', { attempt: i + 1 })
    await new Promise((resolve) => requestAnimationFrame(() => resolve(true)))
  }
  stickyLog('alignStickyAnchorWithRetry failed', {
    state: stickyState.value,
    userId: stickyUserMsgId.value,
    assistantId: stickyAssistantMsgId.value,
  })
  return false
}



function assistantTurnStyle(msg: Message) {
  if (stickyState.value !== 'LOCKED') return undefined
  if (!stickyAssistantMsgId.value || msg._id !== stickyAssistantMsgId.value) return undefined
  const minH = stickyTurnMinHeightPx.value
  if (!minH) return undefined
  // Auto-computed from viewport/header/composer layout.
  return { minHeight: `${minH}px` }
}

async function scrollToBottom() {
  // Arrow click is an explicit user action to leave sticky mode.
  if (stickyState.value === 'LOCKED') {
    unlockSticky()
    await nextTick()
  }
  if (messagesContainer.value) {
    isProgrammaticScroll.value = true
    messagesContainer.value.scrollTo({
      top: messagesContainer.value.scrollHeight,
      behavior: 'smooth'
    })
    setTimeout(() => {
      isProgrammaticScroll.value = false
    }, 500)
  }
}

onMounted(() => {
  handleScroll()
  recomputeStickyTurnMinHeight()
  loadChatModels()
  window.addEventListener('resize', recomputeStickyTurnMinHeight)
  if (typeof ResizeObserver !== 'undefined') {
    layoutObserver = new ResizeObserver(() => recomputeStickyTurnMinHeight())
    if (messagesContainer.value) layoutObserver.observe(messagesContainer.value)
    if (composerContainer.value) layoutObserver.observe(composerContainer.value)
  }
  nextTick().then(() => {
    renderMermaidBlocks()
    renderChartBlocks()
  })
})

watch(() => props.mainId, () => {
  loadChatModels()
})

onBeforeUnmount(() => {
  cancelPromptGuideClose()
  window.removeEventListener('resize', recomputeStickyTurnMinHeight)
  if (layoutObserver) {
    layoutObserver.disconnect()
    layoutObserver = null
  }
  if (layoutRaf !== null) {
    cancelAnimationFrame(layoutRaf)
    layoutRaf = null
  }
})

// onUpdated fires after EVERY component re-render. During heavy backend
// event traffic (QA Round 1/3 emits ~10 events/sec) each event causes:
//   store update → Timeline rerender → ChatWindow rerender → onUpdated
// And the body of this hook used to (a) call handleScroll which writes a
// ref → triggers another rerender, (b) schedule a RAF, (c) walk the DOM
// querying for mermaid/chart nodes, (d) run alignStickyAnchorWithRetry
// up to 6 times. The cumulative paint work outpaced the WebView and
// produced the visible flicker / black-frame / corrupted-paint
// artefacts in embedded desktop renderers.
//
// Throttle to one execution per animation frame: coalesce all updates
// in the current frame into a single deferred run. Cheaper than a
// time-based throttle (no setTimeout), and naturally aligned with the
// browser's paint cadence.
let onUpdatedScheduled = false
function scheduleOnUpdatedWork() {
  if (onUpdatedScheduled) return
  onUpdatedScheduled = true
  requestAnimationFrame(() => {
    onUpdatedScheduled = false
    handleScroll()
    recomputeStickyTurnMinHeight()
    nextTick().then(() => {
      if (stickyState.value === 'LOCKED' && stickyNeedsInitialAlign.value) {
        stickyLog('onUpdated triggers alignStickyAnchorWithRetry')
        void alignStickyAnchorWithRetry(6)
      }
      renderMermaidBlocks()
      renderChartBlocks()
      if (debugEnabled) {
        const nodes = Array.from(document.querySelectorAll('.assistant-content')) as HTMLElement[]
        const texts = nodes.map((n) => n.innerText.trim()).filter(Boolean)
        const htmls = nodes.map((n) => n.innerHTML.trim()).filter(Boolean)
        console.log('[chat-debug] assistant-nodes', { count: nodes.length, texts, htmls })
        nodes.forEach((n, idx) => {
          console.log(`[chat-debug] assistant-node-${idx}-text`, JSON.stringify(n.innerText))
          console.log(`[chat-debug] assistant-node-${idx}-html`, JSON.stringify(n.innerHTML))
          console.log(`[chat-debug] assistant-node-${idx}-children`, n.childNodes.length)
        })
      }
    })
  })
}

onUpdated(scheduleOnUpdatedWork)

watch(
  () => props.sessionId,
  async (nextId, prevId) => {
    if (nextId === prevId) return
    // Reset browser intervention state on session change
    resetBrowserWorkspace()

    msgElements.value = {}
    showScrollButton.value = false

  }
)

watch(
  () => props.initialMessages,
  (nextMessages) => {
    if (!nextMessages) return
    msgElements.value = {}
    showScrollButton.value = false
    if (isLoading.value) {
      activateStickyForLatestRunningTurn()
    } else if (stickyState.value === 'LOCKED') {
      stickyNeedsInitialAlign.value = true
      nextTick(() => {
        void alignStickyAnchorWithRetry(6)
      })
    }
  },
  { deep: true }
)

async function ensureScript(url: string, globalName: string): Promise<any> {
  if ((window as any)[globalName]) return (window as any)[globalName]
  return new Promise((resolve, reject) => {
    const existing = document.querySelector(`script[data-src="${url}"]`) as HTMLScriptElement | null
    if (existing) {
      existing.addEventListener('load', () => resolve((window as any)[globalName]))
      existing.addEventListener('error', reject)
      return
    }
    const script = document.createElement('script')
    script.src = url
    script.async = true
    script.dataset.src = url
    script.onload = () => resolve((window as any)[globalName])
    script.onerror = reject
    document.head.appendChild(script)
  })
}

async function renderMermaidBlocks() {
  const blocks = Array.from(document.querySelectorAll('.mermaid')) as HTMLElement[]
  if (!blocks.length) return
  const mermaid = await ensureScript('https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.min.js', 'mermaid')
  if (!mermaid) return
  mermaid.initialize({ startOnLoad: false })
  for (const block of blocks) {
    if (block.dataset.rendered === 'true') continue
    block.dataset.rendered = 'true'
    try {
      await mermaid.run({ nodes: [block] })
    } catch {
      const raw = block.dataset.raw ? decodeURIComponent(block.dataset.raw) : (block.textContent || '')
      const sanitized = sanitizeMermaid(raw)
      if (sanitized !== raw) {
        try {
          block.textContent = sanitized
          await mermaid.run({ nodes: [block] })
          block.dataset.rendered = 'true'
          continue
        } catch {
          // fall through
        }
      }
      const preview = raw.length > 800 ? raw.slice(0, 800) + '…' : raw
      block.dataset.rendered = 'false'
      block.classList.remove('mermaid')
      block.innerHTML = `<div class="text-xs text-red-600 mb-2">${t('chat.mermaid_error')}</div><pre class="bg-gray-50 border border-gray-200 rounded-lg p-3 text-xs overflow-auto whitespace-pre-wrap">${preview}</pre>`
    }
  }
}

async function renderChartBlocks() {
  const canvases = Array.from(document.querySelectorAll('canvas.chart-block')) as HTMLCanvasElement[]
  if (!canvases.length) return
  const Chart = await ensureScript('https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js', 'Chart')
  if (!Chart) {
    console.error('[Chart] Failed to load Chart.js')
    return
  }
  for (const canvas of canvases) {
    if (canvas.dataset.rendered === 'true') continue
    const raw = canvas.dataset.chart || ''
    let payload: any
    try {
      const decoded = decodeURIComponent(raw)
      try {
        payload = JSON.parse(decoded)
      } catch {
        // Handle potentially escaped double quotes in malformed JSON
        const cleaned = decoded.replace(/\\"/g, '"')
        payload = JSON.parse(cleaned)
      }
    } catch (e) {
      const decoded = decodeURIComponent(raw)
      payload = parseChartPayload(decoded)
      if (!payload) {
        console.error('[Chart] Failed to parse chart data:', e)
        continue
      }
    }
    
    // Support multiple formats:
    // 1. Simplified: {type, labels/xAxis, series: [{name, data}]}
    // 2. Chart.js native: {type, data: {labels, datasets}, options}
    let type = (payload.type || 'line').toLowerCase()
    if (type === 'column') type = 'bar'
    if (type === 'sankey') {
      await ensureScript('https://cdn.jsdelivr.net/npm/chartjs-chart-sankey@0.13.0/dist/chartjs-chart-sankey.min.js', 'chartjsChartSankey')
      // Ensure sankey controller is registered with Chart.js (UMD bundles may not auto-register)
      const candidates = [
        (Chart as any),
        (window as any),
        (window as any).ChartSankey,
        (window as any).chartjsChartSankey,
        (window as any).ChartSankey?.default,
        (window as any).chartjsChartSankey?.default,
      ].filter(Boolean)
      let SankeyController: any
      let Flow: any
      for (const mod of candidates) {
        if (!SankeyController && (mod as any).SankeyController) {
          SankeyController = (mod as any).SankeyController
        }
        if (!Flow && (mod as any).Flow) {
          Flow = (mod as any).Flow
        }
      }
      if (SankeyController && Flow && (Chart as any).register) {
        try {
          ;(Chart as any).register(SankeyController, Flow)
        } catch (e) {
          console.warn('[Chart] Failed to register sankey controller:', e)
        }
      } else {
        console.warn('[Chart] Sankey controller not found after loading plugin')
      }
    }
    
    let labels: any[]
    let datasets: any[]
    let renderAsTable = false
    let tableRows: Array<[string, string]> = []
    
    const dataObj = payload.data || payload
    if (dataObj && dataObj.labels && dataObj.datasets) {
      // Chart.js native or semi-native format
      labels = dataObj.labels
      datasets = dataObj.datasets.map((ds: any) => ({
        ...ds,
        borderWidth: ds.borderWidth || 2,
        fill: ds.fill !== undefined ? ds.fill : (type === 'bar'),
      }))
    } else if (type === 'sankey' && payload.data && payload.data.links) {
      const links = payload.data.links || []
      const nodeNames = Array.isArray(payload.data.nodes)
        ? payload.data.nodes.map((n: any) => (n && n.name ? String(n.name) : String(n)))
        : []
      const derivedNames = new Set<string>()
      for (const link of links) {
        if (link.source !== undefined && link.source !== null) derivedNames.add(String(link.source))
        if (link.target !== undefined && link.target !== null) derivedNames.add(String(link.target))
      }
      const allNames = nodeNames.length ? nodeNames : Array.from(derivedNames)
      const nameSet = new Set(allNames)
      labels = allNames
      datasets = [{
        label: payload.title || 'Sankey',
        data: links
          .map((link: any) => ({
            from: String(link.source),
            to: String(link.target),
            flow: link.value ?? link.flow ?? 0
          }))
          .filter((link: any) => nameSet.has(link.from) && nameSet.has(link.to)),
        colorMode: 'gradient',
        colorFrom: '#7aa6ff',
        colorTo: '#7ecf9a',
        borderWidth: 1,
        borderColor: 'rgba(0,0,0,0.08)'
      }]
    } else if (payload.data && Array.isArray(payload.data) && payload.xField && payload.yField) {
      // Array of objects with xField + multiple yField
      const rows = payload.data
      const yFields = Array.isArray(payload.yField) ? payload.yField : [payload.yField]
      labels = rows.map((r: any) => r[payload.xField])
      datasets = yFields.map((field: string, idx: number) => ({
        label: field,
        data: rows.map((r: any) => r[field] ?? 0),
        borderWidth: 2,
        fill: type === 'bar',
      }))
    } else if (payload.data && payload.data.labels && payload.data.values) {
      // Simple format: {data:{labels, values}}
      labels = payload.data.labels
      datasets = [{
        label: payload.title || 'Series 1',
        data: payload.data.values,
        borderWidth: 2,
        fill: type === 'bar',
      }]
    } else if (payload.data && payload.data.values && Array.isArray(payload.data.values) && payload.type === 'pie') {
      // Pie format: {data:{values:[{category, value}]}}
      labels = payload.data.values.map((v: any) => v.category)
      datasets = [{
        label: payload.title || 'Series 1',
        data: payload.data.values.map((v: any) => v.value),
        borderWidth: 1,
      }]
      type = 'pie'
    } else if (payload.data && Array.isArray(payload.data) && type === 'bar' && !payload.xField) {
      // Array rows without explicit xField -> use first key as label, second as value
      const rows = payload.data
      const keys = rows.length ? Object.keys(rows[0]) : []
      const labelKey = keys[0]
      const valueKey = keys[1]
      const values = rows.map((r: any) => r[valueKey])
      const numeric = values.every((v: any) => typeof v === 'number' && !Number.isNaN(v))
      if (!numeric) {
        renderAsTable = true
        tableRows = rows.map((r: any) => [String(r[labelKey] ?? ''), String(r[valueKey] ?? '')])
        labels = []
        datasets = []
      } else {
        labels = rows.map((r: any) => r[labelKey])
        datasets = [{
          label: payload.title || valueKey || 'Series 1',
          data: values,
          borderWidth: 2,
          fill: true,
        }]
      }
    } else if (payload.series && payload.xAxis) {
      // ECharts-like format
      labels = payload.xAxis.data || payload.xAxis
      datasets = (payload.series || []).map((s: any, idx: number) => ({
        label: s.name || `Series ${idx + 1}`,
        data: s.data || [],
        borderWidth: 2,
        fill: type === 'bar',
      }))
    } else if (type === 'scatter' && payload.data && payload.data.datasets) {
      labels = []
      datasets = payload.data.datasets.map((ds: any) => ({
        ...ds,
        borderWidth: ds.borderWidth || 2,
      }))
    } else if (type === 'scatter' && payload.data && payload.xField && payload.yField) {
      // Scatter chart with xField/yField format
      labels = []
      const dataPoints = payload.data
      const seriesField = payload.seriesField
      
      if (seriesField) {
        // Group by series field
        const grouped = new Map<string, any[]>()
        for (const item of dataPoints) {
          const seriesName = item[seriesField]
          if (!grouped.has(seriesName)) {
            grouped.set(seriesName, [])
          }
          grouped.get(seriesName)!.push({
            x: item[payload.xField],
            y: item[payload.yField]
          })
        }
        
        datasets = Array.from(grouped.entries()).map(([name, data]) => ({
          label: name,
          data: data,
          borderWidth: 2,
        }))
      } else {
        // Single series
        datasets = [{
          label: payload.title || 'Data',
          data: dataPoints.map((item: any) => ({
            x: item[payload.xField],
            y: item[payload.yField]
          })),
          borderWidth: 2,
        }]
      }
    } else {
      // Simplified format (support labels, xAxis, or x)
      labels = payload.labels || payload.xAxis || payload.x || []
      const series = payload.series || []
      
      if (series.length === 0 && payload.y) {
        // Fallback for {x, y} format
        datasets = [{
          label: payload.yLabel || payload.title || 'Data',
          data: payload.y,
          borderWidth: 2,
          fill: type === 'bar',
        }]
      } else {
        datasets = series.map((s: any, idx: number) => ({
          label: s.name || `Series ${idx + 1}`,
          data: s.data || [],
          borderWidth: 2,
          fill: type === 'bar',
        }))
      }
    }
    
    const chartOptions = payload.options || { responsive: true, maintainAspectRatio: false }
    if (type === 'sankey') {
      chartOptions.parsing = { from: 'from', to: 'to', flow: 'flow' }
      chartOptions.plugins = chartOptions.plugins || {}
      chartOptions.plugins.legend = { display: false }
      chartOptions.plugins.tooltip = { enabled: true }
    }
    
    try {
      if (renderAsTable) {
        const container = canvas.parentElement
        if (container) {
          const header1 = payload.xField || (locale.value === 'zh' ? '项' : 'Item')
          const header2 = payload.yField || (locale.value === 'zh' ? '内容' : 'Content')
          const rowsHtml = tableRows
            .map(([a, b]) => `<tr><td class="border border-gray-300 px-3 py-2">${a}</td><td class="border border-gray-300 px-3 py-2">${b}</td></tr>`)
            .join('')
          container.innerHTML = `
            <table class="w-full text-sm border border-gray-300 border-collapse">
              <thead>
                <tr>
                  <th class="border border-gray-300 px-3 py-2 text-left">${header1}</th>
                  <th class="border border-gray-300 px-3 py-2 text-left">${header2}</th>
                </tr>
              </thead>
              <tbody>${rowsHtml}</tbody>
            </table>
          `
        }
        canvas.dataset.rendered = 'true'
        continue
      }
      const resolvedType = type === 'bar' || type === 'line' || type === 'pie' || type === 'scatter' || type === 'sankey'
        ? type
        : 'line'
      new (Chart as any)(canvas, {
        type: resolvedType,
        data: { labels, datasets },
        options: chartOptions,
      })
      canvas.dataset.rendered = 'true'
    } catch (e) {
      console.error('[Chart] Failed to render chart:', e)
    }
  }
}

function parseChartPayload(raw: string): any | null {
  const text = String(raw || '').trim()
  if (!text) return null
  try {
    return JSON.parse(text)
  } catch {
    // fallthrough
  }
  const typeMatch = text.match(/^type:\s*([^\n]+)$/m)
  const titleMatch = text.match(/^title:\s*([^\n]+)$/m)
  const baseType = typeMatch ? typeMatch[1].trim() : 'line'
  const baseTitle = titleMatch ? titleMatch[1].trim() : 'Chart'

  const labelsMatch = text.match(/^labels:\s*(\[[^\]]*\])$/m)
  const valuesMatch = text.match(/^values:\s*(\[[^\]]*\])$/m)
  if (labelsMatch && valuesMatch) {
    try {
      return {
        type: baseType,
        title: baseTitle,
        labels: JSON.parse(labelsMatch[1]),
        series: [{ name: 'Series', data: JSON.parse(valuesMatch[1]) }],
      }
    } catch {
      // continue
    }
  }

  const xMatch = text.match(/^x:\s*(\[[^\]]*\])$/m)
  const yMatch = text.match(/^y:\s*(\[[^\]]*\])$/m)
  if (xMatch && yMatch) {
    try {
      return {
        type: baseType,
        title: baseTitle,
        labels: JSON.parse(xMatch[1]),
        series: [{ name: 'Series', data: JSON.parse(yMatch[1]) }],
      }
    } catch {
      // continue
    }
  }

  const dataLabelsMatch = text.match(/labels:\s*(\[[^\]]*\])/)
  const datasetMatches = Array.from(text.matchAll(/-\s*label:\s*([^\n]+)\s*(?:\n|\r\n)\s*data:\s*(\[[^\]]*\])/g))
  if (dataLabelsMatch && datasetMatches.length) {
    try {
      const labels = JSON.parse(dataLabelsMatch[1])
      const series = datasetMatches.map((m) => ({
        name: m[1].trim(),
        data: JSON.parse(m[2]),
      }))
      return { type: baseType, title: baseTitle, labels, series }
    } catch {
      // continue
    }
  }

  const pieMatches = Array.from(text.matchAll(/-\s*label:\s*([^\n]+)\s*(?:\n|\r\n)\s*value:\s*([0-9.]+)/g))
  if (pieMatches.length) {
    const labels = pieMatches.map((m) => m[1].trim())
    const data = pieMatches.map((m) => Number(m[2]))
    return { type: baseType, title: baseTitle, labels, series: [{ name: 'Series', data }] }
  }
  const lines = text.split('\n').map((l) => l.trim()).filter(Boolean)
  const obj: any = {}
  let currentKey: string | null = null

  const parseScalar = (val: string): any => {
    const v = val.trim()
    if (!v) return ''
    if (v.startsWith('[') && v.endsWith(']')) {
      try {
        return JSON.parse(v)
      } catch {
        return v
      }
    }
    if (/^-?\d+(\.\d+)?$/.test(v)) return Number(v)
    if ((v.startsWith('"') && v.endsWith('"')) || (v.startsWith("'") && v.endsWith("'"))) {
      return v.slice(1, -1)
    }
    return v
  }

  for (const line of lines) {
    if (line.startsWith('- ') && currentKey) {
      const item = line.slice(2)
      const parts = item.split(':')
      if (parts.length >= 2) {
        const key = parts[0].trim()
        const val = parseScalar(parts.slice(1).join(':'))
        obj[currentKey] = obj[currentKey] || []
        obj[currentKey].push({ label: key, value: val })
      } else {
        obj[currentKey] = obj[currentKey] || []
        obj[currentKey].push(parseScalar(item))
      }
      continue
    }
    const idx = line.indexOf(':')
    if (idx === -1) continue
    const key = line.slice(0, idx).trim()
    const val = line.slice(idx + 1).trim()
    if (!val) {
      currentKey = key
      if (!obj[currentKey]) obj[currentKey] = []
      continue
    }
    currentKey = key
    obj[key] = parseScalar(val)
  }

  const payload: any = { type: obj.type || 'line', title: obj.title || 'Chart' }
  if (Array.isArray(obj.labels) && (Array.isArray(obj.values) || Array.isArray(obj.y))) {
    payload.labels = obj.labels
    payload.series = [
      { name: obj.seriesName || 'Series', data: Array.isArray(obj.values) ? obj.values : obj.y },
    ]
    return payload
  }
  if (Array.isArray(obj.x) && Array.isArray(obj.y)) {
    payload.labels = obj.x
    payload.series = [{ name: obj.seriesName || 'Series', data: obj.y }]
    return payload
  }
  if (Array.isArray(obj.values) && obj.values.length && typeof obj.values[0] === 'object') {
    const labels = obj.values.map((v: any) => v.label)
    const data = obj.values.map((v: any) => v.value)
    payload.labels = labels
    payload.series = [{ name: obj.seriesName || 'Series', data }]
    return payload
  }
  return null
}

function normalizeUserContent(content: string): string {
  const text = String(content || '')
  const markers = ['[文档处理状态]', '[文档语义摘要]', '[文档Markdown]']
  let cutIndex = -1
  for (const marker of markers) {
    const idx = text.indexOf(marker)
    if (idx >= 0 && (cutIndex < 0 || idx < cutIndex)) {
      cutIndex = idx
    }
  }
  if (cutIndex < 0) return text
  return text.slice(0, cutIndex).trimEnd()
}

function isPlainAssistantText(content: string): boolean {
  if (!content) return true
  const trimmed = content.trim()
  if (!trimmed) return true
  const markers = ['#', '>', '*', '_', '`', '[', ']', '(', ')', '/', '\\']
  const hasMarker = markers.some((token) => trimmed.includes(token))
  return !hasMarker && !trimmed.includes('```')
}

function formatErrorMessage(raw: string): string {
  const text = String(raw || '')
  if (raw.includes('DeploymentNotFound')) {
    return t('chat.model_not_found')
  }
  if (
    text.includes('content_filter') ||
    text.includes('ResponsibleAIPolicyViolation') ||
    text.includes('content management policy')
  ) {
    return t('chat.safety_blocked')
  }
  if (text.includes('429') || text.toLowerCase().includes('rate limit')) {
    return t('chat.rate_limited')
  }
  if (text.includes('401') || text.toLowerCase().includes('unauthorized')) {
    return t('chat.unauthorized')
  }
  return text
}

</script>

<template>
  <BrowserWorkspace
    :active="props.active"
    :enabled="allowBrowser"
    :open="isPreviewExpanded"
    :tabs="props.desktopToolTabs || []"
    :active-tool="props.desktopActiveTool"
    :active-kind="desktopActiveTab?.kind"
    :available-tools="props.desktopAvailableTools || []"
    :locale="locale === 'en' ? 'en' : 'zh'"
    :session-id="props.sessionId"
    :user-id="props.userId"
    :main-id="props.mainId"
    @update:open="(value) => { isPreviewExpanded = value; if (!value) emit('close-code-panel') }"
    @select-tab="emit('select-desktop-tool', $event)"
    @close-tab="emit('close-desktop-tool', $event)"
    @open-tab="emit('open-desktop-tool', $event)"
  >
    <div class="relative flex h-full w-full overflow-hidden">
    <!-- Main Chat Area -->
    <div 
      class="relative flex h-full min-w-0 flex-1 flex-col"
    >
    <!-- Messages Area -->
    <div
      ref="messagesContainer"
      @scroll="handleScroll"
      class="flex-1 overflow-y-auto w-full custom-scrollbar"
      style="overflow-anchor: none;"
    >
      <div
        v-if="displayMessages.length === 0"
        class="h-full w-full"
      ></div>

            <div 
              v-else
              class="flex flex-col pb-[85vh] text-sm md:text-base space-y-6 p-4 md:p-6 max-w-4xl mx-auto w-full"
              @wheel.passive="markUserScrollIntent"
              @touchstart.passive="markUserScrollIntent"
            >
        <div 
          v-for="(msg, idx) in displayMessages" 
          :key="msg._id || idx"
        >
          <div
            :ref="(el) => setMsgRef(el, msg._id || '')" 
            class="group/user-message flex w-full"
            :class="msg.role === 'user' ? 'justify-end' : 'justify-start'"
            :data-scroll-anchor="stickyState === 'LOCKED' && msg._id === stickyAssistantMsgId ? 'true' : undefined"
            :style="msg.role === 'assistant' ? assistantTurnStyle(msg) : undefined"
          >
          <!-- Message Bubble Container -->
          <div 
            class="relative max-w-[85%] rounded-2xl p-4 transition-all duration-200"
            :class="msg.role === 'user' ? 'bg-transparent p-0 text-slate-800' : 'bg-transparent text-gray-900 px-0'"
          >
            <div v-if="msg.role === 'assistant'" class="mb-4">
              <ExecutionViewV3
                :store="ensureExecV3(msg)"
                :live="isAssistantGenerating(idx, msg)"
                @resolve-permission="(rid: string, dec: 'allow'|'deny'|'always_allow') => onPermissionResolve(msg, rid, dec)"
              />
            </div>

            <!-- Login prompt (local agent) — shown on the last assistant msg -->
            <LocalBrowserInterventionPrompt
              v-if="activeIntervention && msg.role === 'assistant' && idx === displayMessages.length - 1"
              class="mt-2"
              :category="activeIntervention.category"
              :domain="(activeIntervention as any).domain || activeIntervention.reason"
              :reason="activeIntervention.reason"
              :handoff="(activeIntervention as any).handoff"
              @confirm="handleLocalInterventionDone"
              @skip="() => handleLocalInterventionDone()"
              @show-browser="openBrowserForIntervention"
            />

            <!-- Content -->
            <template v-if="msg.role === 'assistant'">
              <div
                v-if="shouldShowBreathingLoading(idx, msg)"
                class="assistant-loading-breathe mt-2 flex items-center gap-2 text-gray-500"
              >
                <span class="assistant-loading-dot"></span>
              </div>
              <div
                v-if="msg.content && isPlainAssistantText(msg.content)"
                class="assistant-content text-[14px] text-gray-900 leading-6 whitespace-pre-wrap"
              >
                {{ normalizeAssistantContent(msg.content) }}
              </div>
              <AssistantMarkdown
                v-else-if="msg.content"
                class="assistant-content"
                :content="msg.content"
                :file-references="Boolean(props.codeSession)"
                @open-file="(path) => emit('open-code-file', path)"
              />
              <CodeTaskChangeCard
                v-if="msg._codeChanges && props.codeSession"
                class="mt-3"
                :session-id="props.codeSession.kernel_session_id"
                :changes="msg._codeChanges"
                :locale="locale === 'en' ? 'en' : 'zh'"
                @review="(changes, path) => emit('review-code-changes', changes, path)"
                @undone="(changes) => { msg._codeChanges = changes; emit('code-workspace-change') }"
              />
              <!-- Artifacts appear AFTER the assistant text, like Claude Code. -->
              <div class="mt-3">
                <ArtifactList
                  :store="artifactStore(msg)"
                  @open="(a: ArtifactItem) => onArtifactOpen(a, msg, idx)"
                  @edit="(a: ArtifactItem) => onArtifactEditPresentation(a, msg)"
                  @export="(a: ArtifactItem) => onArtifactExportPresentation(a, msg)"
                  @preview="(a: ArtifactItem) => onArtifactPreviewHtml(a)"
                  @download="(a: ArtifactItem) => onArtifactDownload(a)"
                />
                <button
                  v-if="shouldShowEvidenceTrigger(idx, msg)"
                  type="button"
                  class="mt-2 inline-flex min-h-11 items-center gap-2 rounded-lg border border-slate-200 bg-white px-3 text-sm font-medium text-slate-700 shadow-sm transition hover:border-blue-200 hover:bg-blue-50 hover:text-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500"
                  @click="openLatestEvidenceDrawer(msg)"
                >
                  <svg viewBox="0 0 24 24" class="h-4 w-4" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <path d="M8 6h13"></path>
                    <path d="M8 12h13"></path>
                    <path d="M8 18h13"></path>
                    <path d="M3 6h.01"></path>
                    <path d="M3 12h.01"></path>
                    <path d="M3 18h.01"></path>
                  </svg>
                  <span>{{ evidenceTriggerTextForMessage(msg) }}</span>
                </button>
              </div>
            </template>
            <template v-else>
              <div class="rounded-2xl rounded-br-sm bg-blue-50 p-4 shadow-sm">
                <div v-if="msg.trigger_source === 'scheduled'" class="mb-2 inline-flex items-center gap-1.5 rounded-full bg-blue-100 px-2 py-1 text-xs font-medium text-blue-700">
                  <svg viewBox="0 0 24 24" class="h-3.5 w-3.5" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/></svg>
                  定时任务自动发送
                </div>
                <div class="whitespace-pre-wrap leading-7">{{ normalizeUserContent(msg.content) }}</div>
                <div v-if="msg.images?.length" class="mt-3 flex flex-wrap gap-2">
                <img
                  v-for="(img, imgIdx) in msg.images"
                  :key="imgIdx"
                  :src="img.signed_url || img.url"
                  :alt="img.filename || 'uploaded-image'"
                  class="h-24 w-auto max-w-[220px] cursor-zoom-in rounded-lg border border-gray-200 object-cover"
                  loading="lazy"
                  @click="openImagePreview(img.signed_url || img.url, img.filename || 'uploaded-image')"
                />
                </div>
                <div v-if="msg.documents?.length" class="mt-3 space-y-2">
                <div
                  v-for="(doc, docIdx) in getDisplayDocuments(msg.documents)"
                  :key="docIdx"
                  class="flex items-center gap-3 rounded-2xl border border-blue-200 bg-blue-50/70 px-4 py-3 shadow-sm"
                >
                  <div class="h-10 w-10 rounded-xl bg-white flex items-center justify-center">
                    <img
                      :src="getDocPresentation(doc).icon"
                      :alt="t(getDocPresentation(doc).labelKey)"
                      class="h-8 w-8 object-contain"
                      loading="lazy"
                    />
                  </div>
                  <div class="min-w-0 flex-1">
                    <div class="truncate text-sm font-semibold text-slate-800">
                      {{ doc.title || doc.filename || t('chat.upload_document') }}
                    </div>
                    <div class="truncate text-xs text-slate-500">
                      {{ doc.filename || (locale === 'zh' ? `${doc.type.toUpperCase()} 文档` : `${doc.type.toUpperCase()} Document`) }}
                    </div>
                  </div>
                </div>
                </div>
              </div>
              <UserMessageActions
                v-if="String(msg.content || '').trim()"
                class="pointer-events-none absolute right-2 top-full z-10 max-w-full -translate-y-1 opacity-0 transition-opacity duration-150 group-hover/user-message:pointer-events-auto group-hover/user-message:opacity-100 group-focus-within/user-message:pointer-events-auto group-focus-within/user-message:opacity-100"
                :text="msg.content"
                :time="toTimeLabel(msg.created_at)"
                @schedule="emit('schedule-message', { prompt: msg.content, sessionId: props.sessionId })"
              />
            </template>
          </div>
        </div>
        </div>
      </div>
    </div>

    <!-- Scroll Down Button -->
    <transition
      enter-active-class="transition duration-200 ease-out"
      enter-from-class="opacity-0 translate-y-2"
      enter-to-class="opacity-100 translate-y-0"
      leave-active-class="transition duration-150 ease-in"
      leave-from-class="opacity-100 translate-y-0"
      leave-to-class="opacity-0 translate-y-2"
    >
      <button 
        v-if="showScrollButton"
        @click="scrollToBottom"
        class="absolute bottom-32 left-1/2 transform -translate-x-1/2 bg-white border border-gray-200 shadow-md rounded-full w-8 h-8 flex items-center justify-center hover:bg-gray-50 z-20 cursor-pointer text-gray-500 hover:text-gray-700 transition-colors"
      >
        <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="12" y1="5" x2="12" y2="19"></line><polyline points="19 12 12 19 5 12"></polyline></svg>
      </button>
    </transition>



    <!-- New composer-area features should be mounted as child components or slot content here. -->
    <div ref="composerContainer" class="shrink-0">
      <div v-if="props.codeError" class="mx-auto w-full max-w-4xl px-4 md:px-6">
        <div class="mb-2 rounded-xl border border-red-200 bg-red-50 px-3 py-2 text-xs leading-5 text-red-700" role="alert">
          {{ props.codeError }}
        </div>
      </div>
      <div v-if="activeDshApprovals.length" class="mx-auto w-full max-w-4xl px-4 md:px-6">
        <ToolApprovalPrompt
          v-for="approval in activeDshApprovals"
          :key="approval.id"
          :item="approval"
          :busy="Boolean(approvalBusy[approval.id])"
          :error="approvalErrors[approval.id] || ''"
          @decide="(decision, grantScope) => approvalControl.decide(approval, decision, grantScope)"
        />
      </div>
      <div v-if="props.codeApprovals?.length" class="mx-auto w-full max-w-4xl px-4 md:px-6">
        <DshCodeApprovalList
          :approvals="props.codeApprovals"
          :busy="props.codeApprovalBusy"
          :error="props.codeError"
          @decide="(approvalId, decision, scope) => emit('code-approval', approvalId, decision, scope)"
        />
      </div>
      <CodeHistoryReadOnlyNotice
        v-if="props.codeHistoryReadOnly && props.codeHistoryLocation"
        :execution-location="props.codeHistoryLocation"
        :project="props.codeHistoryProject"
      />
      <ChatComposer
        v-else
        ref="composerRef"
        :running="isLoading"
        :stopping="Boolean(props.stopping)"
        :is-new-session-view="isNewSessionView"
        :chat-models="chatModels"
        :selected-model-id="selectedModelId"
        :model-selector-label="modelSelectorLabel"
        :model-load-error="modelLoadError"
        :doc-icon="resolveArtifactIcon"
        :user-id="props.userId || ''"
        :main-id="props.mainId || 'default'"
        :allow-knowledge="allowKnowledge"
        :allow-skills="allowSkills"
        @send="(payload) => emit('send', payload)"
        @stop="emit('stop')"
        @select-model="selectChatModel"
        @image-preview="({ src, alt }) => openImagePreview(src, alt)"
      >
        <template #context>
          <CodeDraftContextBar
            v-if="allowCode && isNewSessionView && capabilities.localWorkspacePicker"
            :workspace="props.codeWorkspace || null"
            :session="props.codeSession"
            :busy="props.codeWorkspaceBusy"
            :worktree="props.codeWorktree"
            :source-ref="props.codeSourceRef"
            :model-id="selectedModelId"
            :locale="locale === 'en' ? 'en' : 'zh'"
            @choose="emit('choose-code-workspace', selectedModelId)"
            @clear="emit('clear-code-workspace')"
            @worktree="(enabled) => emit('code-worktree', enabled)"
            @source-ref="(fullRef) => emit('code-source-ref', fullRef)"
            @branch-updated="(branch) => emit('code-branch-updated', branch)"
          />
        </template>
        <template #prompt-guide>
        <div
          v-if="isNewSessionView"
          class="prompt-guide"
          @mouseenter="cancelPromptGuideClose"
          @mouseleave="schedulePromptGuideClose"
        >
          <div class="prompt-guide-tabs" role="tablist" :aria-label="t('任务引导')">
            <button
              v-for="category in visiblePromptGuideCategories"
              :key="category.key"
              type="button"
              class="prompt-guide-tab"
              :class="[category.tone, { 'is-active': activePromptGuideKey === category.key }]"
              role="tab"
              :aria-selected="activePromptGuideKey === category.key"
              @mouseenter="selectPromptGuideCategory(category.key)"
              @focus="selectPromptGuideCategory(category.key)"
              @click="selectPromptGuideCategory(category.key)"
            >
              <span class="prompt-guide-tab-icon">
                <span v-html="category.icon"></span>
              </span>
              <span>{{ t(category.label) }}</span>
            </button>
          </div>
          <transition
            enter-active-class="transition duration-200 ease-out"
            enter-from-class="opacity-0 translate-y-2"
            enter-to-class="opacity-100 translate-y-0"
            leave-active-class="transition duration-150 ease-in"
            leave-from-class="opacity-100 translate-y-0"
            leave-to-class="opacity-0 translate-y-1"
          >
            <div
              v-if="activePromptGuideCategory"
              :key="activePromptGuideCategory.key"
              class="prompt-guide-panel"
              @mouseenter="cancelPromptGuideClose"
              @mouseleave="schedulePromptGuideClose"
            >
              <div class="prompt-guide-arc">
                <button
                  v-for="item in activePromptGuideCategory.items"
                  :key="item.label"
                  type="button"
                  class="prompt-guide-item"
                  :class="{ 'is-locked': !item.available }"
                  @click="usePromptGuideItem(item)"
                >
                  <span class="prompt-guide-item-icon">
                    <span v-html="item.icon"></span>
                  </span>
                  <span class="prompt-guide-item-label">{{ t(item.label) }}</span>
                  <span v-if="!item.available" class="prompt-guide-lock">
                    <span v-html="promptGuideUiIcons.lock"></span>
                    {{ t('需配置') }}
                  </span>
                </button>
              </div>
              <div v-if="promptGuideNotice" class="prompt-guide-notice" role="status">
                <div class="prompt-guide-notice-icon">
                  <span v-html="promptGuideUiIcons.settings"></span>
                </div>
                <div class="min-w-0 flex-1">
                  <div class="prompt-guide-notice-title">{{ t(promptGuideNotice.title) }}</div>
                  <div class="prompt-guide-notice-desc">{{ t(promptGuideNotice.description) }}</div>
                </div>
                <button
                  type="button"
                  class="prompt-guide-config-btn"
                  @click="openPromptGuideConfig(promptGuideNotice.target)"
                >
                  {{ t('去配置') }}
                </button>
              </div>
            </div>
          </transition>
        </div>
        </template>
      </ChatComposer>
    </div>
  </div>
    <ProjectWorkspacePanel
      v-if="capabilities.codeInspector && props.codeSession && hasDesktopCodeTabs"
      v-show="Boolean(desktopCodePanelMode)"
      :session="props.codeSession"
      :active-id="props.desktopActiveTool || ''"
      :tabs="props.desktopToolTabs || []"
      :available-tabs="props.desktopAvailableTools || []"
      :locale="locale === 'en' ? 'en' : 'zh'"
      :running="isLoading"
      :review-path="props.desktopCodeReviewPath"
      :review-changes="props.desktopCodeReviewChanges"
      :file-path="props.desktopCodeFilePath"
      @close="emit('close-code-panel')"
      @select-tab="emit('select-desktop-tool', $event)"
      @close-tab="emit('close-desktop-tool', $event)"
      @open-tab="emit('open-desktop-tool', $event)"
      @open-file="emit('open-desktop-file-tab', $event)"
      @open-diff="(path, changes) => emit('open-desktop-diff-tab', path, changes)"
      @workspace-change="emit('code-workspace-change')"
    />
    </div>
  <div v-if="documentEditorOpen" class="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
    <div class="w-full max-w-5xl rounded-3xl bg-white shadow-xl">
      <div class="flex items-center justify-between border-b border-gray-100 px-6 py-4">
        <div>
          <div class="text-lg font-semibold text-gray-900">{{ activeDocument?.title || t('chat.doc_preview') }}</div>
          <div class="text-xs text-gray-400">{{ activeDocument?.filename }}</div>
        </div>
        <div class="flex items-center gap-3">
          <button
            class="rounded-full border border-gray-200 px-4 py-1.5 text-xs text-gray-600 hover:text-gray-800"
            @click="downloadDocument(activeDocument!)"
          >
            {{ t('ui.download') }}
          </button>
          <button
            class="rounded-full bg-blue-600 px-4 py-1.5 text-xs text-white hover:bg-blue-700"
            :disabled="documentEditorLoading"
            @click="regenerateDocument"
          >
            {{ documentEditorLoading ? t('chat.regenerating') : t('chat.regenerate') }}
          </button>
          <button class="text-gray-400 hover:text-gray-600 text-lg" @click="closeDocumentEditor">×</button>
        </div>
      </div>
      <div class="grid grid-cols-2 gap-4 px-6 py-4">
        <div class="flex flex-col">
          <div class="text-xs text-gray-500 mb-2">{{ t('chat.markdown_edit') }}</div>
          <textarea
            v-model="documentEditorContent"
            class="h-[60vh] w-full rounded-2xl border border-gray-200 p-3 text-sm leading-6 focus:outline-none focus:ring-2 focus:ring-blue-200"
          ></textarea>
        </div>
        <div class="flex flex-col">
          <div class="text-xs text-gray-500 mb-2">{{ t('chat.preview_panel') }}</div>
          <div
            class="h-[60vh] overflow-y-auto rounded-2xl border border-gray-200 p-4 prose prose-slate max-w-none"
            v-html="renderAssistantMarkdown(documentEditorContent)"
          ></div>
        </div>
      </div>
    </div>
  </div>
  <div
    v-if="imagePreviewOpen"
    class="fixed inset-0 z-[60] flex items-center justify-center bg-black/70 p-4"
    @click="closeImagePreview"
  >
    <button
      class="absolute right-5 top-5 rounded-full bg-black/60 px-3 py-1 text-xl text-white"
      @click.stop="closeImagePreview"
    >
      ×
    </button>
    <img
      :src="imagePreviewSrc"
      :alt="imagePreviewAlt"
      class="max-h-[90vh] max-w-[92vw] rounded-xl bg-white object-contain shadow-2xl"
      @click.stop
    />
  </div>

  </BrowserWorkspace>

  <!-- Presentation Editor Overlay -->
  <PresentationEditor
    v-if="presentationEditorOpen && presentationBlueprint"
    :blueprint="presentationBlueprint"
    :user-id="props.userId || 'anonymous'"
    :blueprint-object-path="presentationBlueprintPath"
    @close="closePresentationEditor"
    @exported="onPresentationExported"
    @saved="(bp) => { presentationBlueprint = bp }"
  />
  <EvidenceDrawer
    :open="evidenceDrawerOpen"
    :bundle="activeEvidenceBundle"
    @close="closeEvidenceDrawer"
    @open-source="openKnowledgeSourceFromDrawer"
  />
  <KnowledgeSourceViewer
    :open="knowledgeSourceViewerOpen"
    :bundle="activeKnowledgeSourceBundle"
    @close="closeKnowledgeSourceViewer"
  />
</template>

<style scoped>
.prompt-guide {
  position: relative;
  margin-top: 14px;
  display: flex;
  flex-direction: column;
  align-items: center;
  z-index: 20;
}
.prompt-guide-tabs {
  display: flex;
  flex-wrap: wrap;
  justify-content: center;
  gap: 8px;
}
.prompt-guide-tab {
  display: inline-flex;
  min-height: 38px;
  align-items: center;
  gap: 7px;
  border-radius: 999px;
  border: 1px solid #e5e7eb;
  background: rgba(255, 255, 255, 0.92);
  padding: 0 12px;
  color: #475569;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  box-shadow: 0 8px 22px rgba(15, 23, 42, 0.06);
  transition: border-color 180ms ease, background-color 180ms ease, color 180ms ease, box-shadow 180ms ease;
}
.prompt-guide-tab:hover,
.prompt-guide-tab:focus-visible,
.prompt-guide-tab.is-active {
  border-color: #bfdbfe;
  background: #eff6ff;
  color: #1d4ed8;
  box-shadow: 0 10px 26px rgba(37, 99, 235, 0.12);
  outline: none;
}
.prompt-guide-tab-icon,
.prompt-guide-item-icon,
.prompt-guide-notice-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex: 0 0 auto;
}
.prompt-guide-tab-icon :deep(svg) {
  display: block;
  width: 16px;
  height: 16px;
}
.prompt-guide-panel {
  position: absolute;
  top: calc(100% + 9px);
  left: 50%;
  z-index: 30;
  display: flex;
  width: min(720px, calc(100vw - 48px));
  transform: translateX(-50%);
  flex-direction: column;
  align-items: stretch;
  gap: 10px;
}
.prompt-guide-panel::before {
  content: "";
  position: absolute;
  top: -7px;
  left: 50%;
  height: 14px;
  width: 34px;
  transform: translateX(-50%);
  border: 1px solid #dbeafe;
  border-bottom: 0;
  border-radius: 18px 18px 0 0;
  background: rgba(255, 255, 255, 0.96);
  box-shadow: 0 -4px 12px rgba(37, 99, 235, 0.04);
}
.prompt-guide-arc {
  position: relative;
  display: grid;
  width: 100%;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px 12px;
  overflow: hidden;
  border: 1px solid #dbe5f1;
  border-radius: 22px;
  background:
    linear-gradient(180deg, rgba(255, 255, 255, 0.98) 0%, rgba(248, 251, 255, 0.98) 100%);
  padding: 16px 18px 18px;
  box-shadow: 0 20px 46px rgba(15, 23, 42, 0.11), 0 1px 0 rgba(255, 255, 255, 0.9) inset;
}
.prompt-guide-arc::before {
  content: "";
  position: absolute;
  inset: 0;
  border-radius: inherit;
  background:
    radial-gradient(80% 52% at 50% 0%, rgba(219, 234, 254, 0.58) 0%, rgba(219, 234, 254, 0) 70%),
    radial-gradient(75% 55% at 50% 120%, rgba(226, 232, 240, 0.42) 0%, rgba(226, 232, 240, 0) 68%);
  pointer-events: none;
}
.prompt-guide-arc::after {
  content: "";
  position: absolute;
  left: 16px;
  right: 16px;
  bottom: 0;
  height: 1px;
  background: linear-gradient(90deg, transparent, rgba(148, 163, 184, 0.34), transparent);
  pointer-events: none;
}
.prompt-guide-item {
  position: relative;
  z-index: 1;
  display: inline-flex;
  min-height: 42px;
  min-width: 0;
  align-items: center;
  justify-content: center;
  gap: 7px;
  border-radius: 999px;
  border: 1px solid #dbe5f1;
  background: rgba(255, 255, 255, 0.82);
  padding: 0 12px;
  color: #1f2937;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  transition: border-color 180ms ease, background-color 180ms ease, color 180ms ease, box-shadow 180ms ease;
}
.prompt-guide-item:hover,
.prompt-guide-item:focus-visible {
  border-color: #bfdbfe;
  background: #ffffff;
  color: #1d4ed8;
  box-shadow: 0 8px 20px rgba(37, 99, 235, 0.10);
  outline: none;
}
.prompt-guide-item.is-locked {
  color: #64748b;
  background: rgba(248, 250, 252, 0.92);
}
.prompt-guide-item.is-locked:hover,
.prompt-guide-item.is-locked:focus-visible {
  border-color: #cbd5e1;
  color: #334155;
  box-shadow: 0 8px 20px rgba(15, 23, 42, 0.08);
}
.prompt-guide-item-icon :deep(svg) {
  display: block;
  width: 17px;
  height: 17px;
}
.prompt-guide-item-label {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.prompt-guide-lock {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  border-radius: 999px;
  background: #f1f5f9;
  padding: 2px 6px;
  color: #64748b;
  font-size: 11px;
  font-weight: 700;
}
.prompt-guide-lock :deep(svg) {
  display: block;
  width: 11px;
  height: 11px;
}
.prompt-guide-notice {
  display: flex;
  width: 100%;
  align-items: center;
  gap: 10px;
  border-radius: 14px;
  border: 1px solid #dbeafe;
  background: #f8fbff;
  padding: 10px 12px;
  color: #334155;
  box-shadow: 0 10px 26px rgba(37, 99, 235, 0.08);
}
.prompt-guide-notice-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  height: 30px;
  width: 30px;
  border-radius: 10px;
  background: #eff6ff;
  color: #2563eb;
}
.prompt-guide-notice-icon :deep(svg) {
  display: block;
  width: 17px;
  height: 17px;
}
.prompt-guide-notice-title {
  color: #0f172a;
  font-size: 13px;
  font-weight: 700;
}
.prompt-guide-notice-desc {
  margin-top: 2px;
  color: #64748b;
  font-size: 12px;
  line-height: 1.4;
}
.prompt-guide-config-btn {
  flex: 0 0 auto;
  min-height: 34px;
  border-radius: 999px;
  background: #2563eb;
  padding: 0 12px;
  color: #fff;
  font-size: 12px;
  font-weight: 700;
  cursor: pointer;
  transition: background-color 180ms ease, box-shadow 180ms ease;
}
.prompt-guide-config-btn:hover,
.prompt-guide-config-btn:focus-visible {
  background: #1d4ed8;
  box-shadow: 0 8px 18px rgba(37, 99, 235, 0.22);
  outline: none;
}
.assistant-loading-dot {
  width: 10px;
  height: 10px;
  border-radius: 9999px;
  background: #3b82f6;
  /* GPU-only animation avoids per-frame box-shadow repaint churn during streaming. */
  animation: breatheDot 1.2s ease-in-out infinite;
  will-change: transform, opacity;
}
@keyframes breatheDot {
  0%, 100% { transform: scale(0.9); opacity: 0.8; }
  50%      { transform: scale(1.05); opacity: 1; }
}
@media (prefers-reduced-motion: reduce) {
  .assistant-loading-dot { animation: none; opacity: 0.9; }
  .prompt-guide-tab,
  .prompt-guide-item,
  .prompt-guide-config-btn {
    transition: none;
  }
}
@media (max-width: 640px) {
  .prompt-guide {
    margin-top: 12px;
  }
  .prompt-guide-tabs {
    gap: 6px;
  }
  .prompt-guide-panel {
    width: min(520px, calc(100vw - 24px));
  }
  .prompt-guide-tab {
    min-height: 36px;
    padding: 0 10px;
    font-size: 12px;
  }
  .prompt-guide-arc {
    grid-template-columns: repeat(2, minmax(0, 1fr));
    border-radius: 18px;
    padding: 12px;
  }
  .prompt-guide-item {
    justify-content: flex-start;
    font-size: 12px;
  }
  .prompt-guide-notice {
    align-items: flex-start;
  }
}
</style>
