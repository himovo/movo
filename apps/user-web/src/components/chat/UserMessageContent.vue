<script setup lang="ts">
import KnowledgeReferenceChips from './knowledge/KnowledgeReferenceChips.vue'
import type { KnowledgeReference } from '../../api/knowledgeReferences'
import AnsweredQuestionMessage from './AnsweredQuestionMessage.vue'
import UserMessageActions from './UserMessageActions.vue'
import UserMessageAuthor from './UserMessageAuthor.vue'
import type { QuestionAnswerEntry } from './questionAnswerHistory'
import type { DocumentInfo } from './types'
import { getDisplayDocuments } from './documentArtifacts'
import { legacyDocumentMarkers } from '../../locales/legacyDocumentMarkers'
import { chatChromeMessages } from '../../locales/chatChromeMessages'
import { formatAppTime } from '../../composables/appTimezone'
import { t, type Locale } from '../../composables/i18n'
import { resolveArtifactPresentation } from '../../registries'

type UserMessage = {
  knowledge_references?: KnowledgeReference[]
  content: string
  question_answer?: QuestionAnswerEntry
  trigger_source?: string
  images?: Array<{ signed_url?: string; url?: string; filename?: string }>
  documents?: DocumentInfo[]
  created_at?: string
}
defineProps<{
  message: UserMessage
  shared: boolean
  own: boolean
  displayName: string | null
  avatarUrl: string | null
  authorLabel: string
  locale: Locale
  sessionId?: string
}>()
const emit = defineEmits<{
  (e: 'image-preview', src: string, alt: string): void
  (e: 'document-preview', document: DocumentInfo): void
  (e: 'schedule', payload: { prompt: string; sessionId?: string }): void
}>()
function getDocPresentation(doc: DocumentInfo) {
  return resolveArtifactPresentation({ ...doc, kind: doc.type })
}
function normalizeUserContent(content: string): string {
  const text = String(content || '')
  let cutIndex = -1
  for (const marker of legacyDocumentMarkers) {
    const index = text.indexOf(marker)
    if (index >= 0 && (cutIndex < 0 || index < cutIndex)) cutIndex = index
  }
  return cutIndex < 0 ? text : text.slice(0, cutIndex).trimEnd()
}
</script>

<template>
  <UserMessageAuthor
    v-if="shared"
    class="mb-1 px-1"
    :class="own ? 'justify-end' : ''"
    :display-name="displayName"
    :avatar-url="avatarUrl"
  />
  <div v-else-if="authorLabel" class="mb-1 px-1 text-xs font-medium text-slate-500">{{ authorLabel }}</div>
  <div class="rounded-2xl rounded-br-sm bg-blue-50 p-4 shadow-sm">
    <div v-if="message.trigger_source === 'scheduled'" class="mb-2 inline-flex items-center gap-1.5 rounded-full bg-blue-100 px-2 py-1 text-xs font-medium text-blue-700">
      <svg viewBox="0 0 24 24" class="h-3.5 w-3.5" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/></svg>
      {{ t('scheduled.autoSent') }}
    </div>
    <AnsweredQuestionMessage v-if="message.question_answer" :entry="message.question_answer" />
    <div v-else class="whitespace-pre-wrap leading-7">{{ normalizeUserContent(message.content) }}</div>
    <KnowledgeReferenceChips :items="message.knowledge_references || []" />
    <div v-if="message.images?.length" class="mt-3 flex flex-wrap gap-2">
    <img
      v-for="(img, imgIdx) in message.images"
      :key="imgIdx"
      :src="img.signed_url || img.url"
      :alt="img.filename || 'uploaded-image'"
      class="h-24 w-auto max-w-[220px] cursor-zoom-in rounded-lg border border-gray-200 object-cover"
      loading="lazy"
      @click="emit('image-preview', img.signed_url || img.url, img.filename || 'uploaded-image')"
    />
    </div>
    <div v-if="message.documents?.length" class="mt-3 space-y-2">
    <button
      type="button"
      v-for="(doc, docIdx) in getDisplayDocuments(message.documents)"
      :key="docIdx"
      class="flex w-full items-center gap-3 rounded-2xl border border-blue-200 bg-blue-50/70 px-4 py-3 text-left shadow-sm hover:bg-blue-100 focus-visible:outline focus-visible:outline-2 focus-visible:outline-blue-500"
      @click="emit('document-preview', doc)"
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
          {{ doc.filename || chatChromeMessages.document[locale](doc.type.toUpperCase()) }}
        </div>
      </div>
      <span class="text-xs font-medium text-blue-700">{{ t('ui.preview') }}</span>
    </button>
    </div>
  </div>
  <UserMessageActions
    v-if="String(message.content || '').trim()"
    class="pointer-events-none absolute right-2 top-full z-10 max-w-full -translate-y-1 opacity-0 transition-opacity duration-150 group-hover/user-message:pointer-events-auto group-hover/user-message:opacity-100 group-focus-within/user-message:pointer-events-auto group-focus-within/user-message:opacity-100"
    :text="message.content"
    :time="formatAppTime(message.created_at, '')"
    @schedule="emit('schedule', { prompt: message.content, sessionId })"
  />
</template>
