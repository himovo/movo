<script setup lang="ts">
import { t } from '../../composables/i18n'
import AssistantMarkdownTree from './AssistantMarkdownTree'
import type { DocumentInfo } from './types'

defineProps<{
  open: boolean
  document: DocumentInfo | null
  content: string
  loading: boolean
  status: 'success' | 'warning' | 'error' | ''
}>()
const emit = defineEmits<{
  (e: 'download'): void
  (e: 'regenerate'): void
  (e: 'close'): void
  (e: 'update:content', value: string): void
  (e: 'clear-status'): void
}>()
</script>

<template>
  <div v-if="open" class="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
    <div class="w-full max-w-5xl rounded-3xl bg-white shadow-xl">
      <div class="flex items-center justify-between border-b border-gray-100 px-6 py-4">
        <div>
          <div class="text-lg font-semibold text-gray-900">{{ document?.title || t('chat.doc_preview') }}</div>
          <div class="text-xs text-gray-400">{{ document?.filename }}</div>
        </div>
        <div class="flex items-center gap-3">
          <button
            class="rounded-full border border-gray-200 px-4 py-1.5 text-xs text-gray-600 hover:text-gray-800"
            @click="emit('download')"
          >
            {{ t('ui.download') }}
          </button>
          <button
            class="rounded-full bg-blue-600 px-4 py-1.5 text-xs text-white hover:bg-blue-700"
            :disabled="loading"
            @click="emit('regenerate')"
          >
            {{ loading ? t('chat.regenerating') : t('chat.regenerate') }}
          </button>
          <button class="text-gray-400 hover:text-gray-600 text-lg" @click="emit('close')">×</button>
        </div>
      </div>
      <div
        v-if="status"
        role="status"
        class="mx-6 mt-4 rounded-lg px-4 py-2 text-sm"
        :class="status === 'success' ? 'bg-green-50 text-green-800' : status === 'warning' ? 'bg-amber-50 text-amber-800' : 'bg-red-50 text-red-800'"
      >
        {{ t(`chat.regenerate_${status}`) }}
      </div>
      <div class="grid grid-cols-2 gap-4 px-6 py-4">
        <div class="flex flex-col">
          <div class="text-xs text-gray-500 mb-2">{{ t('chat.markdown_edit') }}</div>
          <textarea
            :value="content"
            @input="emit('update:content', ($event.target as HTMLTextAreaElement).value); emit('clear-status')"
            class="h-[60vh] w-full rounded-2xl border border-gray-200 p-3 text-sm leading-6 focus:outline-none focus:ring-2 focus:ring-blue-200"
          ></textarea>
        </div>
        <div class="flex flex-col">
          <div class="text-xs text-gray-500 mb-2">{{ t('chat.preview_panel') }}</div>
          <div class="h-[60vh] overflow-y-auto rounded-2xl border border-gray-200 p-4 prose prose-slate max-w-none">
            <AssistantMarkdownTree :content="content" />
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
