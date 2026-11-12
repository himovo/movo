<script setup lang="ts">
import { onBeforeUnmount, onMounted } from 'vue'
import { t } from '../../composables/i18n'
import { authenticatedHeaders } from '../../api/authHeaders'
import { resolveArtifactIcon } from '../../registries'
import PdfDocumentViewer from '../knowledge/PdfDocumentViewer.vue'
import CodeFilePreview from './CodeFilePreview.vue'
import type { ChatFilePreviewState } from '../../api/chatFilePreviews'
import type { DocumentInfo } from './types'
import { useDesktopToolPanelSize } from '../../composables/desktop/useDesktopToolPanelSize'

const props = defineProps<{
  open: boolean
  document: DocumentInfo | null
  state: ChatFilePreviewState | null
  text: string
  busy: boolean
  error: string
}>()
const emit = defineEmits<{ (e: 'close'): void; (e: 'retry'): void; (e: 'download'): void }>()
const panel = useDesktopToolPanelSize()
function onKeydown(event: KeyboardEvent) {
  if (event.key === 'Escape' && props.open) emit('close')
}
onMounted(() => window.addEventListener('keydown', onKeydown))
onBeforeUnmount(() => window.removeEventListener('keydown', onKeydown))
</script>

<template>
    <aside v-if="open && document" class="chat-file-pane relative flex h-full min-w-0 flex-none flex-col border-l border-slate-200 bg-white" :style="{ width: `min(${panel.width.value}, calc(100% - 480px))` }" role="region" :aria-label="t('chat.filePreview.title')">
      <button type="button" class="chat-file-resize absolute inset-y-0 -left-1 z-10 w-2 cursor-col-resize bg-transparent hover:bg-blue-200/50" :aria-label="t('chat.filePreview.resize')" @pointerdown="panel.beginDrag" @keydown="panel.adjustByKeyboard" />
        <header class="flex h-11 shrink-0 items-center gap-2 border-b border-slate-200 bg-white px-3">
          <img :src="resolveArtifactIcon(document.type)" alt="" class="h-5 w-5 shrink-0 object-contain" />
          <span class="min-w-0 flex-1 truncate text-sm font-medium text-slate-800" :title="document.title || document.filename || state?.filename">{{ document.title || document.filename || state?.filename }}</span>
          <button type="button" class="flex h-8 w-8 shrink-0 items-center justify-center rounded-md text-slate-600 hover:bg-slate-100" :aria-label="t('ui.download')" :title="t('ui.download')" @click="emit('download')">
            <svg viewBox="0 0 24 24" class="h-4 w-4" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3v12m-4-4 4 4 4-4M5 17v3h14v-3"/></svg>
          </button>
          <button type="button" class="flex h-8 w-8 shrink-0 items-center justify-center rounded-md text-slate-600 hover:bg-slate-100" :aria-label="t('ui.close')" :title="t('ui.close')" @click="emit('close')">
            <svg viewBox="0 0 24 24" class="h-4 w-4" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><path d="M5 5l14 14M19 5 5 19"/></svg>
          </button>
        </header>
        <div class="min-h-0 flex-1 overflow-auto bg-slate-50">
          <PdfDocumentViewer
            v-if="state?.status === 'ready' && state.url && (state.kind === 'pdf' || state.kind === 'office')"
            class="h-full"
            :url="state.url"
            :title="state.filename"
            :http-headers="state.url.startsWith('blob:') ? {} : authenticatedHeaders()"
          />
          <pre v-else-if="state?.status === 'ready' && state.kind === 'text'" class="whitespace-pre-wrap break-words p-5 text-sm text-slate-800">{{ text }}</pre>
          <CodeFilePreview v-else-if="state?.status === 'ready' && state.kind === 'code'" :content="text" :filename="state.filename" />
          <iframe v-else-if="state?.status === 'ready' && state.kind === 'html'" class="h-full w-full border-0 bg-white" :title="state.filename" :srcdoc="text" sandbox="allow-scripts" referrerpolicy="no-referrer" />
          <div v-else class="flex h-full flex-col items-center justify-center gap-3 p-8 text-center text-sm text-slate-600" role="status" aria-live="polite">
            <template v-if="state?.status === 'queued' || busy">
              <svg class="h-7 w-7 animate-spin text-blue-600" viewBox="0 0 24 24" fill="none" aria-hidden="true"><circle class="opacity-20" cx="12" cy="12" r="9" stroke="currentColor" stroke-width="3"/><path d="M12 3a9 9 0 0 1 9 9" stroke="currentColor" stroke-width="3" stroke-linecap="round"/></svg>
              <span>{{ t(state?.status === 'queued' ? 'chat.filePreview.converting' : 'chat.filePreview.uploading') }}</span>
            </template>
            <span v-else-if="state?.status === 'unsupported'">{{ t('chat.filePreview.unsupported') }}</span>
            <span v-else>{{ t(error === 'unavailable' ? 'chat.filePreview.unavailable' : 'chat.filePreview.failed') }}</span>
            <button v-if="state?.status === 'failed' || error" type="button" class="rounded-lg bg-blue-600 px-4 py-2 text-white" @click="emit('retry')">{{ t('chat.filePreview.retry') }}</button>
          </div>
        </div>
    </aside>
</template>

<style scoped>
@container (max-width: 980px) {
  .chat-file-pane { width: 100% !important; }
  .chat-file-resize { display: none; }
}
</style>
