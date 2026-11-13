<template>
  <div class="pdf-viewer">
    <div class="pdf-toolbar">
      <span>{{ t('knowledge.page_count',{current:currentPage,total:pageCount || '--'}) }}</span>
      <span class="load-hint">{{ t('knowledge.scroll_to_load') }}</span>
      <span class="toolbar-spacer" />
      <button type="button" :disabled="zoom <= .6" :aria-label="t('knowledge.zoom_out')" @click="setZoom(zoom - .2)">−</button>
      <span class="zoom-value">{{ Math.round(zoom * 100) }}%</span>
      <button type="button" :disabled="zoom >= 2.4" :aria-label="t('knowledge.zoom_in')" @click="setZoom(zoom + .2)">＋</button>
    </div>

    <div ref="viewportRef" class="pdf-viewport" @scroll.passive="scheduleCurrentPageUpdate">
      <div v-for="page in loadedPages" :key="page" class="pdf-page" :data-page-number="page">
        <canvas :ref="element => setCanvasRef(page, element)" :aria-label="t('knowledge.page_aria',{title,page})" />
        <span>{{ page }}</span>
      </div>
      <div v-if="loadedPages.length < pageCount" ref="loadMoreRef" class="load-more">
        {{ t(loadingMore ? 'knowledge.loading_more' : 'knowledge.keep_scrolling') }}
      </div>
      <div v-if="loading" class="viewer-state">{{ t('knowledge.loading_document') }}</div>
      <div v-else-if="errorText" class="viewer-state viewer-error">
        <span>{{ errorText }}</span>
        <button type="button" @click="loadDocument">{{ t('knowledge.reload') }}</button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { loadPdfjs } from '../../utils/pdfjs'
import { t } from '../../composables/i18n'

const props = defineProps<{
  url: string
  title: string
  httpHeaders?: Record<string, string>
}>()

const viewportRef = ref<HTMLDivElement | null>(null)
const loadMoreRef = ref<HTMLDivElement | null>(null)
const loading = ref(false)
const loadingMore = ref(false)
const errorText = ref('')
const pageCount = ref(0)
const loadedPages = ref<number[]>([])
const currentPage = ref(1)
const zoom = ref(1)
const canvasRefs = new Map<number, HTMLCanvasElement>()
const renderTasks = new Map<number, any>()
const renderQueues = new Map<number, Promise<void>>()
const PAGE_BATCH_SIZE = 3
let loadingTask: any = null
let pdfDocument: any = null
let loadSequence = 0
let resizeObserver: ResizeObserver | null = null
let loadMoreObserver: IntersectionObserver | null = null
let resizeFrame = 0
let scrollFrame = 0

async function loadDocument() {
  const sequence = ++loadSequence
  await destroyDocument()
  pageCount.value = 0
  loadedPages.value = []
  currentPage.value = 1
  canvasRefs.clear()
  errorText.value = ''
  if (!props.url) return
  loading.value = true
  try {
    const pdfjs = await loadPdfjs()
    loadingTask = pdfjs.getDocument({
      url: props.url,
      httpHeaders: props.httpHeaders || {},
      rangeChunkSize: 256 * 1024,
      disableAutoFetch: true,
      disableStream: true,
    })
    const document = await loadingTask.promise
    if (sequence !== loadSequence) {
      await document.destroy()
      return
    }
    pdfDocument = document
    pageCount.value = document.numPages
    await loadNextBatch()
  } catch (error: any) {
    if (sequence === loadSequence) errorText.value = readableError(error)
  } finally {
    if (sequence === loadSequence) loading.value = false
  }
}

function setCanvasRef(pageNumber: number, element: any) {
  if (element instanceof HTMLCanvasElement) canvasRefs.set(pageNumber, element)
  else canvasRefs.delete(pageNumber)
}

async function loadNextBatch() {
  if (!pdfDocument || loadingMore.value || loadedPages.value.length >= pageCount.value) return
  loadingMore.value = true
  try {
    const start = loadedPages.value.length + 1
    const end = Math.min(pageCount.value, start + PAGE_BATCH_SIZE - 1)
    const pages = Array.from({ length: end - start + 1 }, (_, index) => start + index)
    loadedPages.value.push(...pages)
    await nextTick()
    await Promise.all(pages.map(renderPage))
    scheduleCurrentPageUpdate()
  } catch (error: any) {
    errorText.value = readableError(error)
  } finally {
    loadingMore.value = false
  }
}

function renderPage(pageNumber: number): Promise<void> {
  const previous = renderQueues.get(pageNumber) || Promise.resolve()
  const sequence = loadSequence
  const next = previous.catch(() => {}).then(() => renderPageOnce(pageNumber, sequence))
  renderQueues.set(pageNumber, next)
  void next.finally(() => {
    if (renderQueues.get(pageNumber) === next) renderQueues.delete(pageNumber)
  }).catch(() => {})
  return next
}

