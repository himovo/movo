<template>
  <div class="preview-page">
    <!-- 将返回按钮、类型图标、文档名字与大小传送到顶部全局 Header 左侧 -->
    <Teleport v-if="headerTeleportReady" to="#header-title-teleport-target">
      <div v-if="document" class="header-doc-title-block">
        <n-button size="small" secondary @click="closePage" style="margin-right: 4px;">
          <template #icon>
            <span class="button-icon" aria-hidden="true">
              <svg viewBox="0 0 24 24"><path d="M19 12H5" /><path d="M12 19l-7-7 7-7" /></svg>
            </span>
          </template>
          {{ t('返回') }}
        </n-button>
        <FileIcon :ext="document.fileExt" :size="20" />
        <span class="header-doc-title" :title="document.name">{{ document.name }}</span>
        <span class="header-doc-meta">{{ formatFileSize(document.fileSize) }}</span>
      </div>
    </Teleport>

    <!-- 将下载操作按钮传送到顶部全局 Header 右侧 -->
    <Teleport v-if="headerTeleportReady" to="#header-actions-teleport-target">
      <n-space :size="8">
        <n-button size="small" secondary :loading="downloading" :disabled="!objectUrl || downloading" @click="downloadFile">
          <template #icon>
            <span class="button-icon" aria-hidden="true">
              <svg viewBox="0 0 24 24"><path d="M12 3v12" /><path d="M7 10l5 5 5-5" /><path d="M5 21h14" /></svg>
            </span>
          </template>
          {{ t('下载') }}
        </n-button>
      </n-space>
    </Teleport>

    <main class="detail-layout" :class="{ 'is-chunks-panel': activePanel === 'chunks' }">
      <section class="preview-shell">
        <n-spin :show="loading && !objectUrl">
          <template v-if="isConverting">
            <section class="converting-preview">
              <div class="converting-icon" aria-hidden="true">
                <svg viewBox="0 0 24 24" class="converting-spin"><path d="M21 12a9 9 0 0 0-15.3-6.4" /><path d="M3 3v5h5" /><path d="M3 12a9 9 0 0 0 15.3 6.4" /><path d="M21 21v-5h-5" /></svg>
              </div>
              <div class="converting-title">{{ t('在线预览生成中') }}</div>
              <div class="converting-copy">{{ t('文档正在进行格式转换，请稍候...系统将自动刷新。') }}</div>
              <n-button type="primary" secondary @click="reload">{{ t('手动刷新') }}</n-button>
            </section>
          </template>

          <template v-else-if="errorText">
            <n-empty :description="errorText">
              <template #extra>
                <n-button type="primary" secondary @click="reload">{{ t('重新加载') }}</n-button>
              </template>
            </n-empty>
          </template>

          <template v-else-if="document && objectUrl">
            <section v-if="previewKind === 'pdf'" class="pdfjs-viewer">
              <div class="pdfjs-pages">
                <div ref="pdfCanvasLayerRef" class="pdfjs-canvas-layer"></div>
                <div v-if="pdfRendering" class="pdfjs-loading" :aria-label="t('加载中')">
                  <span class="pdfjs-loading-spinner" aria-hidden="true"></span>
                </div>
              </div>
              <div class="pdfjs-floating-controls">
                <div class="pdfjs-page-count">{{ pdfPageCount ? `${pdfPageCount} ${t('页')}` : t('加载中') }}</div>
                <n-button size="small" quaternary :disabled="pdfScale <= PDF_MIN_SCALE || pdfRendering" @click="zoomPdf(-0.1)">
                  <template #icon>
                    <span class="button-icon" aria-hidden="true">
                      <svg viewBox="0 0 24 24"><path d="M5 12h14" /></svg>
                    </span>
                  </template>
                </n-button>
                <div class="pdfjs-zoom-value">{{ Math.round(pdfScale * 100) }}%</div>
                <n-button size="small" quaternary :disabled="pdfScale >= PDF_MAX_SCALE || pdfRendering" @click="zoomPdf(0.1)">
                  <template #icon>
                    <span class="button-icon" aria-hidden="true">
                      <svg viewBox="0 0 24 24"><path d="M12 5v14" /><path d="M5 12h14" /></svg>
                    </span>
                  </template>
                </n-button>
              </div>
            </section>
            <div v-else-if="previewKind === 'image'" class="image-preview">
              <img :src="objectUrl" :alt="document.name" />
            </div>
            <NativeDocumentPreview
              v-else-if="previewKind === 'markdown' || previewKind === 'text' || previewKind === 'html'"
              :kind="previewKind"
              :content="textContent"
              :highlight-texts="targetChunk?.text ? [targetChunk.text] : []"
            />
            <section v-else class="unsupported-preview">
              <div class="unsupported-icon" aria-hidden="true">
                <svg viewBox="0 0 24 24"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" /><path d="M14 2v6h6" /><path d="M16 13H8" /><path d="M16 17H8" /></svg>
              </div>
              <div class="unsupported-title">{{ t('当前格式暂不支持在线预览') }}</div>
              <div class="unsupported-copy">{{ t('DOCX/PPTX/XLSX 后续可接入转换预览，当前可下载查看。') }}</div>
              <n-button type="primary" secondary :loading="downloading" :disabled="downloading" @click="downloadFile">
                <template #icon>
                  <span class="button-icon" aria-hidden="true">
                    <svg viewBox="0 0 24 24"><path d="M12 3v12" /><path d="M7 10l5 5 5-5" /><path d="M5 21h14" /></svg>
                  </span>
                </template>
                {{ t('下载查看') }}
              </n-button>
            </section>
          </template>

          <section v-else-if="document" class="preview-placeholder"></section>
        </n-spin>
      </section>

      <aside class="detail-sidebar">
        <section class="detail-panel">
          <section v-if="activePanel === 'detail'" class="detail-card">
            <div class="detail-card-title">{{ t('文档详情') }}</div>
            <div class="meta-list">
              <div class="meta-row meta-row-full">
                <span>{{ t('文件名') }}</span>
                <strong>{{ document?.originalFilename || '-' }}</strong>
              </div>
              <div class="meta-grid">
                <div class="meta-row">
                  <span>{{ t('类型') }}</span>
                  <div style="margin-top: 4px; display: inline-flex;">
                    <FileIcon v-if="document" :ext="document.fileExt" :show-label="true" />
                    <span v-else>-</span>
                  </div>
                </div>
                <div class="meta-row">
                  <span>{{ t('大小') }}</span>
                  <strong>{{ formatFileSize(document?.fileSize || 0) }}</strong>
                </div>
                <div class="meta-row">
                  <span>{{ t('存储') }}</span>
                  <strong>{{ document?.storageType === 'oss' ? 'OSS' : t('本地') }}</strong>
                </div>
                <div class="meta-row">
                  <span>{{ t('上传人') }}</span>
                  <strong>{{ document?.createdByName || '-' }}</strong>
                </div>
                <div class="meta-row">
                  <span>{{ t('更新时间') }}</span>
                  <strong>{{ formatAdminDateTime(document?.updatedAt, '-') }}</strong>
                </div>
                <div class="meta-row">
                  <span>{{ t('状态') }}</span>
                  <div style="margin-top: 4px; display: inline-flex;">
                    <DocumentStatus v-if="document" :row="document" @retry="retryParse" />
                    <span v-else>-</span>
                  </div>
                </div>
                <div class="meta-row">
                  <span>{{ t('预览状态') }}</span>
                  <strong>{{ previewStatusLabel(document?.previewStatus || 'not_required') }}</strong>
                </div>
                <div class="meta-row">
                  <span>{{ t('分段状态') }}</span>
                  <strong>{{ processLabel(document?.chunkStatus || 'not_started') }}</strong>
                </div>
                <div class="meta-row">
                  <span>{{ t('分段数量') }}</span>
                  <strong>{{ document?.chunkCount || 0 }}</strong>
                </div>
              </div>
            </div>
          </section>

          <section v-else class="chunks-card">
            <div class="chunks-head">
              <div>
                <div class="detail-card-title">{{ t('文档分段') }}</div>
                <div class="chunks-subtitle">{{ chunkTotalText }}</div>
              </div>
              <n-button size="small" secondary :loading="chunksLoading" @click="loadChunks">
                <template #icon>
                  <span class="button-icon" aria-hidden="true">
                    <svg viewBox="0 0 24 24"><path d="M21 12a9 9 0 0 0-15.3-6.4" /><path d="M3 3v5h5" /><path d="M3 12a9 9 0 0 0 15.3 6.4" /><path d="M21 21v-5h-5" /></svg>
                  </span>
                </template>
              </n-button>
            </div>

            <section v-if="targetChunkId" class="source-target-card">
              <div class="source-target-head">
                <span class="source-target-icon" aria-hidden="true">
                  <svg viewBox="0 0 24 24"><path d="M12 20h9" /><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4Z" /></svg>
                </span>
                <div class="source-target-title">{{ t('当前依据') }}</div>
              </div>
              <div class="source-target-meta">
                <span>{{ targetChunkId }}</span>
                <span v-if="targetPageNo">{{ t('第 {page} 页', { page: targetPageNo }) }}</span>
              </div>
              <div v-if="targetSourceText" class="source-target-path">{{ targetSourceText }}</div>
              <pre v-if="targetChunk" class="source-target-text">{{ targetChunk.text }}</pre>
              <div v-else-if="targetChunkLoading" class="source-target-loading">{{ t('依据加载中') }}</div>
            </section>

            <div class="chunks-filter">
              <n-input
                v-model:value="chunkKeyword"
                size="small"
                clearable
                :placeholder="t('搜索分段内容')"
                @keyup.enter="handleChunkSearch"
                @clear="handleChunkSearch"
              >
                <template #prefix>
                  <span class="input-icon" aria-hidden="true">
                    <svg viewBox="0 0 24 24"><path d="m21 21-4.35-4.35" /><circle cx="11" cy="11" r="7" /></svg>
                  </span>
                </template>
              </n-input>
            </div>

            <n-spin :show="chunksLoading">
              <section v-if="document && document.parseStatus === 'failed'" class="chunks-empty">
                <div class="empty-icon" aria-hidden="true">
                  <svg viewBox="0 0 24 24"><path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z" /><path d="M12 9v4" /><path d="M12 17h.01" /></svg>
                </div>
                <div class="empty-title">{{ t('解析失败') }}</div>
                <div class="empty-copy">{{ document.parseError || t('请重新上传或稍后重试。') }}</div>
              </section>

              <section v-else-if="document && document.chunkStatus !== 'succeeded'" class="chunks-empty">
                <div class="empty-icon empty-icon-running" aria-hidden="true">
                  <svg viewBox="0 0 24 24"><path d="M21 12a9 9 0 0 0-15.3-6.4" /><path d="M3 3v5h5" /><path d="M3 12a9 9 0 0 0 15.3 6.4" /><path d="M21 21v-5h-5" /></svg>
                </div>
                <div class="empty-title">{{ t('分段生成中') }}</div>
                <div class="empty-copy">{{ t('解析完成后，这里会自动展示 MongoDB 中保存的分段。') }}</div>
              </section>

              <section v-else-if="!chunks.length" class="chunks-empty">
                <div class="empty-icon" aria-hidden="true">
                  <svg viewBox="0 0 24 24"><path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20" /><path d="M4 4.5A2.5 2.5 0 0 1 6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5z" /><path d="M9 10h6" /><path d="M9 14h4" /></svg>
                </div>
                <div class="empty-title">{{ t('暂无分段') }}</div>
                <div class="empty-copy">{{ t('当前文档没有可展示的分段内容。') }}</div>
              </section>

              <div v-else class="chunk-list">
                <article
                  v-for="chunk in displayChunks"
                  :key="chunk.id"
                  class="chunk-item"
                  :class="{ 'is-target': chunk.chunkIds.includes(targetChunkId) }"
                  :data-chunk-id="chunk.chunkId"
                >
                  <div class="chunk-item-head">
                    <div class="chunk-index">#{{ String(chunk.ordinal + 1).padStart(3, '0') }}</div>
                    <div class="chunk-badges">
                      <span v-if="isImageDerivedChunk(chunk)" class="chunk-badge chunk-badge-image">{{ t('图片 OCR') }}</span>
                      <span class="chunk-badge">{{ chunk.contentType || 'text' }}</span>
                      <span v-if="chunk.rowCount > 1" class="chunk-badge">{{ chunk.rowCount }} {{ t('行') }}</span>
                      <span v-if="chunk.pageNo" class="chunk-badge">{{ t('第 {page} 页', { page: chunk.pageNo }) }}</span>
                      <button
                        v-if="isImageDerivedChunk(chunk) && ['image', 'pdf'].includes(previewKind) && objectUrl"
                        type="button"
                        class="chunk-image-button"
                        @click="openChunkSourceImage(chunk)"
                      >
                        <svg viewBox="0 0 24 24" aria-hidden="true"><rect x="3" y="3" width="18" height="18" rx="2" /><circle cx="8.5" cy="8.5" r="1.5" /><path d="m21 15-5-5L5 21" /></svg>
                        {{ t('查看图片') }}
                      </button>
                    </div>
                  </div>
                  <div v-if="chunk.titlePath.length" class="chunk-title-path">{{ chunk.titlePath.join(' / ') }}</div>
                  <pre class="chunk-text">{{ chunk.text }}</pre>
                </article>
              </div>
            </n-spin>

            <n-pagination
              v-if="chunkPagination.total > chunkPagination.pageSize"
              v-model:page="chunkPagination.page"
              v-model:page-size="chunkPagination.pageSize"
              :item-count="chunkPagination.total"
              :page-sizes="[10, 20, 50]"
              size="small"
              show-size-picker
              class="chunks-pagination"
              @update:page="loadChunks"
              @update:page-size="handleChunkPageSizeChange"
            />
          </section>
        </section>

        <nav class="detail-rail" :aria-label="t('详情导航')">
          <button
            type="button"
            class="rail-button"
            :class="{ active: activePanel === 'detail' }"
            :title="t('文档详情')"
            :aria-label="t('文档详情')"
            @click="activePanel = 'detail'"
          >
            <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" /><path d="M14 2v6h6" /><path d="M16 13H8" /><path d="M16 17H8" /></svg>
          </button>
          <button
            type="button"
            class="rail-button"
            :class="{ active: activePanel === 'chunks' }"
            :title="t('文档分段')"
            :aria-label="t('文档分段')"
            @click="openChunksPanel"
          >
            <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 6h16" /><path d="M4 12h16" /><path d="M4 18h10" /><path d="M3 4v4" /><path d="M3 10v4" /><path d="M3 16v4" /></svg>
            <span v-if="document?.chunkCount" class="rail-count">{{ document.chunkCount }}</span>
          </button>
        </nav>
      </aside>
    </main>

    <n-modal v-model:show="imagePreviewVisible" class="chunk-image-modal">
      <div class="chunk-image-modal-body">
        <button type="button" class="chunk-image-modal-close" :aria-label="t('关闭')" @click="imagePreviewVisible = false">×</button>
        <n-spin :show="imagePreviewLoading">
          <img v-if="imagePreviewUrl" :src="imagePreviewUrl" :alt="document?.name || t('图片来源')" />
        </n-spin>
      </div>
    </n-modal>
  </div>
