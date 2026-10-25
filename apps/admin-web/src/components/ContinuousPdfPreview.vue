<template>
  <section class="continuous-pdf">
    <div class="pdf-toolbar">
      <span>{{ t('legacy.pages', { current: currentPage, total: pageCount || '--' }) }}</span>
      <span class="load-hint">{{ t('legacy.scroll_to_load_more') }}</span>
      <span class="toolbar-spacer"></span>
      <button type="button" :disabled="zoom <= .5" :aria-label="t('legacy.zoom_out')" @click="setZoom(zoom - .1)">−</button>
      <span class="zoom-value">{{ Math.round(zoom * 100) }}%</span>
      <button type="button" :disabled="zoom >= 1.8" :aria-label="t('legacy.zoom_in')" @click="setZoom(zoom + .1)">＋</button>
    </div>
    <div ref="viewportRef" class="pdf-viewport" @scroll.passive="scheduleCurrentPageUpdate">
      <div v-if="firstLoadedPage > 1" ref="topSentinelRef" class="load-more">
        {{ loadingMore ? t('additional.loading') : t('legacy.scroll_up_to_load_earlier_pages') }}
      </div>
      <article v-for="page in loadedPages" :key="page" class="pdf-page" :data-page-number="page">
        <canvas :ref="element => setCanvasRef(page, element)" :aria-label="`${title} 第 ${page} 页`"></canvas>
        <span>{{ page }}</span>
      </article>
      <div v-if="lastLoadedPage < pageCount" ref="bottomSentinelRef" class="load-more">
        {{ loadingMore ? t('additional.loading') : t('legacy.scroll_down_to_continue') }}
      </div>
      <div v-if="loading" class="viewer-state">{{ t('additional.loading') }}</div>
      <div v-else-if="errorText" class="viewer-state viewer-error">
        <span>{{ errorText }}</span>
        <button type="button" @click="loadDocument">{{ t('legacy.reload') }}</button>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue';
import { t } from '@/composables/i18n';
import { loadPdfjs } from '@/utils/pdfjs';

const props = defineProps<{
  url: string;
  title: string;
  httpHeaders?: Record<string, string>;
  initialPage?: number | null;
}>();

const PAGE_BATCH_SIZE = 3;
const viewportRef = ref<HTMLDivElement | null>(null);
const topSentinelRef = ref<HTMLDivElement | null>(null);
const bottomSentinelRef = ref<HTMLDivElement | null>(null);
const loading = ref(false);
const loadingMore = ref(false);
const errorText = ref('');
const pageCount = ref(0);
const loadedPages = ref<number[]>([]);
const currentPage = ref(1);
const zoom = ref(1);
const firstLoadedPage = computed(() => loadedPages.value[0] || 0);
const lastLoadedPage = computed(() => loadedPages.value.at(-1) || 0);
const canvases = new Map<number, HTMLCanvasElement>();
const renderTasks = new Map<number, any>();
let loadingTask: any = null;
let pdfDocument: any = null;
let observer: IntersectionObserver | null = null;
let resizeObserver: ResizeObserver | null = null;
let resizeFrame = 0;
let scrollFrame = 0;
let loadSequence = 0;

function batchForPage(value: number) {
  const page = Math.min(Math.max(1, Number(value || 1)), pageCount.value || 1);
  const start = Math.floor((page - 1) / PAGE_BATCH_SIZE) * PAGE_BATCH_SIZE + 1;
  const end = Math.min(pageCount.value, start + PAGE_BATCH_SIZE - 1);
  return Array.from({ length: end - start + 1 }, (_, index) => start + index);
}

async function loadDocument() {
  const sequence = ++loadSequence;
  await destroyDocument();
  loadedPages.value = [];
  canvases.clear();
  pageCount.value = 0;
  currentPage.value = 1;
  errorText.value = '';
  if (!props.url) return;
  loading.value = true;
  try {
    const pdfjs = await loadPdfjs();
    loadingTask = pdfjs.getDocument({
      url: props.url,
      httpHeaders: props.httpHeaders || {},
      rangeChunkSize: 256 * 1024,
      disableAutoFetch: true,
      disableStream: true,
    });
    const document = await loadingTask.promise;
    if (sequence !== loadSequence) return void document.destroy();
    pdfDocument = document;
    pageCount.value = document.numPages;
    await showBatch(batchForPage(Number(props.initialPage || 1)), Number(props.initialPage || 1));
  } catch (error: any) {
    if (sequence === loadSequence) errorText.value = readError(error);
  } finally {
    if (sequence === loadSequence) loading.value = false;
  }
}