async function renderPageOnce(pageNumber: number, sequence: number) {
  if (sequence !== loadSequence) return
  const canvas = canvasRefs.get(pageNumber)
  if (!pdfDocument || !canvas || !viewportRef.value) return
  const page = await pdfDocument.getPage(pageNumber)
  if (sequence !== loadSequence || canvasRefs.get(pageNumber) !== canvas) return
  const baseViewport = page.getViewport({ scale: 1 })
  const availableWidth = Math.max(240, viewportRef.value.clientWidth - 32)
  const fitScale = Math.min(1.5, availableWidth / baseViewport.width)
  const viewport = page.getViewport({ scale: fitScale * zoom.value })
  const outputScale = Math.max(1, window.devicePixelRatio || 1)
  const context = canvas.getContext('2d')
  if (!context) return
  canvas.width = Math.floor(viewport.width * outputScale)
  canvas.height = Math.floor(viewport.height * outputScale)
  canvas.style.width = `${Math.floor(viewport.width)}px`
  canvas.style.height = `${Math.floor(viewport.height)}px`
  const renderTask = page.render({
    canvasContext: context,
    viewport,
    transform: outputScale === 1 ? undefined : [outputScale, 0, 0, outputScale, 0, 0],
  })
  renderTasks.set(pageNumber, renderTask)
  try {
    await renderTask.promise
  } catch (error: any) {
    if (error?.name !== 'RenderingCancelledException') throw error
  } finally {
    if (renderTasks.get(pageNumber) === renderTask) renderTasks.delete(pageNumber)
  }
}

function renderLoadedPages() {
  void Promise.all(loadedPages.value.map(renderPage)).then(scheduleCurrentPageUpdate)
}

function scheduleCurrentPageUpdate() {
  if (scrollFrame) return
  scrollFrame = requestAnimationFrame(() => {
    scrollFrame = 0
    updateCurrentPage()
  })
}

function updateCurrentPage() {
  const viewport = viewportRef.value
  if (!viewport) return
  const viewportRect = viewport.getBoundingClientRect()
  let visiblePage = currentPage.value
  let visibleHeight = -1
  viewport.querySelectorAll<HTMLElement>('[data-page-number]').forEach((element) => {
    const rect = element.getBoundingClientRect()
    const height = Math.max(0, Math.min(rect.bottom, viewportRect.bottom) - Math.max(rect.top, viewportRect.top))
    if (height > visibleHeight) {
      visibleHeight = height
      visiblePage = Number(element.dataset.pageNumber || visiblePage)
    }
  })
  currentPage.value = visiblePage
}

function setZoom(value: number) {
  zoom.value = Math.min(2.4, Math.max(.6, Number(value.toFixed(1))))
  renderLoadedPages()
}

function readableError(error: any) {
  const status = Number(error?.status || 0)
  if (status === 403) return t('knowledge.preview_forbidden')
  if (status === 409) return t('knowledge.preview_pending')
  return t('knowledge.preview_failed')
}

async function destroyDocument() {
  for (const task of renderTasks.values()) {
    try { task?.cancel?.() } catch {}
  }
  renderTasks.clear()
  renderQueues.clear()
  const task = loadingTask
  const document = pdfDocument
  loadingTask = null
  pdfDocument = null
  try { await task?.destroy?.() } catch {}
  try { await document?.destroy?.() } catch {}
}

watch([() => props.url, () => props.httpHeaders?.Authorization], () => { void loadDocument() })
watch(loadMoreRef, (element) => {
  loadMoreObserver?.disconnect()
  if (element) loadMoreObserver?.observe(element)
})
onMounted(() => {
  resizeObserver = new ResizeObserver(() => {
    cancelAnimationFrame(resizeFrame)
    resizeFrame = requestAnimationFrame(renderLoadedPages)
  })
  loadMoreObserver = new IntersectionObserver(
    entries => { if (entries.some(entry => entry.isIntersecting)) void loadNextBatch() },
    { root: viewportRef.value, rootMargin: '600px 0px' },
  )
  if (viewportRef.value) resizeObserver.observe(viewportRef.value)
  void loadDocument()
})
onBeforeUnmount(() => {
  loadSequence += 1
  cancelAnimationFrame(resizeFrame)
  cancelAnimationFrame(scrollFrame)
  resizeObserver?.disconnect()
  loadMoreObserver?.disconnect()
  void destroyDocument()
})
</script>

<style scoped>
.pdf-viewer{display:flex;height:100%;min-height:0;flex-direction:column;background:#eef1f5}.pdf-toolbar{display:flex;min-height:42px;align-items:center;gap:10px;padding:0 12px;border-bottom:1px solid #dfe4eb;background:#fff;color:#4b5565;font-size:12px}.load-hint{color:#98a2b3}.pdf-toolbar button{display:grid;width:30px;height:30px;padding:0;border:0;border-radius:6px;background:transparent;color:#364152;cursor:pointer;font-size:20px;place-items:center}.pdf-toolbar button:hover:not(:disabled){background:#f1f4f8}.pdf-toolbar button:disabled{cursor:not-allowed;opacity:.35}.toolbar-spacer{flex:1}.zoom-value{min-width:38px;text-align:center}.pdf-viewport{position:relative;flex:1;overflow:auto;padding:16px}.pdf-page{position:relative;width:max-content;margin:0 auto 16px}.pdf-page canvas{display:block;background:#fff;box-shadow:0 2px 10px rgba(31,42,68,.12)}.pdf-page>span{position:absolute;right:8px;bottom:8px;padding:2px 7px;border-radius:10px;background:rgba(25,33,48,.65);color:#fff;font-size:11px}.load-more{display:flex;min-height:52px;align-items:center;justify-content:center;color:#7b8798;font-size:12px}.viewer-state{position:absolute;inset:0;display:flex;align-items:center;justify-content:center;gap:12px;background:rgba(247,249,252,.86);color:#667085}.viewer-error{flex-direction:column}.viewer-error button{padding:6px 12px;border:1px solid #d7deea;border-radius:6px;background:#fff;color:#315fce;cursor:pointer}
</style>
