<script setup lang="ts">
import { computed, inject, nextTick, onMounted, onBeforeUnmount, ref, watch } from 'vue'
import { saveBlobDownload } from '../../utils/desktopResources'
import { t } from '../../composables/i18n'
import ImageEditPanel from './ImageEditPanel.vue'
import { imageEditingKey, type ImageEditingContext } from './imageEditingContext'
import type { DocumentInfo } from './types'
import AddOutline from '@vicons/ionicons5/es/AddOutline'
import RemoveOutline from '@vicons/ionicons5/es/RemoveOutline'
import DownloadOutline from '@vicons/ionicons5/es/DownloadOutline'
import CloseOutline from '@vicons/ionicons5/es/CloseOutline'
import ImageOutline from '@vicons/ionicons5/es/ImageOutline'

const props = defineProps<{ src: string; alt: string; editContext?: ImageEditingContext; objectPath?: string }>()
const inheritedContext = inject(imageEditingKey, undefined)
const editing = computed(() => props.editContext || inheritedContext?.value)
const currentSrc = ref(props.src)
const currentPath = ref(props.objectPath)
watch(() => props.src, value => { currentSrc.value = value; currentPath.value = props.objectPath })
function onEdited(document: DocumentInfo) {
  currentSrc.value = document.signed_url || document.url
  currentPath.value = document.object_path
  zoom.value = 1
}
const emit = defineEmits<{ (event: 'close'): void }>()
const closeButton = ref<HTMLButtonElement | null>(null)
const downloading = ref(false)
const downloadError = ref(false)
const viewport = ref<HTMLDivElement | null>(null)
const viewportSize = ref({ width: 0, height: 0 })
const naturalSize = ref({ width: 0, height: 0 })
const zoom = ref(1)
const baseWidth = computed(() => {
  const { width, height } = naturalSize.value
  if (!width || !height || !viewportSize.value.width || !viewportSize.value.height) return 0
  return Math.min(width, 1400, viewportSize.value.width, width * viewportSize.value.height / height)
})
const displayWidth = computed(() => Math.round(baseWidth.value * zoom.value))
const isOverflowing = computed(() => displayWidth.value > viewportSize.value.width ||
  (displayWidth.value * naturalSize.value.height / naturalSize.value.width) > viewportSize.value.height)

function measureViewport() {
  viewportSize.value = { width: viewport.value?.clientWidth || 0, height: viewport.value?.clientHeight || 0 }
}

function onImageLoad(event: Event) {
  const image = event.target as HTMLImageElement
  naturalSize.value = { width: image.naturalWidth, height: image.naturalHeight }
  measureViewport()
}

function changeZoom(next: number) {
  zoom.value = Math.max(0.5, Math.min(3, Math.round(next * 100) / 100))
}

function onKeydown(event: KeyboardEvent) {
  if (event.key === 'Escape') emit('close')
}

function imageFilename(): string {
  try {
    const name = decodeURIComponent(new URL(currentSrc.value, window.location.href).pathname.split('/').pop() || '')
    return name && /\.(?:png|jpe?g|webp|gif|svg|avif)$/i.test(name) ? name : 'movo-image.png'
  } catch {
    return 'movo-image.png'
  }
}

async function downloadImage() {
  if (downloading.value) return
  downloading.value = true
  downloadError.value = false
  try {
    const response = await fetch(currentSrc.value)
    if (!response.ok) throw new Error(`HTTP ${response.status}`)
    await saveBlobDownload(await response.blob(), imageFilename())
  } catch {
    downloadError.value = true
  } finally {
    downloading.value = false
  }
}

onMounted(() => {
  window.addEventListener('keydown', onKeydown)
  window.addEventListener('resize', measureViewport)
  nextTick(() => { closeButton.value?.focus(); measureViewport() })
})
onBeforeUnmount(() => {
  window.removeEventListener('keydown', onKeydown)
  window.removeEventListener('resize', measureViewport)
})
</script>

