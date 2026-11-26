<script setup lang="ts">
import { computed, provide } from 'vue'
import { imageEditingKey, imageEditingContext } from './imageEditingContext'
import ExecutionViewV3 from '../../features/execution-v3/components/ExecutionViewV3.vue'
import ArtifactList from '../execution/ArtifactList.vue'
import AssistantMarkdown from './AssistantMarkdown.vue'
import AssistantMessageActions from './AssistantMessageActions.vue'
import CodeTaskChangeCard from '../code/CodeTaskChangeCard.vue'
import LocalBrowserInterventionPrompt from '../execution/LocalBrowserInterventionPrompt.vue'
import { ensureMessageExecutionV3 } from '../../features/execution-v3/stores/messageExecution'
import { visibleAnswerArtifacts } from '../../features/execution-v3/domain/artifactVisibility'
import { withoutCodeChangeArtifacts } from './codeChangeArtifacts'
import { artifactReferences } from './artifactReferences'
import type { ArtifactItem } from '../../features/execution-v3/domain/delivery'
import type { DshCodeSession, DshTaskChangeSet } from '../../platform/types'
import type { Locale } from '../../locales/messages'
import type { ChatMessage } from './chatMessage'
import type { QuotaNotice } from '../../composables/useQuotaNotice'
import type { BrowserAssistanceHandoff } from '../../composables/browser/useBrowserWorkspace'

const props = defineProps<{
  message: ChatMessage
  sessionId?: string
  live: boolean
  connectionLostAt?: number
  codeSession?: DshCodeSession | null
  locale: Locale
  quotaNotice?: QuotaNotice
  evidenceVisible: boolean
  evidenceLabel: string
  intervention?: {
    reason: string
    category: string
    domain?: string
    handoff?: BrowserAssistanceHandoff
  } | null
}>()
const emit = defineEmits<{
  (e: 'resolve-permission', requestId: string, decision: 'allow' | 'deny' | 'always_allow'): void
  (e: 'download-artifact-path', path: string): void
  (e: 'open-file', path: string): void
  (e: 'image-preview', payload: { src: string; alt: string }): void
  (e: 'review-code-changes', changes: DshTaskChangeSet, path?: string): void
  (e: 'changes-undone', changes: DshTaskChangeSet): void
  (e: 'artifact-open', artifact: ArtifactItem): void
  (e: 'artifact-edit', artifact: ArtifactItem): void
  (e: 'artifact-export', artifact: ArtifactItem): void
  (e: 'artifact-preview', artifact: ArtifactItem): void
  (e: 'artifact-download', artifact: ArtifactItem): void
  (e: 'open-evidence'): void
  (e: 'complete-intervention'): void
  (e: 'show-browser'): void
}>()

const store = computed(() => ensureMessageExecutionV3(props.message))
provide(imageEditingKey, computed(() => imageEditingContext(props.sessionId, props.message)))
const artifactPaths = computed(() => {
  const state = store.value.state
  const artifacts = withoutCodeChangeArtifacts(visibleAnswerArtifacts(state.artifacts, state.runStatus), props.codeSession ? props.message._codeChanges : undefined)
  return artifactReferences(artifacts)
})

</script>

<template>
  <div class="mb-4">
    <ExecutionViewV3
      :store="store"
      :live="live"
      :connection-lost-at="connectionLostAt"
      :quota-notice="quotaNotice"
      @resolve-permission="(requestId, decision) => emit('resolve-permission', requestId, decision)"
    />
  </div>
  <LocalBrowserInterventionPrompt
    v-if="intervention"
    class="mt-2"
    :category="intervention.category"
    :domain="intervention.domain || intervention.reason"
    :reason="intervention.reason"
    :handoff="intervention.handoff"
    @confirm="emit('complete-intervention')"
    @skip="emit('complete-intervention')"
    @show-browser="emit('show-browser')"
  />
  <AssistantMarkdown
    v-if="message.content"
    class="assistant-content"
    :content="message.content"
    :artifact-paths="artifactPaths"
    :file-references="Boolean(codeSession)"
    @download-artifact="emit('download-artifact-path', $event)"
    @open-file="emit('open-file', $event)"
    @image-preview="emit('image-preview', $event)"
  />
  <CodeTaskChangeCard
    v-if="message._codeChanges && codeSession"
    class="mt-3"
    :session-id="codeSession.kernel_session_id"
    :changes="message._codeChanges"
    :locale="locale === 'en' ? 'en' : 'zh'"
    @review="(changes, path) => emit('review-code-changes', changes, path)"
    @undone="emit('changes-undone', $event)"
  />
  <div class="mt-3">
    <ArtifactList
      :store="store"
      :content="message.content"
      :code-changes="codeSession ? message._codeChanges : undefined"
      @open="emit('artifact-open', $event)"
      @edit="emit('artifact-edit', $event)"
      @export="emit('artifact-export', $event)"
      @preview="emit('artifact-preview', $event)"
      @download="emit('artifact-download', $event)"
    />
    <button
      v-if="evidenceVisible"
      type="button"
      class="mt-2 inline-flex min-h-11 items-center gap-2 rounded-lg border border-slate-200 bg-white px-3 text-sm font-medium text-slate-700 shadow-sm transition hover:border-blue-200 hover:bg-blue-50 hover:text-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500"
      @click="emit('open-evidence')"
    >
      <svg viewBox="0 0 24 24" class="h-4 w-4" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <path d="M8 6h13" />
        <path d="M8 12h13" />
        <path d="M8 18h13" />
        <path d="M3 6h.01" />
        <path d="M3 12h.01" />
        <path d="M3 18h.01" />
      </svg>
      <span>{{ evidenceLabel }}</span>
    </button>
  </div>
  <AssistantMessageActions :message="message" :locale="locale" :live="live" />
</template>