async function showBatch(pages: number[], scrollPage?: number) {
  loadedPages.value = pages;
  await nextTick();
  await Promise.all(pages.map(renderPage));
  await nextTick();
  if (scrollPage) scrollToPage(scrollPage);
  scheduleCurrentPageUpdate();
}

async function loadAdjacent(direction: 'before' | 'after') {
  if (!pdfDocument || loadingMore.value) return;
  const start = direction === 'before'
    ? Math.max(1, firstLoadedPage.value - PAGE_BATCH_SIZE)
    : lastLoadedPage.value + 1;
  if (start > pageCount.value || (direction === 'before' && firstLoadedPage.value <= 1)) return;
  const end = direction === 'before'
    ? firstLoadedPage.value - 1
    : Math.min(pageCount.value, start + PAGE_BATCH_SIZE - 1);
  const pages = Array.from({ length: end - start + 1 }, (_, index) => start + index);
  const host = viewportRef.value;
  const previousHeight = host?.scrollHeight || 0;
  loadingMore.value = true;
  try {
    loadedPages.value = direction === 'before' ? [...pages, ...loadedPages.value] : [...loadedPages.value, ...pages];
    await nextTick();
    await Promise.all(pages.map(renderPage));
    if (direction === 'before' && host) host.scrollTop += host.scrollHeight - previousHeight;
    scheduleCurrentPageUpdate();
  } finally {
    loadingMore.value = false;
  }
}

function setCanvasRef(page: number, element: any) {
  if (element instanceof HTMLCanvasElement) canvases.set(page, element);
  else canvases.delete(page);
}

async function renderPage(pageNumber: number) {
  const canvas = canvases.get(pageNumber);
  if (!pdfDocument || !canvas || !viewportRef.value) return;
  try { renderTasks.get(pageNumber)?.cancel?.(); } catch {}
  const page = await pdfDocument.getPage(pageNumber);
  const base = page.getViewport({ scale: 1 });
  const fit = Math.min(1, Math.max(.5, (viewportRef.value.clientWidth - 56) / base.width));
  const viewport = page.getViewport({ scale: fit * zoom.value });
  const outputScale = Math.max(1, window.devicePixelRatio || 1);
  const context = canvas.getContext('2d');
  if (!context) return;
  canvas.width = Math.floor(viewport.width * outputScale);
  canvas.height = Math.floor(viewport.height * outputScale);
  canvas.style.width = `${Math.floor(viewport.width)}px`;
  canvas.style.height = `${Math.floor(viewport.height)}px`;
  const task = page.render({ canvas, canvasContext: context, viewport, transform: outputScale === 1 ? undefined : [outputScale, 0, 0, outputScale, 0, 0] });
  renderTasks.set(pageNumber, task);
  try { await task.promise; } catch (error: any) { if (error?.name !== 'RenderingCancelledException') throw error; }
  finally { if (renderTasks.get(pageNumber) === task) renderTasks.delete(pageNumber); }
}

function setZoom(value: number) {
  zoom.value = Math.min(1.8, Math.max(.5, Number(value.toFixed(1))));
  void Promise.all(loadedPages.value.map(renderPage)).then(scheduleCurrentPageUpdate);
}

function scheduleCurrentPageUpdate() {
  if (scrollFrame) return;
  scrollFrame = requestAnimationFrame(() => {
    scrollFrame = 0;
    updateCurrentPage();
  });
}

function updateCurrentPage() {
  const viewport = viewportRef.value;
  if (!viewport) return;
  const viewportRect = viewport.getBoundingClientRect();
  let visiblePage = currentPage.value;
  let visibleHeight = -1;
  viewport.querySelectorAll<HTMLElement>('[data-page-number]').forEach((element) => {
    const rect = element.getBoundingClientRect();
    const height = Math.max(0, Math.min(rect.bottom, viewportRect.bottom) - Math.max(rect.top, viewportRect.top));
    if (height > visibleHeight) {
      visibleHeight = height;
      visiblePage = Number(element.dataset.pageNumber || visiblePage);
    }
  });
  currentPage.value = visiblePage;
}