<template>
  <Teleport to="body">
    <div class="image-preview-backdrop" role="dialog" aria-modal="true" :aria-label="alt || t('chat.image_preview.title')" @click.self="emit('close')">
      <div class="image-preview-toolbar">
        <div class="image-preview-heading"><ImageOutline aria-hidden="true" /><span>{{ t(editing ? 'imageEdit.title' : 'chat.image_preview.title') }}</span></div>
        <div class="image-preview-controls">
          <div class="image-preview-zoom">
            <button type="button" :aria-label="t('chat.image_preview.zoom_out')" :disabled="zoom <= 0.5" @click="changeZoom(zoom - 0.25)"><RemoveOutline aria-hidden="true" /></button>
            <button type="button" class="image-preview-percent" :aria-label="t('chat.image_preview.reset_zoom')" @click="changeZoom(1)">{{ Math.round(zoom * 100) }}%</button>
            <button type="button" :aria-label="t('chat.image_preview.zoom_in')" :disabled="zoom >= 3" @click="changeZoom(zoom + 0.25)"><AddOutline aria-hidden="true" /></button>
          </div>
          <button type="button" class="image-preview-download" :aria-label="t('chat.image_preview.download')" :title="t('chat.image_preview.download')" :disabled="downloading" @click="downloadImage"><DownloadOutline aria-hidden="true" /><span>{{ t(downloading ? 'chat.image_preview.downloading' : 'ui.download') }}</span></button>
          <span class="image-preview-separator" aria-hidden="true" />
          <button ref="closeButton" type="button" class="image-preview-close" :aria-label="t('chat.image_preview.close')" :title="t('chat.image_preview.close')" @click="emit('close')"><CloseOutline aria-hidden="true" /></button>
        </div>
      </div>
      <div ref="viewport" class="image-preview-viewport" :class="{ 'is-overflowing': isOverflowing }" @click.self="emit('close')">
        <img :src="currentSrc" :alt="alt" class="image-preview-picture" :style="displayWidth ? { width: `${displayWidth}px` } : undefined" @load="onImageLoad" />
      </div>
      <ImageEditPanel v-if="editing" :src="currentSrc" :context="editing" :object-path="currentPath" @edited="onEdited" />
      <p v-if="downloadError" class="image-preview-error" role="alert">{{ t('chat.image_preview.download_failed') }}</p>
    </div>
  </Teleport>
</template>

<style scoped>
.image-preview-backdrop { position: fixed; inset: 0; z-index: 1000; background: rgb(13 16 21 / 96%); backdrop-filter: blur(18px); display: flex; flex-direction: column; gap: 24px; padding: 18px 32px 28px; box-sizing: border-box; -webkit-app-region: no-drag; color: #e5e8ed; }
.image-preview-toolbar { display: flex; flex: none; align-items: center; justify-content: space-between; gap: 16px; }
.image-preview-heading { display: flex; align-items: center; gap: 10px; font-size: 14px; font-weight: 500; color: #b7bec8; letter-spacing: .02em; }
.image-preview-heading svg { width: 18px; height: 18px; color: #858e9b; }
.image-preview-controls { display: flex; align-items: center; gap: 12px; }
.image-preview-toolbar button { display: inline-flex; min-width: 40px; min-height: 40px; align-items: center; justify-content: center; border: 1px solid transparent; border-radius: 10px; color: #c6ccd5; cursor: pointer; transition: color 150ms, background 150ms; }
.image-preview-toolbar button svg { width: 19px; height: 19px; }
.image-preview-toolbar button:hover:not(:disabled) { background: #ffffff0d; color: white; }
.image-preview-toolbar button:focus-visible { outline: 2px solid #93b4f5; outline-offset: 2px; }
.image-preview-toolbar button:disabled { opacity: .35; cursor: not-allowed; }
.image-preview-zoom { display: flex; align-items: center; border: 1px solid #ffffff0d; border-radius: 12px; padding: 2px; background: #ffffff04; }
.image-preview-zoom button { min-height: 34px; min-width: 34px; border-radius: 8px; }
.image-preview-zoom .image-preview-percent { min-width: 60px; font-size: 12px; font-variant-numeric: tabular-nums; }
.image-preview-toolbar .image-preview-download { gap: 7px; padding: 0 13px; border-color: #ffffff16; background: #ffffff06; font-size: 12px; }
.image-preview-separator { width: 1px; height: 20px; background: #ffffff12; }
.image-preview-viewport { display: flex; align-items: center; justify-content: center; width: 100%; flex: 1; min-height: 0; overflow: auto; }
.image-preview-viewport.is-overflowing { display: block; }
.image-preview-picture { display: block; flex: none; max-width: 100%; max-height: 100%; object-fit: contain; border-radius: 14px; box-shadow: 0 20px 80px #00000055, 0 0 0 1px #ffffff0a; }
.is-overflowing .image-preview-picture { max-width: none; max-height: none; margin: auto; }
.image-preview-error { position: absolute; bottom: 20px; border-radius: 8px; background: #fff; color: #b91c1c; padding: 8px 12px; }
/* Native caption controls are composited above web content. */
:global(html.platform-desktop .image-preview-backdrop) { top: max(48px, env(titlebar-area-height, 0px)); }
@media (max-width: 600px) {
  .image-preview-backdrop { padding: 12px 14px max(16px, env(safe-area-inset-bottom)); gap: 16px; }
  .image-preview-toolbar { gap: 8px; }
  .image-preview-heading { gap: 6px; font-size: 12px; }
  .image-preview-heading svg, .image-preview-download span, .image-preview-separator { display: none; }
  .image-preview-controls { gap: 6px; }
  .image-preview-toolbar .image-preview-download { padding: 0; min-width: 40px; }
  .image-preview-percent { min-width: 48px !important; }
}
@media (prefers-reduced-motion: reduce) { .image-preview-toolbar button { transition: none; } }
</style>
