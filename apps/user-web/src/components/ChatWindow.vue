<script setup lang="ts">
import type { KnowledgeReference } from '../api/knowledgeReferences'
import { computed, defineAsyncComponent, ref, watch } from 'vue'
import BrowserWorkspace from './browser/BrowserWorkspace.vue'
import CodeHistoryReadOnlyNotice from './code/CodeHistoryReadOnlyNotice.vue'
import CodeHistoryRestoringNotice from './code/CodeHistoryRestoringNotice.vue'
import CodeDraftContextBar from './code/CodeDraftContextBar.vue'
import CodePermissionPicker from './code/CodePermissionPicker.vue'
import ChatComposer from './chat/ChatComposer.vue'
import DocumentEditorDialog from './chat/DocumentEditorDialog.vue'
import UserMessageContent from './chat/UserMessageContent.vue'
import AssistantMessageBody from './chat/AssistantMessageBody.vue'
import ChatTurnInterruptions from './chat/ChatTurnInterruptions.vue'
import AssistantImagePreview from './chat/AssistantImagePreview.vue'
import type { PendingDocument } from './chat/types'
import { useDocumentEditors } from './chat/useDocumentEditors'
import { useAuthoritativeMessages } from './chat/useAuthoritativeMessages'
import PromptGuidePanel from './chat/PromptGuidePanel.vue'
import { usePromptGuide } from './chat/usePromptGuide'
import PresentationEditor from './PresentationEditor.vue'
import EvidenceDrawer from './execution/EvidenceDrawer.vue'
import KnowledgeSourceViewer from './execution/KnowledgeSourceViewer.vue'
import { resolvePermission } from '../composables/useChatStream'
import { useDshToolApprovals } from '../composables/useDshToolApprovals'
import { useUserQuestions } from '../composables/useUserQuestions'
import { useLocale } from '../composables/i18n'
import { useChatModels } from '../composables/useChatModels'
import { useBrowserWorkspace } from '../composables/browser/useBrowserWorkspace'
import type { ExecutionStoreV3 } from '../features/execution-v3/stores/executionStore'
import { ensureMessageExecutionV3 } from '../features/execution-v3/stores/messageExecution'
import type { CodePermissionMode, DshCodeSession, DshExecutionEvent, DshPendingApproval, DshTaskChangeSet, DshWorkspace } from '../platform/types'
import { capabilities } from '../platform'
import type { DesktopToolLauncherKind, DesktopToolTab } from './desktop/desktopToolTabs'
import type { AgentPolicySnapshot } from '../api/auth'
import { useMessageAuthors } from './chat/useMessageAuthors'
import { useEvidenceViewer } from './chat/useEvidenceViewer'
import { useStickyChatScroll } from './chat/useStickyChatScroll'
import type { ChatMessage } from './chat/chatMessage'
import { useChatWindowLifecycle } from './chat/useChatWindowLifecycle'
import { useChatMessageProjection } from './chat/useChatMessageProjection'
import { useChatArtifactActions } from './chat/useChatArtifactActions'
import { resolveArtifactIcon } from '../registries'
import { agentResourceFamilyAvailable } from '../composables/useEnterpriseAccessPolicy'
import type { ForeignRun } from '../composables/sessionRunPresence'

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
  modelInstanceId?: string
  userId?: string
  mainId?: string
  authToken?: string
  active: boolean
  running?: boolean
  foreignRun?: ForeignRun | null
  foreignRunFinished?: boolean
  refreshingSession?: boolean
  stopping?: boolean
  /** T8: transient top-of-conversation notice for a manual-only concurrent-send
   *  409; the store owns the auto-dismiss timer and this never enters the
   *  message thread. */
  busyNotice?: string | null
  /** T9: authoritative shared-session flag wired from `pane.shared` in App.vue.
   *  When true, user rows render author avatar + display name through the
   *  focused UserMessageAuthor child (architecture boundary above). */
  shared?: boolean
  codeWorkspace?: DshWorkspace | null
  codeWorkspaces?: readonly DshWorkspace[]
  codeWorkspacesLoading?: boolean
  codeSession?: DshCodeSession | null
  codeEvents?: DshExecutionEvent[]
  codeApprovals?: DshPendingApproval[]
  codeApprovalBusy?: Record<string, boolean>
  codeError?: string
  codeWorkspaceBusy?: boolean
  codeWorktree?: boolean
  codeSourceRef?: string
  codePermissionMode?: CodePermissionMode
  codeHistoryReadOnly?: boolean
  codeHistoryRestoring?: boolean
  codeHistoryLocation?: 'desktop' | 'remote_sandbox'
  codeHistoryProject?: { workspace_id: string; git_branch: string; worktree: boolean } | null
  codeHistoryLocalFolderUnavailable?: boolean
  desktopBrowserRequest?: number
  browserSessionId?: string
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
  return agentResourceFamilyAvailable(props.agentPolicy, 'skill')
})
const allowTools = computed(() => {
  return agentResourceFamilyAvailable(props.agentPolicy, 'tool')
})
const emit = defineEmits<{
  (e: 'open-skills'): void
  (e: 'open-tools'): void
  (e: 'open-knowledge'): void
  (e: 'send', payload: { text: string; images: File[]; documents: PendingDocument[]; knowledgeQaEnabled: boolean; knowledgeReferences?: KnowledgeReference[]; selectedSkillId?: string; modelId?: string; onRejected?: () => void }): void
  (e: 'stop'): void
  (e: 'refresh-session'): void
  (e: 'clear-intervention'): void
  (e: 'approval-decided'): void
  (e: 'choose-code-workspace'): void
  (e: 'start-local-code-task'): void
  (e: 'select-code-workspace', workspace: DshWorkspace): void
  (e: 'clear-code-workspace'): void
  (e: 'code-worktree', enabled: boolean): void
  (e: 'code-source-ref', fullRef: string): void
  (e: 'code-permission-mode', mode: CodePermissionMode): void
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

type Message = ChatMessage

function ensureExecV3(msg: Message): ExecutionStoreV3 {
  return ensureMessageExecutionV3(msg)
}

const {
  activeEvidenceBundle,
  activeKnowledgeSourceBundle,
  evidenceDrawerOpen,
  knowledgeSourceViewerOpen,
  shouldShowEvidenceTrigger,
  evidenceTriggerTextForMessage,
  openLatestEvidenceDrawer,
  closeEvidenceDrawer,
  closeKnowledgeSourceViewer,
  openKnowledgeSourceFromDrawer,
} = useEvidenceViewer<Message>({
  store: ensureExecV3,
  isGenerating: (index, message) => isAssistantGenerating(index, message),
})


const defaultGreeting = props.initialMessage || 'Hello! I am your AI Agent. How can I help you today?'

// The runtime store is the sole message owner. Keeping a local copied array
// caused new-session runs to remain on the welcome screen while the parent was
// already streaming events into a different array.
const messages = useAuthoritativeMessages<Message>(() => props.initialMessages)
const displayMessages = useChatMessageProjection({
  messages, greeting: defaultGreeting, submittedAnswers: () => questionControl.submitted.value,
})

const { isOwnMessage, authorLabel, sharedAuthorName, sharedAuthorAvatar, foreignRunSpeakerName } = useMessageAuthors({
  sessionId: () => props.sessionId,
  userId: () => props.userId,
  foreignRunInitiatorId: () => props.foreignRun?.initiatorUserId,
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
  getPreferredModelId: () => props.modelInstanceId || '',
})
watch(() => props.modelInstanceId, (modelId) => {
  if (modelId) selectChatModel(modelId)
})
watch(() => props.desktopBrowserRequest, (value, previous) => {
  if (props.active && value && value !== previous) isPreviewExpanded.value = true
})
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
const {
  activeDocument, documentEditorOpen, documentEditorContent,
  documentEditorLoading, documentEditorStatus, presentationEditorOpen,
  presentationBlueprint, presentationBlueprintPath,
  openDocumentEditor, closeDocumentEditor, openPresentationEditor,
  openHtmlPreview, closePresentationEditor, onPresentationExported,
  downloadDocument, confirmPresentationPreview, regenerateDocument,
} = useDocumentEditors({ messages, getUserId: () => props.userId, debugEnabled })
const {
  showScrollButton, stickyState, stickyAssistantMsgId,
  stickyNeedsInitialAlign, markUserScrollIntent, recomputeStickyTurnMinHeight,
  stickyLog, activateStickyForLatestRunningTurn, setMsgRef, handleScroll,
  alignStickyAnchorWithRetry, assistantTurnStyle, scrollToBottom,
  startLayoutObserver, stopLayoutObserver, resetMessageRefs,
} = useStickyChatScroll({
  messages, displayMessages, isLoading, messagesContainer, composerContainer,
})
const isNewSessionView = computed(() => displayMessages.value.length === 0)

const {
  activePromptGuideKey, promptGuideNotice, visiblePromptGuideCategories,
  activePromptGuideCategory, setKnowledgeSourceSummary, selectPromptGuideCategory,
  closePromptGuide, cancelPromptGuideClose, schedulePromptGuideClose,
  usePromptGuideItem, openPromptGuideConfig, loadPromptGuideShortcuts,
  handleShortcutPreferencesUpdated,
} = usePromptGuide({
  allowContent, allowKnowledge, allowTools, locale, composerRef,
  authToken: () => props.authToken,
  userId: () => props.userId,
  openSkills: () => emit('open-skills'),
  openKnowledge: () => emit('open-knowledge'),
  openTools: () => emit('open-tools'),
})


function isAssistantGenerating(idx: number, msg: Message): boolean {
  return !!isLoading.value && msg.role === 'assistant' && idx === displayMessages.value.length - 1
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
const questionControl = useUserQuestions({
  active: () => props.active,
  conversationId: () => props.sessionId,
  codeSessionId: () => props.codeSession?.kernel_session_id,
  token: () => props.authToken,
  running: () => Boolean(props.running || isLoading.value),
  assistantMessageId: () => [...messages.value].reverse().find(message => message.role === 'assistant')?.message_id,
})

const {
  onArtifactOpen, onArtifactEditPresentation,
  onArtifactExportPresentation, onArtifactPreviewHtml, onArtifactDownload,
  downloadMessageArtifact,
} = useChatArtifactActions({
  downloadDocument, openDocumentEditor, openPresentationEditor,
  confirmPresentationPreview, openHtmlPreview,
})

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

useChatWindowLifecycle({
  messages, displayMessages, locale,
  mainId: () => props.mainId, authToken: () => props.authToken,
  sessionId: () => props.sessionId, initialMessages: () => props.initialMessages,
  isLoading, stickyState, stickyNeedsInitialAlign, handleScroll,
  recomputeStickyTurnMinHeight, loadChatModels, loadPromptGuideShortcuts,
  handleShortcutPreferencesUpdated, startLayoutObserver, stopLayoutObserver,
  cancelPromptGuideClose, stickyLog, alignStickyAnchorWithRetry,
  resetBrowserWorkspace, resetMessageRefs, activateStickyForLatestRunningTurn,
})


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
    :session-id="props.browserSessionId || props.sessionId"
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
    <!-- T8: transient concurrent-send notice, in-flow at the top of the
         conversation (never covering messages, never a thread row). The store
         owns the auto-dismiss timer; this is display-only. -->
    <Transition
      enter-active-class="transition duration-200 ease-out"
      enter-from-class="opacity-0 -translate-y-1"
      enter-to-class="opacity-100 translate-y-0"
      leave-active-class="transition duration-150 ease-in"
      leave-from-class="opacity-100 translate-y-0"
      leave-to-class="opacity-0 -translate-y-1"
    >
      <div
        v-if="props.busyNotice"
        class="w-full max-w-4xl mx-auto px-4 md:px-6 pt-3 shrink-0"
        role="status"
        aria-live="polite"
      >
        <div class="flex items-start gap-2.5 rounded-xl border border-gray-200 bg-blue-50 px-3.5 py-2.5 text-sm text-slate-700">
          <svg class="mt-0.5 h-4 w-4 shrink-0 text-blue-500" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
            <circle cx="12" cy="12" r="10" />
            <path d="M12 16v-4" />
            <path d="M12 8h.01" />
          </svg>
          <span class="min-w-0">{{ props.busyNotice }}</span>
        </div>
      </div>
    </Transition>
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
            :class="msg.role === 'user' && isOwnMessage(msg) ? 'justify-end' : 'justify-start'"
            :data-scroll-anchor="stickyState === 'LOCKED' && msg._id === stickyAssistantMsgId ? 'true' : undefined"
            :style="msg.role === 'assistant' ? assistantTurnStyle(msg) : undefined"
          >
          <!-- Message Bubble Container -->
          <div 
            class="relative max-w-[85%] rounded-2xl bg-transparent transition-all duration-200"
            :class="msg.role === 'assistant'
              ? 'py-4 text-gray-900'
              : isOwnMessage(msg) ? 'p-4 text-slate-800' : 'text-slate-800'"
          >
            <AssistantMessageBody
              v-if="msg.role === 'assistant'"
              :message="msg"
              :live="isAssistantGenerating(idx, msg)"
              :code-session="props.codeSession"
              :locale="locale"
              :intervention="idx === displayMessages.length - 1 ? activeIntervention : null"
              :evidence-visible="shouldShowEvidenceTrigger(idx, msg)"
              :evidence-label="evidenceTriggerTextForMessage(msg)"
              @resolve-permission="(requestId, decision) => onPermissionResolve(msg, requestId, decision)"
              @complete-intervention="handleLocalInterventionDone"
              @show-browser="openBrowserForIntervention"
              @download-artifact-path="path => downloadMessageArtifact(msg, path)"
              @open-file="path => emit('open-code-file', path)"
              @image-preview="({ src, alt }) => openImagePreview(src, alt)"
              @review-code-changes="(changes, path) => emit('review-code-changes', changes, path)"
              @changes-undone="changes => { msg._codeChanges = changes; emit('code-workspace-change') }"
              @artifact-open="artifact => onArtifactOpen(artifact, msg, idx)"
              @artifact-edit="artifact => onArtifactEditPresentation(artifact, msg)"
              @artifact-export="artifact => onArtifactExportPresentation(artifact, msg)"
              @artifact-preview="onArtifactPreviewHtml"
              @artifact-download="onArtifactDownload"
              @open-evidence="openLatestEvidenceDrawer(msg)"
            />
            <UserMessageContent
              v-else
              :message="msg"
              :shared="props.shared"
              :own="isOwnMessage(msg)"
              :display-name="sharedAuthorName(msg)"
              :avatar-url="sharedAuthorAvatar(msg)"
              :author-label="authorLabel(msg)"
              :locale="locale"
              :session-id="props.sessionId"
              @image-preview="openImagePreview"
              @schedule="emit('schedule-message', $event)"
            />
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
      <ChatTurnInterruptions
        :questions="questionControl"
        :approvals="approvalControl"
        :foreign-run-active="Boolean(props.foreignRun)"
        :foreign-run-finished="Boolean(props.foreignRunFinished)"
        :foreign-run-speaker-name="foreignRunSpeakerName"
        :refreshing-session="Boolean(props.refreshingSession)"
        :code-error="props.codeError"
        :code-approvals="props.codeApprovals"
        :code-approval-busy="props.codeApprovalBusy"
        @refresh-session="emit('refresh-session')"
        @code-approval="(approvalId, decision, scope) => emit('code-approval', approvalId, decision, scope)"
      />
      <CodeHistoryRestoringNotice v-if="props.codeHistoryRestoring" />
      <CodeHistoryReadOnlyNotice
        v-else-if="props.codeHistoryReadOnly && props.codeHistoryLocation"
        :execution-location="props.codeHistoryLocation"
        :project="props.codeHistoryProject"
        :local-folder-unavailable="props.codeHistoryLocalFolderUnavailable"
        :can-start-local="capabilities.localWorkspacePicker"
        @start-local="emit('start-local-code-task')"
      />
      <ChatComposer
        v-else
        ref="composerRef"
        :active="props.active"
        :running="isLoading"
        :blocked="Boolean(props.foreignRun || props.foreignRunFinished)"
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
        @knowledge-source="setKnowledgeSourceSummary"
      >
        <template #model-actions>
          <CodePermissionPicker v-if="capabilities.codeExecution && (props.codeWorkspace || props.codeSession)"
            :model-value="props.codePermissionMode || 'ask'" :disabled="isLoading || props.codeWorkspaceBusy"
            @update:model-value="(mode) => emit('code-permission-mode', mode)" />
        </template>
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
            :workspaces="props.codeWorkspaces"
            :workspaces-loading="props.codeWorkspacesLoading"
            @choose="emit('choose-code-workspace')"
            @select="(workspace) => emit('select-code-workspace', workspace)"
            @clear="emit('clear-code-workspace')"
            @worktree="(enabled) => emit('code-worktree', enabled)"
            @source-ref="(fullRef) => emit('code-source-ref', fullRef)"
            @branch-updated="(branch) => emit('code-branch-updated', branch)"
          />
        </template>
        <template #prompt-guide>
        <PromptGuidePanel
          v-if="isNewSessionView"
          :active-key="activePromptGuideKey"
          :categories="visiblePromptGuideCategories"
          :active-category="activePromptGuideCategory"
          :notice="promptGuideNotice"
          :select-category="selectPromptGuideCategory"
          :cancel-close="cancelPromptGuideClose"
          :schedule-close="schedulePromptGuideClose"
          :use-item="usePromptGuideItem"
          :open-config="openPromptGuideConfig"
        />
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
  <DocumentEditorDialog
    :open="documentEditorOpen"
    :document="activeDocument"
    :content="documentEditorContent"
    :loading="documentEditorLoading"
    :status="documentEditorStatus"
    @download="activeDocument && downloadDocument(activeDocument)"
    @regenerate="regenerateDocument"
    @close="closeDocumentEditor"
    @update:content="documentEditorContent = $event"
    @clear-status="documentEditorStatus = ''"
  />
  <AssistantImagePreview
    v-if="imagePreviewOpen"
    :src="imagePreviewSrc"
    :alt="imagePreviewAlt"
    @close="closeImagePreview"
  />

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