</template>

<script setup lang="ts">
import { computed, markRaw, nextTick, onBeforeUnmount, onMounted, reactive, ref, shallowRef, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import axios from 'axios';
import * as pdfjsLib from 'pdfjs-dist/legacy/build/pdf.mjs';
import { apiClient } from '@/api/client';
import {
  fetchKnowledgeDocument,
  fetchKnowledgeDocumentChunk,
  fetchKnowledgeDocumentChunks,
  retryKnowledgeDocumentParse,
  type KnowledgeDocumentChunkItem,
  type KnowledgeDocumentItem,
} from '@/api/knowledge-documents';
import { t } from '@/composables/i18n';
import { formatAdminDateTime } from '@/composables/adminTimezone';
import FileIcon from '@/components/FileIcon.vue';
import DocumentStatus from '@/components/DocumentStatus.vue';
import NativeDocumentPreview from '@/components/NativeDocumentPreview.vue';

const pdfWorkerUrl = `${import.meta.env.BASE_URL}vendor/pdfjs/pdf.worker.min.mjs`;
pdfjsLib.GlobalWorkerOptions.workerSrc = pdfWorkerUrl;

interface DisplayChunkItem extends KnowledgeDocumentChunkItem {
  chunkIds: string[];
  rowCount: number;
}

const route = useRoute();
const router = useRouter();
const loading = ref(false);
const document = ref<KnowledgeDocumentItem | null>(null);
const objectUrl = ref('');
const textContent = ref('');
const errorText = ref('');
const isConverting = ref(false);
const pollTimer = ref<number | null>(null);
const downloading = ref(false);
const pdfCanvasLayerRef = ref<HTMLDivElement | null>(null);
const pdfDocument = shallowRef<any>(null);
const pdfBlob = ref<Blob | null>(null);
const pdfScale = ref(1);
const PDF_MIN_SCALE = 0.4;
const PDF_MAX_SCALE = 1.8;
const PDF_VIEWER_HORIZONTAL_PADDING = 60;
const pdfPageCount = ref(0);
const pdfRendering = ref(false);
const pdfScaleTouched = ref(false);
let pdfRenderSeq = 0;
const headerTeleportReady = ref(false);
const activePanel = ref<'detail' | 'chunks'>('detail');
const chunkStage = 'rag';
const chunksLoading = ref(false);
const chunks = ref<KnowledgeDocumentChunkItem[]>([]);
const imagePreviewVisible = ref(false);
const imagePreviewLoading = ref(false);
const imagePreviewUrl = ref('');
const targetChunk = ref<KnowledgeDocumentChunkItem | null>(null);
const targetChunkLoading = ref(false);
const chunkKeyword = ref('');
const chunkPagination = reactive({
  page: 1,
  pageSize: 20,
  total: 0,
});

const documentId = computed(() => String(route.params.id || ''));
const targetChunkId = computed(() => String(route.query.chunkId || '').trim());
const targetPageNo = computed(() => {
  const value = Number(route.query.pageNo || targetChunk.value?.pageNo || 0);
  return Number.isFinite(value) && value > 0 ? value : null;
});
const chunkTotalText = computed(() => {
  const fallback = document.value?.ragChunkCount || document.value?.chunkCount || 0;
  return `共 ${chunkPagination.total || fallback} 个分段`;
});

const displayChunks = computed<DisplayChunkItem[]>(() => {
  const output: DisplayChunkItem[] = [];
  const tableGroups = new Map<string, DisplayChunkItem>();
  for (const chunk of chunks.value) {
    const tableContext = (chunk.metadata || {}).tableContext || {};
    const tableRef = String(tableContext.tableRef || '').trim();
    if (chunk.contentType === 'table_row' && tableRef) {
      const existing = tableGroups.get(tableRef);
      if (existing) {
        existing.chunkIds.push(chunk.chunkId);
        existing.rowCount += 1;
        existing.text = mergeTableRowMarkdown(existing.text, chunk.text);
        continue;
      }
      const group: DisplayChunkItem = {
        ...chunk,
        id: `${chunk.documentId}:table:${tableRef}`,
        contentType: 'table',
        chunkIds: [chunk.chunkId],
        rowCount: 1,
        metadata: {
          ...chunk.metadata,
          tableGroup: {
            tableRef,
            displayMode: 'grouped',
          },
        },
      };
      tableGroups.set(tableRef, group);
      output.push(group);
      continue;
    }
    output.push({ ...chunk, chunkIds: [chunk.chunkId], rowCount: 1 });
  }
  return output;
});

const targetSourceText = computed(() => {
  if (!targetChunkId.value) return '';
  if (targetChunk.value?.titlePath?.length) {
    return targetChunk.value.titlePath.join(' / ');
  }
  return targetPageNo.value ? t('已定位到第 {page} 页', { page: targetPageNo.value }) : t('已定位到引用分段');
});
const previewKind = computed(() => {
  const mime = document.value?.mimeType || '';
  const previewMime = document.value?.previewMimeType || '';
  const ext = (document.value?.fileExt || '').toLowerCase();
  const effectiveMime = String(previewMime || mime).toLowerCase();
  if (effectiveMime.includes('pdf') || ext === 'pdf' || ['doc', 'docx', 'xls', 'xlsx', 'ppt', 'pptx'].includes(ext)) return 'pdf';
  if (effectiveMime.includes('markdown') || ['md', 'markdown'].includes(ext)) return 'markdown';
  if (effectiveMime.includes('html') || ['html', 'htm'].includes(ext)) return 'html';
  if (mime.startsWith('image/') || ['png', 'jpg', 'jpeg', 'webp', 'gif'].includes(ext)) return 'image';
  if (effectiveMime.startsWith('text/') || ['txt', 'csv', 'json', 'tsv', 'log'].includes(ext)) return 'text';
  return 'unsupported';
});

function isImageDerivedChunk(chunk: KnowledgeDocumentChunkItem) {
  const metadata = chunk.metadata || {};
  const sourceKinds = Array.isArray(metadata.sourceKinds) ? metadata.sourceKinds : [];
  const sourceParsers = Array.isArray(metadata.sourceParsers) ? metadata.sourceParsers : [];
  return previewKind.value === 'image'
    || chunk.contentType === 'image'
    || metadata.sourceKind === 'image_ocr'
    || sourceKinds.includes('image_ocr')
    || sourceParsers.includes('rapidocr');
}

async function openChunkSourceImage(chunk: KnowledgeDocumentChunkItem) {
  imagePreviewVisible.value = true;
  imagePreviewLoading.value = true;
  imagePreviewUrl.value = '';
  try {
    if (previewKind.value === 'image') {
      imagePreviewUrl.value = objectUrl.value;
      return;
    }
    if (previewKind.value !== 'pdf' || !pdfBlob.value) {
      return;
    }
    const buffer = await pdfBlob.value.arrayBuffer();
    const pdf = await pdfjsLib.getDocument({ data: buffer }).promise;
    try {
      const requestedPage = Number(chunk.pageNo || 1);
      const pageNumber = Math.min(pdf.numPages, Math.max(1, Number.isFinite(requestedPage) ? requestedPage : 1));
      const page = await pdf.getPage(pageNumber);
      const viewport = page.getViewport({ scale: 1.5 });
      const canvas = window.document.createElement('canvas');
      const context = canvas.getContext('2d');
      canvas.width = Math.ceil(viewport.width);
      canvas.height = Math.ceil(viewport.height);
      if (!context) return;
      await page.render({ canvas, canvasContext: context, viewport }).promise;
      imagePreviewUrl.value = canvas.toDataURL('image/png');
    } finally {
      await pdf.destroy();
    }
  } catch (error) {
    window.alert(readError(error, t('图片加载失败')));
    imagePreviewVisible.value = false;
  } finally {
    imagePreviewLoading.value = false;
  }
}

function revokeObjectUrl() {
  if (objectUrl.value) {
    URL.revokeObjectURL(objectUrl.value);
    objectUrl.value = '';
  }
  destroyPdfDocument();
  pdfBlob.value = null;
  pdfPageCount.value = 0;
  pdfScaleTouched.value = false;
  if (pdfCanvasLayerRef.value) {
    pdfCanvasLayerRef.value.innerHTML = '';
  }
}

function destroyPdfDocument() {
  pdfRenderSeq += 1;
  const current = pdfDocument.value;
  pdfDocument.value = null;
  if (!current) {
    return;
  }
  try {
    const result = current.destroy?.();
    if (result && typeof result.catch === 'function') {
      result.catch(() => {});
    }
  } catch {
    // PDF.js may throw if a document is destroyed while a page render is being cancelled.
  }
}

function formatFileSize(bytes: number) {
  if (!bytes) return '0 B';
  const units = ['B', 'KB', 'MB', 'GB'];
  let value = bytes;
  let index = 0;
  while (value >= 1024 && index < units.length - 1) {
    value /= 1024;
    index += 1;
  }
  return `${value.toFixed(index === 0 ? 0 : 1)} ${units[index]}`;
}

function readError(error: unknown, fallback: string) {
  if (axios.isAxiosError(error)) {
    return String(error.response?.data?.detail || error.message || fallback);
  }
  if (error instanceof Error) {
    return error.message || fallback;
  }
  return fallback;
}

function mergeTableRowMarkdown(current: string, next: string) {
  const currentLines = String(current || '').split('\n').filter((line) => line.trim());
  const nextLines = String(next || '').split('\n').filter((line) => line.trim());
  if (currentLines.length < 3 || nextLines.length < 3) {
    return [current, next].filter(Boolean).join('\n\n');
  }
  return [...currentLines, ...nextLines.slice(2)].join('\n');
}

function processLabel(value: string) {
  const map: Record<string, string> = {
    not_started: t('未开始'),
    queued: t('排队'),
    running: t('运行中'),
    succeeded: t('成功'),
    failed: t('失败'),
  };
  return map[value] || value;
}

function previewStatusLabel(value: string) {
  const map: Record<string, string> = {
    not_required: t('无需转换'),
    pending: t('等待生成'),
    queued: t('排队中'),
    running: t('生成中'),
    succeeded: t('已生成'),
    failed: t('生成失败'),
  };
  return map[value] || value;
}

async function loadChunks() {
  if (!documentId.value) {
    return;
  }
  chunksLoading.value = true;
  try {
    const result = await fetchKnowledgeDocumentChunks(documentId.value, {
      page: chunkPagination.page,
      pageSize: chunkPagination.pageSize,
      keyword: chunkKeyword.value.trim(),
      chunkStage,
    });
    const items = result.items;
    if (targetChunk.value && !items.some((item) => item.chunkId === targetChunk.value?.chunkId)) {
      chunks.value = [targetChunk.value, ...items];
    } else {
      chunks.value = items;
    }
    chunkPagination.total = result.total;
  } catch (error) {
    window.alert(readError(error, t('分段加载失败')));
  } finally {
    chunksLoading.value = false;
  }
}

async function loadTargetChunk() {
  if (!documentId.value || !targetChunkId.value) {
    targetChunk.value = null;
    return;
  }
  targetChunkLoading.value = true;
  try {
    targetChunk.value = await fetchKnowledgeDocumentChunk(documentId.value, targetChunkId.value, chunkStage);
    const exists = chunks.value.some((item) => item.chunkId === targetChunk.value?.chunkId);
    if (targetChunk.value && !exists) {
      chunks.value = [targetChunk.value, ...chunks.value];
    }
  } catch (error) {
    console.warn('target chunk load failed', error);
    targetChunk.value = null;
  } finally {
    targetChunkLoading.value = false;
  }
}

function openChunksPanel() {
  activePanel.value = 'chunks';
  if (!chunks.value.length && !chunksLoading.value) {
    void loadChunks();
  }
  if (document.value?.chunkStatus !== 'succeeded' && document.value?.parseStatus !== 'failed') {
    startPolling();
  }
}

function scrollToPdfPage(pageNo: number | null = targetPageNo.value) {
  if (!pageNo || !pdfCanvasLayerRef.value) {
    return;
  }
  const page = pdfCanvasLayerRef.value.querySelector<HTMLElement>(`[data-page-number="${pageNo}"]`);
  page?.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

function scrollToTargetChunk() {
  if (!targetChunkId.value) {
    return;
  }
  const escaped = window.CSS?.escape ? window.CSS.escape(targetChunkId.value) : targetChunkId.value.replace(/"/g, '\\"');
  const node = window.document.querySelector<HTMLElement>(`[data-chunk-id="${escaped}"]`);
  node?.scrollIntoView({ behavior: 'smooth', block: 'center' });
}

async function applySourceTarget() {
  if (!targetChunkId.value && !targetPageNo.value) {
    return;
  }
  activePanel.value = 'chunks';
  await loadTargetChunk();
  await nextTick();
  scrollToPdfPage();
  scrollToTargetChunk();
}

function handleChunkSearch() {
  chunkPagination.page = 1;
  void loadChunks();
}

function handleChunkPageSizeChange() {
  chunkPagination.page = 1;
  void loadChunks();
}

function stopPolling() {
  if (pollTimer.value !== null) {
    window.clearInterval(pollTimer.value);
    pollTimer.value = null;
  }
}

function shouldPollDocument(doc: KnowledgeDocumentItem) {
  const previewPending = ['pending', 'queued', 'running'].includes(doc.previewStatus);
  const chunksPending = activePanel.value === 'chunks'
    && doc.parseStatus !== 'failed'
    && doc.chunkStatus !== 'succeeded'
    && doc.chunkStatus !== 'failed';
  return previewPending || chunksPending;
}

function startPolling() {
  if (pollTimer.value !== null) {
    return;
  }
  pollTimer.value = window.setInterval(async () => {
    try {
      const doc = await fetchKnowledgeDocument(documentId.value);
      document.value = doc;
      if (isConverting.value && (doc.previewStatus === 'succeeded' || doc.previewStatus === 'failed')) {
        isConverting.value = false;
        void reload();
      }
      if (activePanel.value === 'chunks' && doc.chunkStatus === 'succeeded') {
        void loadChunks();
      }
      if (!shouldPollDocument(doc)) {
        stopPolling();
      }
    } catch (error) {
      console.error(error);
    }
  }, 5000);
}

async function loadBlob() {
  isConverting.value = false;
  try {
    const response = await apiClient.get<Blob>(`/api/knowledge/documents/${documentId.value}/preview`, {
      responseType: 'blob',
      timeout: 120000,
    });
    revokeObjectUrl();
    const blob = response.data;
    objectUrl.value = URL.createObjectURL(blob);
    if (previewKind.value === 'pdf') {
      pdfBlob.value = blob;
      await renderPdf(blob);
    } else if (previewKind.value === 'text' || previewKind.value === 'markdown' || previewKind.value === 'html') {
      textContent.value = await blob.text();
    } else {
      textContent.value = '';
    }
  } catch (error) {
    if (axios.isAxiosError(error) && error.response?.status === 409) {
      const status = document.value?.previewStatus;
      if (status === 'pending' || status === 'queued' || status === 'running') {
        isConverting.value = true;
        startPolling();
        return;
      }
    }
    throw error;
  }
}

async function renderPdf(blob = pdfBlob.value) {
  if (!blob) {
    return;
  }
  let activeSeq = 0;
  pdfRendering.value = true;
  await nextTick();
  const host = pdfCanvasLayerRef.value;
  if (!host) {
    pdfRendering.value = false;
    return;
  }
  host.innerHTML = '';
  try {
    destroyPdfDocument();
    activeSeq = ++pdfRenderSeq;
    const buffer = await blob.arrayBuffer();
    const task = pdfjsLib.getDocument({ data: buffer });
    const pdf = await task.promise;
    if (activeSeq !== pdfRenderSeq) {
      await pdf.destroy();
      return;
    }
    pdfDocument.value = markRaw(pdf);
    pdfPageCount.value = pdf.numPages;
    const firstPage = await pdf.getPage(1);
    if (!pdfScaleTouched.value) {
      applyDefaultPdfScale(firstPage);
    }
    const estimatedViewport = firstPage.getViewport({ scale: pdfScale.value });
    const wrappers = new Map<number, HTMLElement>();
    const fragment = window.document.createDocumentFragment();
    for (let pageNumber = 1; pageNumber <= pdf.numPages; pageNumber += 1) {
      const wrapper = window.document.createElement('article');
      wrapper.className = 'pdfjs-page pdfjs-page-pending';
      wrapper.dataset.pageNumber = String(pageNumber);
      wrapper.style.width = `${Math.floor(estimatedViewport.width)}px`;
      wrapper.style.height = `${Math.floor(estimatedViewport.height)}px`;
      fragment.appendChild(wrapper);
      wrappers.set(pageNumber, wrapper);
    }
    host.innerHTML = '';
    host.appendChild(fragment);
    await nextTick();

    const renderedPages = new Set<number>();
    const renderPage = async (pageNumber: number) => {
      if (activeSeq !== pdfRenderSeq || renderedPages.has(pageNumber)) {
        return;
      }
      const wrapper = wrappers.get(pageNumber);
      if (!wrapper) {
        return;
      }
      renderedPages.add(pageNumber);
      const page = pageNumber === 1 ? firstPage : await pdf.getPage(pageNumber);
      const viewport = page.getViewport({ scale: pdfScale.value });
      wrapper.classList.remove('pdfjs-page-pending');
      wrapper.innerHTML = '';
      wrapper.style.width = `${Math.floor(viewport.width)}px`;
      wrapper.style.height = `${Math.floor(viewport.height)}px`;
      const canvas = window.document.createElement('canvas');
      const context = canvas.getContext('2d');
      const outputScale = window.devicePixelRatio || 1;
      canvas.width = Math.floor(viewport.width * outputScale);
      canvas.height = Math.floor(viewport.height * outputScale);
      canvas.style.width = `${Math.floor(viewport.width)}px`;
      canvas.style.height = `${Math.floor(viewport.height)}px`;
      wrapper.appendChild(canvas);
      if (context) {
        await page.render({
          canvas,
          canvasContext: context,
          viewport,
          transform: outputScale !== 1 ? [outputScale, 0, 0, outputScale, 0, 0] : undefined,
        }).promise;
      }
    };

    const order = createPdfPageRenderOrder(pdf.numPages, targetPageNo.value);
    const priorityCount = targetPageNo.value ? Math.min(5, order.length) : Math.min(3, order.length);
    const priorityPages = order.slice(0, priorityCount);
    const remainingPages = order.slice(priorityCount);
    for (const pageNumber of priorityPages) {
      await renderPage(pageNumber);
    }
    await nextTick();
    scrollToPdfPage();
    pdfRendering.value = false;

    void (async () => {
      for (const pageNumber of remainingPages) {
        if (activeSeq !== pdfRenderSeq) {
          return;
        }
        await nextAnimationFrame();
        await renderPage(pageNumber);
      }
    })();
  } catch (error) {
    errorText.value = readError(error, t('PDF 渲染失败'));
  } finally {
    if (!activeSeq || activeSeq === pdfRenderSeq) {
      pdfRendering.value = false;
    }
  }
}

function createPdfPageRenderOrder(totalPages: number, targetPage: number | null): number[] {
  const priority = targetPage
    ? [targetPage, targetPage - 1, targetPage + 1, targetPage - 2, targetPage + 2]
    : [1, 2, 3];
  const seen = new Set<number>();
  const output: number[] = [];
  const add = (pageNumber: number) => {
    if (!Number.isFinite(pageNumber) || pageNumber < 1 || pageNumber > totalPages || seen.has(pageNumber)) {
      return;
    }
    seen.add(pageNumber);
    output.push(pageNumber);
  };
  priority.forEach(add);
  for (let pageNumber = 1; pageNumber <= totalPages; pageNumber += 1) {
    add(pageNumber);
  }
  return output;
}

function nextAnimationFrame(): Promise<void> {
  return new Promise((resolve) => window.requestAnimationFrame(() => resolve()));
}

function applyDefaultPdfScale(page: any) {
  const host = pdfCanvasLayerRef.value;
  if (!host) {
    return;
  }
  const baseViewport = page.getViewport({ scale: 1 });
  const availableWidth = Math.max(320, host.clientWidth - PDF_VIEWER_HORIZONTAL_PADDING);
  const nextScale = Math.min(1, Math.max(PDF_MIN_SCALE, availableWidth / baseViewport.width));
  pdfScale.value = Number(nextScale.toFixed(2));
}

function zoomPdf(delta: number) {
  const nextScale = Math.min(PDF_MAX_SCALE, Math.max(PDF_MIN_SCALE, Number((pdfScale.value + delta).toFixed(1))));
  if (nextScale === pdfScale.value || pdfRendering.value) {
    return;
  }
  pdfScaleTouched.value = true;
  pdfScale.value = nextScale;
  void renderPdf();
}

async function reload() {
  if (!documentId.value) {
    errorText.value = t('文档 ID 无效');
    return;
  }
  loading.value = true;
  errorText.value = '';
  try {
    document.value = await fetchKnowledgeDocument(documentId.value);
  } catch (error) {
    errorText.value = readError(error, t('文档详情加载失败'));
    loading.value = false;
    return;
  }

  try {
    if (targetChunkId.value && !targetChunk.value) {
      await loadTargetChunk();
    }
    await loadBlob();
    await applySourceTarget();
  } catch (error) {
    errorText.value = readError(error, t('文档预览加载失败'));
  } finally {
    loading.value = false;
  }
}

async function retryParse() {
  if (!document.value) {
    return;
  }
  try {
    document.value = await retryKnowledgeDocumentParse(document.value.id);
    activePanel.value = 'detail';
    chunks.value = [];
    chunkPagination.page = 1;
    chunkPagination.total = 0;
    startPolling();
  } catch (error) {
    window.alert(readError(error, t('重新学习失败')));
  }
}

async function downloadFile() {
  if (!document.value) {
    return;
  }
  downloading.value = true;
  try {
    const response = await apiClient.get<Blob>(`/api/knowledge/documents/${document.value.id}/content`, {
      responseType: 'blob',
      timeout: 180000,
    });
    const blob = response.data;
    const url = URL.createObjectURL(blob);
    const link = window.document.createElement('a');
    link.href = url;
    link.download = document.value.originalFilename || document.value.name || 'document';
    window.document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
  } catch (error) {
    window.alert(readError(error, t('文件下载失败')));
  } finally {
    downloading.value = false;
  }
}

function closePage() {
  void router.push({ name: 'KnowledgeDocuments' });
}

function refreshHeaderTeleportReady(attempt = 0) {
  const ready = Boolean(
    window.document.querySelector('#header-title-teleport-target')
      && window.document.querySelector('#header-actions-teleport-target'),
  );
  headerTeleportReady.value = ready;
  if (!ready && attempt < 5) {
    window.requestAnimationFrame(() => refreshHeaderTeleportReady(attempt + 1));
  }
}

onMounted(async () => {
  await nextTick();
  window.requestAnimationFrame(refreshHeaderTeleportReady);
  void reload();
});
onBeforeUnmount(() => {
  // Reset teleport readiness to clean up injected header elements and avoid duplication on navigation
  headerTeleportReady.value = false;
  revokeObjectUrl();
  stopPolling();
});

watch(activePanel, async (value) => {
  if (value === 'chunks') {
    void loadChunks();
  }
  if (previewKind.value === 'pdf' && pdfBlob.value && !pdfScaleTouched.value) {
    await nextTick();
    void renderPdf();
  }
});

watch(
  () => [route.query.chunkId, route.query.pageNo],
  () => {
    void applySourceTarget();
  },
);

watch(documentId, (next, previous) => {
  if (!next || next === previous) {
    return;
  }
  chunks.value = [];
  targetChunk.value = null;
  chunkPagination.page = 1;
  chunkPagination.total = 0;
  pdfScaleTouched.value = false;
  void reload();
});
</script>

<style scoped>
.preview-page {
  height: calc(100vh - 65px);
  min-height: 0;
  display: flex;
  flex-direction: column;
  gap: 14px;
  padding: 12px;
}

.preview-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 18px;
  padding: 14px 16px;
  border: 1px solid #e6ebf5;
  border-radius: 8px;
  background: #fff;
  box-shadow: 0 4px 14px rgba(16, 38, 84, 0.05);
}

.title-block {
  min-width: 0;
}

.title-row {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
}

.title-icon,
.button-icon {
  display: inline-flex;
  width: 16px;
  height: 16px;
}

.title-icon {
  color: #366aff;
}

.title-icon svg,
.button-icon svg {
  width: 16px;
  height: 16px;
  fill: none;
  stroke: currentColor;
  stroke-width: 2;
  stroke-linecap: round;
  stroke-linejoin: round;
}

.page-title {
  min-width: 0;
  overflow: hidden;
  color: #17233d;
  font-size: 16px;
  font-weight: 800;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.page-meta {
  margin-top: 4px;
  color: #687789;
  font-size: 12px;
}

.detail-layout {
  flex: 1;
  min-height: 0;
  display: grid;
  grid-template-columns: minmax(560px, 1fr) clamp(520px, 34vw, 720px);
  gap: 14px;
}

.detail-layout.is-chunks-panel {
  grid-template-columns: minmax(620px, 1fr) clamp(520px, 34vw, 680px);
}

.preview-shell {
  min-height: 0;
  overflow: hidden;
  border: 1px solid #e6ebf5;
  border-radius: 8px;
  background: #fff;
}

.preview-shell :deep(.n-spin-container),
.preview-shell :deep(.n-spin-content) {
  height: 100%;
  min-height: 0;
}

.detail-sidebar {
  min-height: 0;
  display: grid;
  grid-template-columns: minmax(0, 1fr) 48px;
  gap: 10px;
}

.detail-panel {
  min-height: 0;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.detail-rail {
  min-height: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  padding: 8px 6px;
  border: 1px solid #e6ebf5;
  border-radius: 8px;
  background: #fff;
  box-shadow: 0 4px 14px rgba(16, 38, 84, 0.04);
}

.rail-button {
  position: relative;
  width: 34px;
  height: 34px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border: 1px solid transparent;
  border-radius: 8px;
  background: transparent;
  color: #687789;
  cursor: pointer;
  transition: color 0.16s ease, background 0.16s ease, border-color 0.16s ease;
}

.rail-button:hover,
.rail-button.active {
  border-color: #dbe6ff;
  background: #f1f5ff;
  color: #366aff;
}

.rail-button svg {
  width: 18px;
  height: 18px;
  fill: none;
  stroke: currentColor;
  stroke-width: 2;
  stroke-linecap: round;
  stroke-linejoin: round;
}

.rail-count {
  position: absolute;
  top: -5px;
  right: -5px;
  min-width: 16px;
  height: 16px;
  padding: 0 4px;
  border: 1px solid #fff;
  border-radius: 999px;
  background: #366aff;
  color: #fff;
  font-size: 10px;
  line-height: 14px;
  font-weight: 700;
}

.detail-card {
  min-height: 0;
  padding: 16px;
  border: 1px solid #e6ebf5;
  border-radius: 8px;
  background: #fff;
  box-shadow: 0 4px 14px rgba(16, 38, 84, 0.04);
}

.chunks-card {
  min-height: 0;
  height: 100%;
  display: flex;
  flex-direction: column;
  padding: 14px;
  border: 1px solid #e6ebf5;
  border-radius: 8px;
  background: #fff;
  box-shadow: 0 4px 14px rgba(16, 38, 84, 0.04);
}

.detail-card-title {
  color: #17233d;
  font-size: 15px;
  font-weight: 800;
}

.chunks-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}

.chunks-subtitle {
  margin-top: 4px;
  color: #7a8797;
  font-size: 12px;
}

.source-target-card {
  margin-top: 12px;
  padding: 12px;
  border: 1px solid #cfe0ff;
  border-radius: 8px;
  background: linear-gradient(180deg, #f7faff 0%, #ffffff 100%);
  box-shadow: 0 8px 20px rgba(54, 106, 255, 0.08);
}

.source-target-head {
  display: flex;
  align-items: center;
  gap: 8px;
}

.source-target-icon {
  width: 24px;
  height: 24px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: 6px;
  color: #366aff;
  background: #eaf1ff;
}

.source-target-icon svg {
  width: 15px;
  height: 15px;
  fill: none;
  stroke: currentColor;
  stroke-width: 2;
  stroke-linecap: round;
  stroke-linejoin: round;
}

.source-target-title {
  color: #17233d;
  font-size: 13px;
  font-weight: 800;
}

.source-target-meta {
  margin-top: 8px;
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.source-target-meta span {
  min-height: 22px;
  display: inline-flex;
  align-items: center;
  border-radius: 999px;
  background: #eef4ff;
  padding: 0 8px;
  color: #3158bc;
  font-size: 12px;
  font-weight: 700;
}

.source-target-path {
  margin-top: 8px;
  color: #687789;
  font-size: 12px;
  line-height: 1.6;
}

.source-target-text {
  margin: 10px 0 0;
  max-height: 150px;
  overflow: auto;
  white-space: pre-wrap;
  word-break: break-word;
  color: #24324a;
  font-family: inherit;
  font-size: 13px;
  line-height: 1.7;
}

.source-target-loading {
  margin-top: 8px;
  color: #7a8797;
  font-size: 12px;
}

.chunks-filter {
  margin-top: 12px;
}

.input-icon {
  display: inline-flex;
  width: 15px;
  height: 15px;
  color: #8a96a8;
}

.input-icon svg {
  width: 15px;
  height: 15px;
  fill: none;
  stroke: currentColor;
  stroke-width: 2;
  stroke-linecap: round;
  stroke-linejoin: round;
}

.chunks-card :deep(.n-spin-container),
.chunks-card :deep(.n-spin-content) {
  min-height: 0;
  flex: 1;
  display: flex;
  flex-direction: column;
}

.chunk-list {
  min-height: 0;
  flex: 1;
  overflow: auto;
  display: flex;
  flex-direction: column;
  gap: 10px;
  margin-top: 12px;
  padding-right: 2px;
}

.chunk-item {
  padding: 12px;
  border: 1px solid #e8eef7;
  border-radius: 8px;
  background: #fbfdff;
}

.chunk-item.is-target {
  border-color: #366aff;
  background: #f5f8ff;
  box-shadow: 0 10px 24px rgba(54, 106, 255, 0.14);
}

.chunk-item-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.chunk-index {
  color: #366aff;
  font-size: 12px;
  font-weight: 800;
}

.chunk-badges {
  min-width: 0;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
  justify-content: flex-end;
}

.chunk-badge {
  max-width: 112px;
  height: 20px;
  display: inline-flex;
  align-items: center;
  padding: 0 7px;
  border-radius: 999px;
  background: #eef4ff;
  color: #456083;
  font-size: 11px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.chunk-badge-image {
  background: #e9f8ef;
  color: #18794e;
}

.chunk-image-button {
  height: 24px;
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 0 8px;
  border: 1px solid #b8caff;
  border-radius: 6px;
  background: #fff;
  color: #366aff;
  font-size: 11px;
  cursor: pointer;
}

.chunk-image-button:hover {
  background: #f1f5ff;
}

.chunk-image-button svg {
  width: 13px;
  height: 13px;
  fill: none;
  stroke: currentColor;
  stroke-width: 1.8;
  stroke-linecap: round;
  stroke-linejoin: round;
}

.chunk-image-modal-body {
  position: relative;
  max-width: min(92vw, 1200px);
  max-height: 90vh;
  padding: 12px;
  border-radius: 8px;
  background: #fff;
  box-shadow: 0 24px 64px rgba(15, 23, 42, 0.28);
}

.chunk-image-modal-body img {
  display: block;
  max-width: 100%;
  max-height: calc(90vh - 24px);
  object-fit: contain;
}

.chunk-image-modal-close {
  position: absolute;
  top: 18px;
  right: 18px;
  z-index: 1;
  width: 30px;
  height: 30px;
  border: 0;
  border-radius: 50%;
  background: rgba(15, 23, 42, 0.72);
  color: #fff;
  font-size: 22px;
  line-height: 28px;
  cursor: pointer;
}

.chunk-title-path {
  margin-top: 8px;
  color: #516071;
  font-size: 12px;
  font-weight: 650;
  line-height: 1.5;
  overflow-wrap: anywhere;
}

.chunk-text {
  max-height: 220px;
  margin: 9px 0 0;
  overflow: auto;
  color: #25324a;
  font-family: "SFMono-Regular", Consolas, "Liberation Mono", monospace;
  font-size: 12px;
  line-height: 1.65;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}

.chunks-empty {
  min-height: 260px;
  flex: 1;
  display: grid;
  place-content: center;
  justify-items: center;
  gap: 10px;
  padding: 24px;
  text-align: center;
}

.empty-icon {
  display: grid;
  width: 44px;
  height: 44px;
  place-items: center;
  border-radius: 10px;
  background: #eef4ff;
  color: #366aff;
}

.empty-icon svg {
  width: 22px;
  height: 22px;
  fill: none;
  stroke: currentColor;
  stroke-width: 2;
  stroke-linecap: round;
  stroke-linejoin: round;
}

.empty-icon-running svg {
  animation: converting-spin-animation 1.4s linear infinite;
}

.empty-title {
  color: #17233d;
  font-size: 14px;
  font-weight: 800;
}

.empty-copy {
  max-width: 260px;
  color: #687789;
  font-size: 12px;
  line-height: 1.6;
}

.chunks-pagination {
  margin-top: 12px;
  justify-content: flex-end;
}

.meta-list {
  display: grid;
  gap: 12px;
  margin-top: 14px;
}

.meta-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px 14px;
}

.meta-row {
  display: grid;
  gap: 4px;
  min-width: 0;
}

.meta-row-full strong {
  white-space: normal;
  overflow-wrap: anywhere;
}

.meta-row span {
  color: #7a8797;
  font-size: 12px;
}

.meta-row strong {
  min-width: 0;
  overflow: hidden;
  color: #23324f;
  font-size: 13px;
  font-weight: 650;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.pdfjs-viewer {
  height: 100%;
  min-height: 0;
  position: relative;
  display: flex;
  flex-direction: column;
  background: #f5f7fb;
}

.pdfjs-page-count {
  color: #687789;
  font-size: 12px;
  font-weight: 500;
  padding: 0 4px;
}

.pdfjs-zoom-value {
  width: 54px;
  height: 28px;
  display: grid;
  place-items: center;
  border: 1px solid #e6ebf5;
  border-radius: 6px;
  background: #f8fbff;
  color: #23324f;
  font-size: 12px;
  font-weight: 700;
}

.pdfjs-floating-controls {
  position: absolute;
  right: 18px;
  bottom: 44px;
  z-index: 3;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 8px;
  border: 1px solid rgba(214, 224, 241, 0.92);
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.94);
  box-shadow: 0 10px 28px rgba(16, 38, 84, 0.16);
  backdrop-filter: blur(10px);
}

.pdfjs-pages {
  flex: 1;
  min-height: 0;
  overflow: auto;
  padding: 18px;
  position: relative;
}

.pdfjs-canvas-layer {
  min-height: 100%;
  width: max-content;
  min-width: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 18px;
}

.pdfjs-canvas-layer :deep(.pdfjs-page) {
  position: relative;
  flex: 0 0 auto;
  box-sizing: content-box;
  overflow: hidden;
  border: 1px solid #dfe7f3;
  border-radius: 6px;
  background: #fff;
  box-shadow: 0 8px 22px rgba(16, 38, 84, 0.12);
}

.pdfjs-canvas-layer :deep(.pdfjs-page-pending::after) {
  content: "";
  position: absolute;
  inset: 0;
  border-radius: 4px;
  background: linear-gradient(90deg, #f2f5fa 0%, #fafcff 45%, #f2f5fa 100%);
  background-size: 220% 100%;
  animation: pdfjs-page-pending-shimmer 1.2s ease-in-out infinite;
}

.pdfjs-canvas-layer :deep(canvas) {
  display: block;
}

.pdfjs-loading {
  position: absolute;
  top: 80px;
  left: 50%;
  transform: translateX(-50%);
  width: 36px;
  height: 36px;
  display: grid;
  place-items: center;
  border: 1px solid #dfe7f3;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.92);
  box-shadow: 0 6px 18px rgba(16, 38, 84, 0.08);
}

.pdfjs-loading-spinner {
  width: 18px;
  height: 18px;
  border: 2px solid #d6e0f1;
  border-top-color: #366aff;
  border-radius: 50%;
  animation: pdfjs-loading-spin 0.8s linear infinite;
}

@keyframes pdfjs-loading-spin {
  to {
    transform: rotate(360deg);
  }
}

@keyframes pdfjs-page-pending-shimmer {
  0% {
    background-position: 100% 0;
  }
  100% {
    background-position: -100% 0;
  }
}

.image-preview {
  width: 100%;
  height: 100%;
  overflow: auto;
  display: grid;
  place-items: center;
  padding: 24px;
  background: #f8fafc;
}

.image-preview img {
  max-width: 100%;
  max-height: 100%;
  object-fit: contain;
  box-shadow: 0 10px 32px rgba(15, 31, 69, 0.12);
}

.text-preview {
  height: 100%;
  margin: 0;
  overflow: auto;
  padding: 24px;
  color: #17233d;
  background: #fbfdff;
  font-family: "SFMono-Regular", Consolas, "Liberation Mono", monospace;
  font-size: 13px;
  line-height: 1.7;
  white-space: pre-wrap;
}

.unsupported-preview {
  height: 100%;
  display: grid;
  place-content: center;
  justify-items: center;
  gap: 12px;
  padding: 32px;
  text-align: center;
}

.converting-preview {
  height: 100%;
  display: grid;
  place-content: center;
  justify-items: center;
  gap: 12px;
  padding: 32px;
  text-align: center;
  background: #f8fafc;
}

.converting-icon {
  display: grid;
  width: 56px;
  height: 56px;
  place-items: center;
  border-radius: 12px;
  background: #eaf0ff;
  color: #366aff;
}

.converting-icon svg {
  width: 26px;
  height: 26px;
  fill: none;
  stroke: currentColor;
  stroke-width: 2;
  stroke-linecap: round;
  stroke-linejoin: round;
}

.converting-spin {
  animation: converting-spin-animation 1.5s linear infinite;
}

@keyframes converting-spin-animation {
  from {
    transform: rotate(0deg);
  }
  to {
    transform: rotate(360deg);
  }
}

.converting-title {
  color: #17233d;
  font-size: 16px;
  font-weight: 800;
}

.converting-copy {
  max-width: 420px;
  color: #687789;
  font-size: 13px;
  line-height: 1.6;
}

.preview-placeholder {
  height: 100%;
  display: grid;
  place-items: center;
  background: #f8fafc;
}

.unsupported-icon {
  display: grid;
  width: 56px;
  height: 56px;
  place-items: center;
  border-radius: 12px;
  background: #eaf0ff;
  color: #366aff;
}

.unsupported-icon svg {
  width: 26px;
  height: 26px;
  fill: none;
  stroke: currentColor;
  stroke-width: 2;
  stroke-linecap: round;
  stroke-linejoin: round;
}

.unsupported-title {
  color: #17233d;
  font-size: 16px;
  font-weight: 800;
}

.unsupported-copy {
  max-width: 420px;
  color: #687789;
  font-size: 13px;
  line-height: 1.6;
}

.header-doc-title-block {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  max-width: 550px;
  min-width: 0;
}

.header-doc-title {
  font-size: 14px;
  font-weight: 700;
  color: #1f2d3d;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  line-height: 1.2;
}

html.dark .header-doc-title {
  color: #e2e8f0;
}

.header-doc-meta {
  font-size: 11px;
  color: #8892a0;
  background: #f1f3f6;
  padding: 2px 6px;
  border-radius: 4px;
  white-space: nowrap;
  line-height: 1;
}

html.dark .header-doc-meta {
  background: #232a35;
  color: #718096;
}

@media (max-width: 1440px) {
  .detail-layout {
    grid-template-columns: minmax(520px, 1fr) clamp(480px, 38vw, 640px);
  }

  .detail-layout.is-chunks-panel {
    grid-template-columns: minmax(560px, 1fr) clamp(480px, 38vw, 620px);
  }
}

@media (max-width: 1180px) {
  .detail-layout {
    grid-template-columns: 1fr;
    grid-template-rows: minmax(520px, 1fr) 520px;
  }

  .detail-layout.is-chunks-panel {
    grid-template-columns: 1fr;
  }
}
</style>
