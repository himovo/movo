<script setup lang="ts">
import { computed, nextTick, onMounted, onBeforeUnmount, ref } from 'vue'
import { saveBlobDownload } from '../../utils/desktopResources'
import { t } from '../../composables/i18n'

const props = defineProps<{ src: string; alt: string }>()
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
    const name = decodeURIComponent(new URL(props.src, window.location.href).pathname.split('/').pop() || '')
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
    const response = await fetch(props.src)
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
        <button type="button" :aria-label="t('chat.image_preview.zoom_out')" :disabled="zoom <= 0.5" @click="changeZoom(zoom - 0.25)">−</button>
        <button type="button" :aria-label="t('chat.image_preview.reset_zoom')" @click="changeZoom(1)">{{ Math.round(zoom * 100) }}%</button>
        <button type="button" :aria-label="t('chat.image_preview.zoom_in')" :disabled="zoom >= 3" @click="changeZoom(zoom + 0.25)">＋</button>
        <button type="button" :disabled="downloading" @click="downloadImage">{{ t(downloading ? 'chat.image_preview.downloading' : 'chat.image_preview.download') }}</button>
        <button ref="closeButton" type="button" :aria-label="t('chat.image_preview.close')" @click="emit('close')">{{ t('ui.close') }}</button>
      </div>
      <div ref="viewport" class="image-preview-viewport" :class="{ 'is-overflowing': isOverflowing }" @click.self="emit('close')">
        <img :src="src" :alt="alt" class="image-preview-picture" :style="displayWidth ? { width: `${displayWidth}px` } : undefined" @load="onImageLoad" />
      </div>
      <p v-if="downloadError" class="image-preview-error" role="alert">{{ t('chat.image_preview.download_failed') }}</p>
    </div>
  </Teleport>
</template>

<style scoped>
.image-preview-backdrop { position: fixed; inset: 0; z-index: 1000; background: rgba(3, 9, 22, .88); display: flex; flex-direction: column; gap: 16px; padding: 16px 24px 24px; box-sizing: border-box; -webkit-app-region: no-drag; }
.image-preview-toolbar { display: flex; flex: none; justify-content: flex-end; flex-wrap: wrap; gap: 8px; }
.image-preview-toolbar button { border: 1px solid rgba(255,255,255,.28); border-radius: 8px; background: rgba(255,255,255,.12); color: #fff; padding: 7px 14px; cursor: pointer; }
.image-preview-toolbar button:hover:not(:disabled), .image-preview-toolbar button:focus-visible { background: rgba(255,255,255,.25); }
.image-preview-toolbar button:disabled { opacity: .6; cursor: not-allowed; }
.image-preview-viewport { display: flex; align-items: center; justify-content: center; width: 100%; flex: 1; min-height: 0; overflow: auto; }
.image-preview-viewport.is-overflowing { display: block; }
.image-preview-picture { display: block; flex: none; max-width: 100%; max-height: 100%; object-fit: contain; border-radius: 8px; }
.is-overflowing .image-preview-picture { max-width: none; max-height: none; margin: auto; }
.image-preview-error { position: absolute; bottom: 20px; border-radius: 8px; background: #fff; color: #b91c1c; padding: 8px 12px; }
/* Native caption controls are composited above web content. */
:global(html.platform-desktop .image-preview-backdrop) { top: max(48px, env(titlebar-area-height, 0px)); }
</style>