function scrollToPage(page: number) {
  viewportRef.value?.querySelector<HTMLElement>(`[data-page-number="${page}"]`)?.scrollIntoView({ block: 'start' });
}

async function openAtPage(page: number) {
  if (!pdfDocument || !page) return;
  if (loadedPages.value.includes(page)) return scrollToPage(page);
  await showBatch(batchForPage(page), page);
}

function readError(error: any) {
  const status = Number(error?.status || 0);
  if (status === 403) return t('additional.access_denied');
  if (status === 409) return t('legacy.generating_online_preview');
  return t('additional.pdf_rendering_failed');
}

async function destroyDocument() {
  for (const task of renderTasks.values()) { try { task?.cancel?.(); } catch {} }
  renderTasks.clear();
  const task = loadingTask;
  const document = pdfDocument;
  loadingTask = null;
  pdfDocument = null;
  try { await task?.destroy?.(); } catch {}
  try { await document?.destroy?.(); } catch {}
}

watch(() => [props.url, props.httpHeaders?.Authorization], () => void loadDocument());
watch(() => Number(props.initialPage || 0), page => { if (page) void openAtPage(page); });
watch([topSentinelRef, bottomSentinelRef], () => {
  observer?.disconnect();
  if (topSentinelRef.value) observer?.observe(topSentinelRef.value);
  if (bottomSentinelRef.value) observer?.observe(bottomSentinelRef.value);
});
onMounted(() => {
  observer = new IntersectionObserver(entries => {
    for (const entry of entries) {
      if (!entry.isIntersecting) continue;
      void loadAdjacent(entry.target === topSentinelRef.value ? 'before' : 'after');
    }
  }, { root: viewportRef.value, rootMargin: '500px 0px' });
  resizeObserver = new ResizeObserver(() => {
    cancelAnimationFrame(resizeFrame);
    resizeFrame = requestAnimationFrame(() => void Promise.all(loadedPages.value.map(renderPage)));
  });
  if (viewportRef.value) resizeObserver.observe(viewportRef.value);
  void loadDocument();
});
onBeforeUnmount(() => {
  loadSequence += 1;
  cancelAnimationFrame(resizeFrame);
  cancelAnimationFrame(scrollFrame);
  observer?.disconnect();
  resizeObserver?.disconnect();
  void destroyDocument();
});
</script>

<style scoped>
.continuous-pdf{display:flex;height:100%;min-height:0;flex-direction:column;background:#eef1f5}.pdf-toolbar{display:flex;min-height:42px;align-items:center;gap:10px;padding:0 12px;border-bottom:1px solid #dfe4eb;background:#fff;color:#4b5565;font-size:12px}.load-hint{color:#98a2b3}.toolbar-spacer{flex:1}.pdf-toolbar button{display:grid;width:30px;height:30px;padding:0;border:0;border-radius:6px;background:transparent;color:#364152;cursor:pointer;font-size:20px;place-items:center}.pdf-toolbar button:hover:not(:disabled){background:#f1f4f8}.pdf-toolbar button:disabled{cursor:not-allowed;opacity:.35}.zoom-value{min-width:38px;text-align:center}.pdf-viewport{position:relative;flex:1;overflow:auto;padding:16px}.pdf-page{position:relative;width:max-content;margin:0 auto 16px}.pdf-page canvas{display:block;background:#fff;box-shadow:0 2px 10px rgba(31,42,68,.12)}.pdf-page>span{position:absolute;right:8px;bottom:8px;padding:2px 7px;border-radius:10px;background:rgba(25,33,48,.65);color:#fff;font-size:11px}.load-more{display:flex;min-height:52px;align-items:center;justify-content:center;color:#7b8798;font-size:12px}.viewer-state{position:absolute;inset:0;display:flex;align-items:center;justify-content:center;gap:12px;background:rgba(247,249,252,.9);color:#667085}.viewer-error{flex-direction:column}.viewer-error button{padding:6px 12px;border:1px solid #d7deea;border-radius:6px;background:#fff;color:#315fce;cursor:pointer}
</style>
