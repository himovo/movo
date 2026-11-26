<script setup lang="ts">
import { ref, watch } from 'vue'
import type { ArtifactItem } from '../../features/execution-v3/domain/delivery'
import { signDocument } from '../../api/documents'
import { t } from '../../composables/i18n'
import AssistantImagePreview from '../chat/AssistantImagePreview.vue'

const props = defineProps<{ artifact: ArtifactItem; compact?: boolean }>()
const emit = defineEmits<{ (event: 'download', artifact: ArtifactItem): void }>()
const src = ref('')
const failed = ref(false)
const preview = ref(false)
let generation = 0

function safeUrl(value: string): string {
  try {
    const url = new URL(value, window.location.origin)
    return ['http:', 'https:'].includes(url.protocol) ? url.href : ''
  } catch { return '' }
}

watch(() => [props.artifact.object_path, props.artifact.signed_url, props.artifact.url], async () => {
  const current = ++generation
  failed.value = false
  preview.value = false
  src.value = safeUrl(props.artifact.signed_url || props.artifact.url || '')
  if (!props.artifact.object_path) return
  try {
    const result = await signDocument({ user_id: '', object_path: props.artifact.object_path })
    if (current === generation && result.url) {
      src.value = safeUrl(result.url)
      failed.value = false
    }
  } catch { /* Keep the delivered URL when renewal is temporarily unavailable. */ }
}, { immediate: true })

function download() {
  emit('download', { ...props.artifact, url: src.value || props.artifact.url, signed_url: src.value || props.artifact.signed_url })
}
</script>

<template>
  <div class="max-w-full">
    <div v-if="!compact && src && !failed" class="image-artifact-thumbnail">
      <button type="button" class="image-artifact-open" :aria-label="t('ui.preview')" @click="preview = true">
        <img :src="src" :alt="artifact.title || artifact.filename || t('artifact.image')" loading="lazy" @error="failed = true" />
      </button>
      <div class="image-artifact-actions">
        <button type="button" class="image-artifact-action" @click="preview = true">{{ t('ui.preview') }}</button>
        <button type="button" class="image-artifact-action image-artifact-download" :aria-label="t('ui.download')" :title="t('ui.download')" @click="download">
          <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
            <path d="M12 3v12m-4-4 4 4 4-4M5 15v5h14v-5" />
          </svg>
        </button>
      </div>
    </div>
    <div v-else class="flex w-fit max-w-full items-center gap-4 rounded-xl border border-slate-200 px-4 py-2">
      <span class="min-w-0 truncate text-sm text-slate-500">{{ compact ? t('artifact.image') : t('artifact.imageUnavailable') }}</span>
      <button v-if="src && !failed" type="button" class="min-h-11 text-xs text-slate-600" @click="preview = true">{{ t('ui.preview') }}</button>
      <button type="button" class="min-h-11 text-xs text-blue-600" @click="download">{{ t('ui.download') }}</button>
    </div>
    <Teleport to="body">
      <AssistantImagePreview v-if="preview && src" :src="src" :object-path="artifact.object_path" :alt="artifact.title || artifact.filename || t('artifact.image')" @close="preview = false" />
    </Teleport>
  </div>
</template>

<style scoped>
.image-artifact-thumbnail {
  position: relative;
  width: fit-content;
  max-width: 100%;
  overflow: hidden;
  border-radius: 20px;
}
.image-artifact-open { display: block; max-width: 100%; cursor: zoom-in; }
.image-artifact-open img {
  display: block;
  width: auto;
  height: auto;
  max-width: min(100%, 640px);
  max-height: 480px;
}
.image-artifact-actions {
  position: absolute;
  inset: auto 12px 12px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  pointer-events: none;
}
.image-artifact-action {
  display: inline-flex;
  min-height: 44px;
  align-items: center;
  justify-content: center;
  padding: 0 16px;
  border-radius: 999px;
  color: white;
  background: rgb(32 32 32 / 65%);
  backdrop-filter: blur(12px);
  pointer-events: auto;
  transition: background 150ms;
  font-size: 14px;
}
.image-artifact-action:hover { background: rgb(32 32 32 / 85%); }
.image-artifact-download { width: 44px; padding: 0; }
.image-artifact-open:focus-visible { outline: 2px solid #3b82f6; outline-offset: -4px; }
.image-artifact-action:focus-visible { outline: 2px solid white; outline-offset: 2px; }
</style>
