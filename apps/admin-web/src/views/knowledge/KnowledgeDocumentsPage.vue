<template>
  <div class="page-stack knowledge-page">
    <div class="metrics-row">
      <n-card v-for="item in metricCards" :key="item.key" class="metric-card" :bordered="false" size="small">
        <div class="metric-main">
          <span class="metric-icon" :class="`metric-icon-${item.key}`" v-html="item.icon"></span>
          <div class="metric-body">
            <div class="metric-label">{{ item.label }}</div>
            <div class="metric-value">{{ item.value }}</div>
          </div>
        </div>
        <span class="metric-help-icon" tabindex="0" :aria-label="item.note">
          <svg viewBox="0 0 24 24" aria-hidden="true">
            <circle cx="12" cy="12" r="9"></circle>
            <path d="M12 8v5"></path>
            <path d="M12 16h.01"></path>
          </svg>
          <span class="metric-help-tooltip">{{ item.note }}</span>
        </span>
      </n-card>
    </div>

    <div class="list-workspace">
      <div class="knowledge-layout">
        <!-- 左侧目录树 -->
        <aside class="dept-panel">
          <div class="panel-head">
            <span class="panel-title">{{ t('知识目录') }}</span>
            <n-space :size="6">
              <n-button size="tiny" @click="openCreateDir(null)">
                <template #icon>
                  <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <path d="M5 12h14" />
                    <path d="M12 5v14" />
                  </svg>
                </template>
                {{ t('新增') }}
              </n-button>
              <n-button size="tiny" :disabled="!selectedDirId" @click="openEditDir(null)">
                <template #icon>
                  <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <path d="M12 20h9" />
                    <path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4 12.5-12.5z" />
                  </svg>
                </template>
                {{ t('编辑') }}
              </n-button>
            </n-space>
          </div>
          <n-input v-model:value="treeKeyword" :placeholder="t('搜索目录')" clearable size="small" />
          <div class="tree-wrap">
            <n-tree
              block-line
              selectable
              :pattern="treeKeyword"
              :data="treeOptions"
              :render-label="renderTreeLabel"
              :selected-keys="selectedDirKeys"
              :expanded-keys="expandedDirKeys"
              @update:selected-keys="handleSelectDirectory"
              @update:expanded-keys="handleExpandDirectories"
            />
          </div>
          <n-space :size="8">
            <n-button size="tiny" :disabled="!selectedDirId" @click="openMoveDir">
              <template #icon>
                <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                  <path d="m5 9-3 3 3 3M9 5l3-3 3 3M15 19l-3 3-3-3M19 9l3 3-3 3M2 12h20M12 2v20" />
                </svg>
              </template>
              {{ t('移动') }}
            </n-button>
            <n-button
              size="tiny"
              type="error"
              ghost
              :disabled="deleteDirectoryDisabled"
              :title="deleteDirectoryDisabledReason"
              @click="deleteSelectedDir"
            >
              <template #icon>
                <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                  <path d="M3 6h18" />
                  <path d="M19 6v14c0 1-1 2-2 2H7c-1 0-2-1-2-2V6" />
                  <path d="M8 6V4c0-1 1-2 2-2h4c1 0 2 1 2 2v2" />
                </svg>
              </template>
              {{ t('删除') }}
            </n-button>
          </n-space>
        </aside>

        <!-- 右侧列表 -->
        <section class="list-panel">
          <div class="list-filter-row">
            <div class="filter-toolbar">
              <div class="filter-left">
                <n-input-group class="document-search-group">
                  <n-select
                    v-model:value="effectiveSearchScope"
                    :options="searchScopeOptions"
                    class="search-scope-select"
                    @update:value="handleSearchScopeChange"
                  />
                  <n-input
                    v-model:value="filters.keyword"
                    :placeholder="t('搜索文档名称')"
                    clearable
                    class="keyword-input"
                    @keyup.enter="handleSearch"
                    @update:value="handleKeywordUpdate"
                  />
                </n-input-group>
                <n-select
                  v-model:value="filters.fileType"
                  :options="fileTypeOptions"
                  :placeholder="t('文件类型')"
                  clearable
                  class="compact-filter-select"
                  @update:value="handleSearch"
                />
                <n-select
                  v-model:value="filters.statusValue"
                  :options="statusOptions"
                  :placeholder="t('状态')"
                  clearable
                  class="compact-filter-select"
                  @update:value="handleSearch"
                />
              </div>
              <div class="filter-right">
                <n-button
                  type="error"
                  ghost
                  :disabled="!selectedDocumentKeys.length"
                  @click="confirmBatchDelete"
                >
                  <template #icon>
                    <span class="button-icon" aria-hidden="true">
                      <svg viewBox="0 0 24 24"><path d="M3 6h18" /><path d="M8 6V4h8v2" /><path d="M6 6l1 16h10l1-16" /></svg>
                    </span>
                  </template>
                  {{ batchDeleteButtonText }}
                </n-button>
                <n-button type="primary" strong @click="openUpload">
                  <template #icon>
                    <span class="button-icon" aria-hidden="true">
                      <svg viewBox="0 0 24 24"><path d="M12 3v12" /><path d="M7 8l5-5 5 5" /><path d="M5 21h14" /><path d="M5 17h14" /></svg>
                    </span>
                  </template>
                  {{ t('上传文档') }}
                </n-button>
              </div>
            </div>
          </div>

          <div class="list-body">
            <n-spin :show="loading" class="document-list-spin">
              <div class="table-scroll-shell">
                <n-data-table
                  :columns="columns"
                  :data="documents"
                  :bordered="false"
                  :pagination="false"
                  :row-key="rowKey"
                  :checked-row-keys="selectedDocumentKeys"
                  :scroll-x="documentTableScrollX"
                  :scrollbar-props="tableScrollbarProps"
                  @update:checked-row-keys="handleCheckedRowKeys"
                  flex-height
                  class="documents-table"
                />
              </div>
              <div class="table-pagination">
                <n-pagination
                  v-model:page="pagination.page"
                  v-model:page-size="pagination.pageSize"
                  :item-count="pagination.total"
                  :page-sizes="[10, 12, 20, 50]"
                  show-size-picker
                  @update:page="handlePageChange"
                  @update:page-size="handlePageSizeChange"
                />
              </div>
            </n-spin>
          </div>
        </section>
      </div>
    </div>
  </div>

  <n-modal v-model:show="uploadVisible" preset="card" :title="t('上传知识文档')" style="width: 720px">
    <div style="margin-bottom: 16px;">
      <div style="margin-bottom: 8px; font-weight: 600; font-size: 14px;">{{ t('目标目录') }}</div>
      <n-select v-model:value="uploadDirectoryId" :options="directoryOptionsWithRoot" />
    </div>
    <section
      class="upload-picker"
      :class="{ 'is-dragging': uploadDragging }"
      @dragenter.prevent="handleUploadDragEnter"
      @dragover.prevent="handleUploadDragOver"
      @dragleave.prevent="handleUploadDragLeave"
      @drop.prevent="handleUploadDrop"
    >
      <input ref="fileInputRef" type="file" class="hidden-file-input" multiple :accept="acceptTypes" @change="handleFileChange" />
      <button class="upload-drop" type="button" @click="triggerFilePicker">
        <span class="upload-drop-icon" aria-hidden="true">
          <svg viewBox="0 0 24 24"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" /><path d="M14 2v6h6" /><path d="M12 18v-6" /><path d="M9 15l3-3 3 3" /></svg>
        </span>
        <span class="upload-drop-title">{{ t('点击选择或拖入文档/文件夹') }}</span>
        <span class="upload-drop-copy">{{ t('支持多次选择、批量上传，也支持拖入文件夹；上传会保存到当前目标目录。') }}</span>
      </button>
      <div v-if="uploadQueue.length" class="upload-queue-panel">
        <div class="upload-queue-head">
          <span class="upload-queue-title">{{ t('待上传文件') }}</span>
          <span class="upload-queue-count">{{ t('已选择 {count} 个文件', { count: uploadQueue.length }) }}</span>
          <button class="upload-queue-clear" type="button" :disabled="uploading" @click="clearUploadQueue">
            {{ t('清空') }}
          </button>
        </div>
        <div class="upload-queue-list">
          <article v-for="item in uploadQueue" :key="item.id" class="upload-queue-item">
            <span class="upload-queue-file-icon" aria-hidden="true">
              <svg viewBox="0 0 24 24"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" /><path d="M14 2v6h6" /></svg>
            </span>
            <div class="upload-queue-file-main">
              <div class="upload-queue-file-name" :title="item.file.name">{{ item.file.name }}</div>
              <div v-if="item.relativePath" class="upload-queue-file-path" :title="item.relativePath">{{ item.relativePath }}</div>
              <div class="upload-queue-file-meta">
                <span>{{ formatFileSize(item.file.size) }}</span>
                <span class="meta-divider">·</span>
                <span :class="['status-text', `status-${item.status}`]">{{ item.error || uploadStatusLabel(item.status) }}</span>
              </div>
              <n-progress
                v-if="item.status !== 'pending'"
                type="line"
                :percentage="item.progress"
                :show-indicator="false"
                :status="item.status === 'failed' ? 'error' : item.status === 'success' ? 'success' : 'default'"
                class="upload-queue-progress"
              />
            </div>
            <button
              class="upload-queue-remove"
              type="button"
              :disabled="uploading"
              :title="t('移除')"
              @click="removeUploadItem(item.id)"
            >
              <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M18 6 6 18" /><path d="m6 6 12 12" /></svg>
            </button>
          </article>
        </div>
      </div>
    </section>
    <template #footer>
      <n-space justify="end">
        <n-button :disabled="uploading" @click="uploadVisible = false">{{ t('取消') }}</n-button>
        <n-button type="primary" :loading="uploading" :disabled="!uploadQueue.length" @click="submitUpload">
          <template #icon>
            <span class="button-icon" aria-hidden="true">
              <svg viewBox="0 0 24 24"><path d="M20 6L9 17l-5-5" /></svg>
            </span>
          </template>
          {{ uploadQueue.length ? t('上传 {count} 个文档', { count: uploadQueue.length }) : t('上传文档') }}
        </n-button>
      </n-space>
    </template>
  </n-modal>

  <!-- 目录新建/编辑 Modal -->
  <n-modal v-model:show="dirEditorVisible" preset="card" :title="dirEditorTitle" style="width: 520px">
    <n-form :model="dirForm" label-placement="left" label-width="90">
      <n-form-item :label="t('目录名称')">
        <n-input v-model:value="dirForm.name" :placeholder="t('请输入目录名称')" />
      </n-form-item>
      <n-form-item v-if="dirEditorMode === 'create'" :label="t('上级目录')">
        <n-select v-model:value="dirForm.parentId" :options="directoryOptionsWithRoot" clearable :placeholder="t('根目录')" />
      </n-form-item>
    </n-form>
    <template #footer>
      <n-space justify="end">
        <n-button @click="dirEditorVisible = false">{{ t('取消') }}</n-button>
        <n-button type="primary" :loading="loading" @click="saveDirectory">{{ t('保存') }}</n-button>
      </n-space>
    </template>
  </n-modal>

  <!-- 目录移动 Modal -->
  <n-modal v-model:show="dirMoveVisible" preset="card" :title="t('移动目录')" style="width: 520px">
    <n-form :model="moveForm" label-placement="left" label-width="90">
      <n-form-item :label="t('目标上级')">
        <n-select v-model:value="moveForm.parentId" :options="moveDirectoryOptions" clearable :placeholder="t('根目录')" />
      </n-form-item>
    </n-form>
    <template #footer>
      <n-space justify="end">
        <n-button @click="dirMoveVisible = false">{{ t('取消') }}</n-button>
        <n-button type="primary" :loading="loading" @click="saveMoveDirectory">{{ t('确认移动') }}</n-button>
      </n-space>
    </template>
  </n-modal>

  <n-modal v-model:show="deleteConfirmVisible" preset="card" :title="t('删除知识文档')" style="width: 460px">
    <div class="delete-confirm">
      <div class="delete-confirm-icon" aria-hidden="true">
        <svg viewBox="0 0 24 24">
          <path d="M3 6h18" />
          <path d="M8 6V4h8v2" />
          <path d="M6 6l1 16h10l1-16" />
          <path d="M10 11v6" />
          <path d="M14 11v6" />
        </svg>
      </div>
      <div class="delete-confirm-body">
        <div class="delete-confirm-title">{{ deleteTarget?.name || t('未命名文档') }}</div>
        <div class="delete-confirm-copy">
          {{ t('删除后列表默认不再展示，该文档的分段、检索索引和向量会同步失效，后续知识问答不会再召回它。') }}
        </div>
      </div>
    </div>
    <template #footer>
      <n-space justify="end">
        <n-button :disabled="deleteSubmitting" @click="closeDeleteConfirm">{{ t('取消') }}</n-button>
        <n-button type="error" :loading="deleteSubmitting" @click="submitDeleteDocument">{{ t('确认删除') }}</n-button>
      </n-space>
    </template>
  </n-modal>

  <n-modal v-model:show="batchDeleteConfirmVisible" preset="card" :title="t('批量删除知识文档')" style="width: 480px">
    <div class="delete-confirm">
      <div class="delete-confirm-icon" aria-hidden="true">
        <svg viewBox="0 0 24 24">
          <path d="M3 6h18" />
          <path d="M8 6V4h8v2" />
          <path d="M6 6l1 16h10l1-16" />
          <path d="M10 11v6" />
          <path d="M14 11v6" />
        </svg>
      </div>
      <div class="delete-confirm-body">
        <div class="delete-confirm-title">{{ selectedBatchDeleteTitle }}</div>
        <div class="delete-confirm-copy">
          {{ t('删除后列表默认不再展示，所选文档的分段、检索索引和向量会同步失效，后续知识问答不会再召回它们。') }}
        </div>
      </div>
    </div>
    <template #footer>
      <n-space justify="end">
        <n-button :disabled="batchDeleteSubmitting" @click="closeBatchDeleteConfirm">{{ t('取消') }}</n-button>
        <n-button type="error" :loading="batchDeleteSubmitting" @click="submitBatchDeleteDocuments">{{ t('确认删除') }}</n-button>
      </n-space>
    </template>
  </n-modal>

  <aside v-if="uploadQueue.length && showFloatPanel" class="upload-float-panel">
    <div class="upload-progress-head">
      <div class="upload-progress-title-wrap">
        <span class="upload-progress-icon">
          <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
            <polyline points="17 8 12 3 7 8" />
            <line x1="12" y1="3" x2="12" y2="15" />
          </svg>
        </span>
        <span class="upload-progress-title">{{ t('上传进度') }}</span>
        <span class="upload-progress-count">({{ uploadFinishedCount }}/{{ uploadQueue.length }})</span>
      </div>
      <button class="upload-progress-close" type="button" @click="closeFloatPanel" :title="t('关闭')">
        <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <line x1="18" y1="6" x2="6" y2="18"></line>
          <line x1="6" y1="6" x2="18" y2="18"></line>
        </svg>
      </button>
    </div>
    <div class="upload-progress-list">
      <article v-for="item in uploadQueue" :key="item.id" class="upload-progress-item">
        <div class="upload-file-icon">
          <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
            <polyline points="14 2 14 8 20 8" />
          </svg>
        </div>
        <div class="upload-file-main">
          <div class="upload-file-name" :title="item.file.name">{{ item.file.name }}</div>
          <div v-if="item.relativePath" class="upload-file-path" :title="item.relativePath">{{ item.relativePath }}</div>
          <div class="upload-file-meta">
            <span>{{ formatFileSize(item.file.size) }}</span>
            <span class="meta-divider">·</span>
            <span :class="['status-text', `status-${item.status}`]">
              {{ item.error || uploadStatusLabel(item.status) }}
            </span>
          </div>
          <div class="progress-bar-container">
            <n-progress
              type="line"
              :percentage="item.progress"
              :show-indicator="false"
              :status="item.status === 'failed' ? 'error' : item.status === 'success' ? 'success' : 'default'"
              class="upload-progress-bar"
            />
          </div>
        </div>
        <div class="upload-item-action">
          <span v-if="item.status === 'success'" class="status-icon success-icon">
            <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
              <polyline points="20 6 9 17 4 12" />
            </svg>
          </span>
          <span v-else-if="item.status === 'failed'" class="status-icon error-icon" :title="item.error">
            <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
              <line x1="18" y1="6" x2="6" y2="18" />
              <line x1="6" y1="6" x2="18" y2="18" />
            </svg>
          </span>
          <span v-else-if="item.status === 'uploading'" class="status-icon spinning-icon">
            <svg class="spinner" viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
              <circle cx="12" cy="12" r="10" stroke-dasharray="40" stroke-dashoffset="10" />
            </svg>
          </span>
          <span v-else class="status-icon pending-icon">
            <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <circle cx="12" cy="12" r="10" />
              <polyline points="12 6 12 12 16 14" />
            </svg>
          </span>
        </div>
      </article>
    </div>
  </aside>
</template>

<script setup lang="ts">
import { computed, h, nextTick, onActivated, onDeactivated, onMounted, onUnmounted, reactive, ref, watch } from 'vue';
import { useRouter } from 'vue-router';
import type { DataTableColumns, DataTableRowKey, SelectOption, TreeOption } from 'naive-ui';
import { NButton, NInputGroup, NProgress, NSpace, NTag, useDialog, useMessage } from 'naive-ui';
import axios from 'axios';
import FileIcon from '@/components/FileIcon.vue';
import DocumentStatus from '@/components/DocumentStatus.vue';
import { t } from '@/composables/i18n';
import { formatAdminDateTime } from '@/composables/adminTimezone';
import {
  deleteKnowledgeDocument,
  fetchKnowledgeDocuments,
  fetchKnowledgeDocumentStats,
  retryKnowledgeDocumentParse,
  uploadKnowledgeDocument,
  type KnowledgeDocumentItem,
  type KnowledgeDocumentStats,
} from '@/api/knowledge-documents';
import {
  fetchDirectoryTree,
  createDirectory,
  updateDirectory,
  moveDirectory,
  deleteDirectory,
  type KnowledgeDirectoryNode,
} from '@/api/knowledge-directories';

type UploadStatus = 'pending' | 'uploading' | 'success' | 'failed';

interface UploadQueueItem {
  id: string;
  file: File;
  relativePath: string;
  status: UploadStatus;
  progress: number;
  error: string;
}

interface UploadFileCandidate {
  file: File;
  relativePath: string;
}

const router = useRouter();
const message = useMessage();
const dialog = useDialog();
const loading = ref(false);
const uploading = ref(false);
const documents = ref<KnowledgeDocumentItem[]>([]);
const stats = ref<KnowledgeDocumentStats>({ total: 0, indexed: 0, failed: 0, local: 0, oss: 0, totalSize: 0 });
const uploadVisible = ref(false);
const uploadQueue = ref<UploadQueueItem[]>([]);
const showFloatPanel = ref(false);
const uploadDragging = ref(false);
const deleteConfirmVisible = ref(false);
const deleteSubmitting = ref(false);
const deleteTarget = ref<KnowledgeDocumentItem | null>(null);
const batchDeleteConfirmVisible = ref(false);
const batchDeleteSubmitting = ref(false);
const selectedDocumentKeys = ref<DataTableRowKey[]>([]);
const fileInputRef = ref<HTMLInputElement | null>(null);
const processingPollTimer = ref<number | null>(null);
const processingPollInFlight = ref(false);

const filters = reactive({
  keyword: '',
  searchScope: 'current' as 'current' | 'all',
  fileType: null as string | null,
  statusValue: null as string | null,
});
const appliedKeyword = ref('');

const pagination = reactive({
  page: 1,
  pageSize: 12,
  total: 0,
});

const LIST_STATE_CACHE_KEY = 'askai:knowledge-documents:list-state';

const acceptTypes = '.pdf,.doc,.docx,.ppt,.pptx,.xls,.xlsx,.txt,.md,.png,.jpg,.jpeg,.webp';
const supportedUploadExtensions = new Set(acceptTypes.split(',').map((item) => item.trim().toLowerCase()));

const statusOptions = computed(() => [
  { label: t('学习成功'), value: 'indexed' },
  { label: t('学习失败'), value: 'failed' },
]);

const searchScopeOptions = computed(() => selectedDirectoryId.value
  ? [
      { label: t('当前目录及子目录'), value: 'current' },
      { label: t('全部目录'), value: 'all' },
    ]
  : [{ label: t('全部目录'), value: 'all' }]);

const effectiveSearchScope = computed<'current' | 'all'>({
  get: () => selectedDirectoryId.value ? filters.searchScope : 'all',
  set: (value) => {
    if (selectedDirectoryId.value) {
      filters.searchScope = value;
    }
  },
});

const fileTypeOptions = computed(() => [
  { label: 'PDF', value: 'pdf' },
  { label: 'Word', value: 'word' },
  { label: 'PPT', value: 'presentation' },
  { label: 'Excel', value: 'spreadsheet' },
  { label: 'Markdown', value: 'markdown' },
  { label: 'Text', value: 'txt' },
  { label: t('图片'), value: 'image' },
]);

const uploadFinishedCount = computed(() =>
  uploadQueue.value.filter((item) => item.status === 'success' || item.status === 'failed').length,
);

const batchDeleteButtonText = computed(() =>
  selectedDocumentKeys.value.length ? `${t('批量删除')} ${selectedDocumentKeys.value.length} ${t('项')}` : t('批量删除'),
);

const selectedBatchDeleteTitle = computed(() => `${t('已选择')} ${selectedDocumentKeys.value.length} ${t('个文档')}`);
const documentTableScrollX = 1078;
const tableScrollbarProps = { trigger: 'none' as const };

const metricCards = computed(() => [
  {
    key: 'total',
    icon: '<svg viewBox="0 0 24 24"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" /><path d="M14 2v6h6" /><path d="M16 13H8" /><path d="M16 17H8" /></svg>',
    label: t('文档总数'),
    value: stats.value.total,
    note: t('当前主账号下的知识文档'),
  },
  {
    key: 'indexed',
    icon: '<svg viewBox="0 0 24 24"><path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20" /><path d="M4 4.5A2.5 2.5 0 0 1 6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5z" /><path d="M9 10l2 2 4-4" /></svg>',
    label: t('已学习'),
    value: stats.value.indexed,
    note: t('后续解析并学习完成后自动更新'),
  },
  {
    key: 'storage',
    icon: '<svg viewBox="0 0 24 24"><ellipse cx="12" cy="5" rx="9" ry="3" /><path d="M3 5v14c0 1.7 4 3 9 3s9-1.3 9-3V5" /><path d="M3 12c0 1.7 4 3 9 3s9-1.3 9-3" /></svg>',
    label: t('文档总容量'),
    value: formatFileSize(stats.value.totalSize),
    note: t('当前主账号下所有知识文档的文件大小合计'),
  },
  {
    key: 'failed',
    icon: '<svg viewBox="0 0 24 24"><path d="M10.3 3.9L1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z" /><path d="M12 9v4" /><path d="M12 17h.01" /></svg>',
    label: t('失败状态'),
    value: stats.value.failed,
    note: t('解析或学习失败状态的文档数'),
  },
]);

const columns = computed<DataTableColumns<KnowledgeDocumentItem>>(() => [
  {
    type: 'selection',
    width: 48,
    fixed: 'left',
  },
  {
    title: t('文档'),
    key: 'name',
    width: 300,
    fixed: 'left',
    render(row) {
      const documentName = formatDocumentDisplayName(row);
      const directoryPath = formatDirectoryPath(row.directoryId);
      return h('div', { class: 'doc-cell' }, [
        h(
          'button',
          {
            type: 'button',
            class: 'doc-title-link',
            style: {
              maxWidth: '100%',
              padding: '0',
              border: '0',
              background: 'transparent',
              color: '#17233d',
              fontSize: '14px',
              overflow: 'hidden',
              cursor: 'pointer',
              textOverflow: 'ellipsis',
              whiteSpace: 'nowrap',
              textAlign: 'left',
              lineHeight: '1.4',
            },
            onMouseenter: (event: MouseEvent) => {
              (event.currentTarget as HTMLElement).style.color = '#366aff';
            },
            onMouseleave: (event: MouseEvent) => {
              (event.currentTarget as HTMLElement).style.color = '#17233d';
            },
            onClick: () => openDetail(row),
          },
          documentName,
        ),
        appliedKeyword.value
          ? h('div', { class: 'doc-directory-path', title: directoryPath }, [
              h('span', { class: 'doc-directory-icon', 'aria-hidden': 'true' }, [
                h('svg', { viewBox: '0 0 24 24', width: 13, height: 13 }, [
                  h('path', { d: 'M3 6.5A2.5 2.5 0 0 1 5.5 4H9l2 2h7.5A2.5 2.5 0 0 1 21 8.5v8A2.5 2.5 0 0 1 18.5 19h-13A2.5 2.5 0 0 1 3 16.5z' }),
                ]),
              ]),
              h('span', { class: 'doc-directory-label' }, `${t('所在目录')}：`),
              h('span', { class: 'doc-directory-value' }, directoryPath),
            ])
          : null,
      ]);
    },
  },
  {
    title: t('类型'),
    key: 'fileExt',
    width: 80,
    align: 'center',
    render(row) {
      return h(FileIcon, { ext: row.fileExt });
    },
  },
  {
    title: t('大小'),
    key: 'fileSize',
    width: 110,
    render(row) {
      return formatFileSize(row.fileSize);
    },
  },
  {
    title: t('状态'),
    key: 'status',
    width: 140,
    render(row) {
      return h(DocumentStatus, { row, onRetry: () => retryParse(row) });
    },
  },
  {
    title: t('更新时间'),
    key: 'updatedAt',
    width: 150,
    render(row) {
      return formatAdminDateTime(row.updatedAt, '-');
    },
  },
  {
    title: t('操作'),
    key: 'actions',
    width: 250,
    render(row) {
      return h(NSpace, { size: 6 }, {
        default: () => [
          h(NButton, { size: 'small', tertiary: true, onClick: () => openDetail(row) }, {
            default: () => actionContent('preview', t('预览')),
          }),
          h(NButton, { size: 'small', tertiary: true, type: 'error', onClick: () => confirmDelete(row) }, {
            default: () => actionContent('delete', t('删除')),
          }),
        ],
      });
    },
  },
]);

function rowKey(row: KnowledgeDocumentItem) {
  return row.id;
}

function handleCheckedRowKeys(keys: DataTableRowKey[]) {
  selectedDocumentKeys.value = keys;
}

function actionContent(type: 'preview' | 'delete', label: string) {
  return h(
    'span',
    {
      class: 'action-button-content',
      style: {
        display: 'inline-flex',
        alignItems: 'center',
        gap: '5px',
      },
    },
    [iconSvg(type), h('span', label)],
  );
}

function iconSvg(type: 'preview' | 'delete') {
  const paths = {
    preview: ['M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7-10-7-10-7z', 'M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6z'],
    delete: ['M3 6h18', 'M8 6V4h8v2', 'M6 6l1 16h10l1-16', 'M10 11v6', 'M14 11v6'],
  };
  return h('span', {
    class: 'button-icon',
    'aria-hidden': 'true',
    style: {
      display: 'inline-flex',
      width: '15px',
      height: '15px',
      flexShrink: '0',
    },
  }, [
    h(
      'svg',
      {
        viewBox: '0 0 24 24',
        fill: 'none',
        stroke: 'currentColor',
        'stroke-width': '2',
        'stroke-linecap': 'round',
        'stroke-linejoin': 'round',
        style: {
          width: '15px',
          height: '15px',
        },
      },
      paths[type].map((d) => h('path', { d })),
    ),
  ]);
}

function statusTagType(value: string) {
  if (value === 'indexed') return 'success';
  if (value === 'failed') return 'error';
  if (value === 'pending_parse') return 'warning';
  if (value === 'parsed') return 'info';
  return 'default';
}

function uploadStatusLabel(value: UploadStatus) {
  const map: Record<UploadStatus, string> = {
    pending: t('待上传'),
    uploading: t('上传中'),
    success: t('完成'),
    failed: t('失败'),
  };
  return map[value];
}

function uploadStatusType(value: UploadStatus) {
  if (value === 'success') return 'success';
  if (value === 'failed') return 'error';
  if (value === 'uploading') return 'info';
  return 'default';
}

function isProcessingDocument(row: KnowledgeDocumentItem) {
  const activeStatuses = ['queued', 'running'];
  return (
    row.status === 'pending_parse' ||
    activeStatuses.includes(row.parseStatus) ||
    activeStatuses.includes(row.chunkStatus) ||
    activeStatuses.includes(row.indexStatus) ||
    ['pending', 'queued', 'running'].includes(row.previewStatus)
  );
}

function hasProcessingDocuments() {
  return documents.value.some(isProcessingDocument);
}

function startProcessingPoll() {
  if (processingPollTimer.value !== null) {
    return;
  }
  processingPollTimer.value = window.setInterval(() => {
    void pollProcessingDocuments();
  }, 5000);
}

function stopProcessingPoll() {
  if (processingPollTimer.value === null) {
    return;
  }
  window.clearInterval(processingPollTimer.value);
  processingPollTimer.value = null;
}

function syncProcessingPoll() {
  if (hasProcessingDocuments()) {
    startProcessingPoll();
  } else {
    stopProcessingPoll();
  }
}

async function pollProcessingDocuments() {
  if (processingPollInFlight.value || !hasProcessingDocuments()) {
    syncProcessingPoll();
    return;
  }
  processingPollInFlight.value = true;
  try {
    await reload({ silent: true });
  } finally {
    processingPollInFlight.value = false;
    syncProcessingPoll();
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

function formatDocumentDisplayName(row: KnowledgeDocumentItem) {
  const name = String(row.name || row.originalFilename || t('未命名文档')).trim();
  const ext = String(row.fileExt || '').trim().replace(/^\./, '');
  if (!ext) {
    return name;
  }
  return name.toLowerCase().endsWith(`.${ext.toLowerCase()}`) ? name : `${name}.${ext}`;
}

function formatDirectoryPath(directoryId?: string) {
  const path = directoryPathMap.value.get(directoryId || '');
  return path ? `${t('根目录')} / ${path}` : t('根目录');
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

function handleSearch() {
  appliedKeyword.value = filters.keyword.trim();
  pagination.page = 1;
  void reload();
}

function handleKeywordUpdate(value: string) {
  if (value.trim()) {
    return;
  }
  filters.keyword = '';
  appliedKeyword.value = '';
  pagination.page = 1;
  void reload();
}

function handleSearchScopeChange() {
  pagination.page = 1;
  persistListState();
  if (appliedKeyword.value) {
    void reload();
  }
}

function handlePageChange() {
  persistListState();
  void reload();
}

function handlePageSizeChange() {
  pagination.page = 1;
  persistListState();
  void reload();
}

function openUpload() {
  uploadQueue.value = [];
  showFloatPanel.value = false;
  if (fileInputRef.value) {
    fileInputRef.value.value = '';
  }
  uploadDirectoryId.value = selectedDirKeys.value[0] || 'root';
  uploadVisible.value = true;
}

function triggerFilePicker() {
  fileInputRef.value?.click();
}

function handleFileChange(event: Event) {
  const input = event.target as HTMLInputElement;
  const files = Array.from(input.files || []);
  if (!files.length) {
    return;
  }
  appendUploadFiles(files);
  input.value = '';
}

function appendUploadFiles(files: File[]) {
  appendUploadCandidates(files.map((file) => ({
    file,
    relativePath: getFileRelativePath(file),
  })));
}

function appendUploadCandidates(candidates: UploadFileCandidate[]) {
  const validCandidates = candidates.filter((item) => isSupportedUploadFile(item.file));
  const skippedCount = candidates.length - validCandidates.length;
  const queuedFileKeys = new Set(uploadQueue.value.map((item) => fileQueueKey(item.file, item.relativePath)));
  const nextItems = validCandidates
    .filter((item) => !queuedFileKeys.has(fileQueueKey(item.file, item.relativePath)))
    .map((file) => ({
      id: `${fileQueueKey(file.file, file.relativePath)}-${Math.random().toString(16).slice(2)}`,
      file: file.file,
      relativePath: file.relativePath,
      status: 'pending' as UploadStatus,
      progress: 0,
      error: '',
    }));
  if (!nextItems.length) {
    message.info(skippedCount ? t('未找到支持的文档类型') : t('所选文件已在列表中'));
    return;
  }
  uploadQueue.value = [...uploadQueue.value, ...nextItems];
  if (skippedCount) {
    message.warning(t('已跳过 {count} 个不支持的文件', { count: skippedCount }));
  }
}

function handleUploadDragEnter() {
  uploadDragging.value = true;
}

function handleUploadDragOver() {
  uploadDragging.value = true;
}

function handleUploadDragLeave(event: DragEvent) {
  const current = event.currentTarget as HTMLElement | null;
  const related = event.relatedTarget as Node | null;
  if (!current || !related || !current.contains(related)) {
    uploadDragging.value = false;
  }
}

async function handleUploadDrop(event: DragEvent) {
  uploadDragging.value = false;
  const candidates = await readDroppedUploadCandidates(event.dataTransfer);
  if (!candidates.length) {
    return;
  }
  appendUploadCandidates(candidates);
}

function removeUploadItem(id: string) {
  if (uploading.value) {
    return;
  }
  uploadQueue.value = uploadQueue.value.filter((item) => item.id !== id);
}

function clearUploadQueue() {
  if (uploading.value) {
    return;
  }
  uploadQueue.value = [];
  if (fileInputRef.value) {
    fileInputRef.value.value = '';
  }
}

function fileQueueKey(file: File, relativePath = '') {
  return `${relativePath || file.name}-${file.size}-${file.lastModified}`;
}

function getFileRelativePath(file: File) {
  return String((file as File & { webkitRelativePath?: string }).webkitRelativePath || '');
}

function isSupportedUploadFile(file: File) {
  const index = file.name.lastIndexOf('.');
  if (index < 0) return false;
  return supportedUploadExtensions.has(file.name.slice(index).toLowerCase());
}

async function readDroppedUploadCandidates(dataTransfer: DataTransfer | null): Promise<UploadFileCandidate[]> {
  if (!dataTransfer) return [];
  const items = Array.from(dataTransfer.items || []);
  const entries = items
    .map((item) => {
      const getter = (item as DataTransferItem & { webkitGetAsEntry?: () => unknown }).webkitGetAsEntry;
      return getter ? getter.call(item) : null;
    })
    .filter(Boolean);
  if (!entries.length) {
    return Array.from(dataTransfer.files || []).map((file) => ({
      file,
      relativePath: getFileRelativePath(file),
    }));
  }
  const results = await Promise.all(entries.map((entry) => readEntryUploadCandidates(entry)));
  return results.flat();
}

function readEntryUploadCandidates(entry: unknown, parentPath = ''): Promise<UploadFileCandidate[]> {
  const item = entry as {
    isFile?: boolean;
    isDirectory?: boolean;
    name?: string;
    file?: (callback: (file: File) => void, errorCallback?: () => void) => void;
    createReader?: () => { readEntries: (callback: (entries: unknown[]) => void, errorCallback?: () => void) => void };
  };
  const entryName = item.name || '';
  const relativePath = parentPath ? `${parentPath}/${entryName}` : entryName;
  if (item.isFile && item.file) {
    return new Promise((resolve) => {
      item.file?.(
        (file) => resolve([{ file, relativePath }]),
        () => resolve([]),
      );
    });
  }
  if (item.isDirectory && item.createReader) {
    const reader = item.createReader();
    return new Promise((resolve) => {
      const entries: unknown[] = [];
      const readBatch = () => {
        reader.readEntries(
          (batch) => {
            if (!batch.length) {
              Promise.all(entries.map((child) => readEntryUploadCandidates(child, relativePath)))
                .then((groups) => resolve(groups.flat()));
              return;
            }
            entries.push(...batch);
            readBatch();
          },
          () => resolve([]),
        );
      };
      readBatch();
    });
  }
  return Promise.resolve([]);
}

function isDuplicateFilenameError(error: unknown) {
  return axios.isAxiosError(error)
    && error.response?.status === 409
    && error.response?.data?.detail?.code === 'DUPLICATE_FILENAME';
}

function confirmAction(content: string, options: { title?: string; positiveText?: string } = {}) {
  return new Promise<boolean>((resolve) => {
    dialog.warning({
      title: options.title || t('确认操作'),
      content,
      positiveText: options.positiveText || t('确认'),
      negativeText: t('取消'),
      onPositiveClick: () => resolve(true),
      onNegativeClick: () => resolve(false),
      onClose: () => resolve(false),
    });
  });
}

function confirmDuplicateReplace(filename: string) {
  return confirmAction(
    t('知识文档中已存在同名文件「{name}」，是否上传并替换原文档？', { name: filename }),
    {
      title: t('同名文件已存在'),
      positiveText: t('替换上传'),
    },
  );
}

async function uploadQueueItem(item: UploadQueueItem, replaceExisting = false) {
  const formData = new FormData();
  formData.append('file', item.file);
  const targetDirId = uploadDirectoryId.value === 'root' ? '' : uploadDirectoryId.value;
  formData.append('directoryId', targetDirId);
  if (replaceExisting) {
    formData.append('replaceExisting', 'true');
  }
  await uploadKnowledgeDocument(formData, (progress) => {
    item.progress = Math.max(item.progress, progress);
  });
}

async function submitUpload() {
  if (!uploadQueue.value.length) {
    message.warning(t('请选择要上传的文档'));
    return;
  }
  uploading.value = true;
  try {
    uploadVisible.value = false;
    showFloatPanel.value = true;
    for (const item of uploadQueue.value) {
      item.status = 'uploading';
      item.progress = 1;
      item.error = '';
      try {
        await uploadQueueItem(item);
        item.status = 'success';
        item.progress = 100;
      } catch (error) {
        if (isDuplicateFilenameError(error)) {
          const shouldReplace = await confirmDuplicateReplace(item.file.name);
          if (shouldReplace) {
            try {
              item.progress = 1;
              await uploadQueueItem(item, true);
              item.status = 'success';
              item.progress = 100;
              continue;
            } catch (replaceError) {
              item.error = readError(replaceError, t('替换失败'));
            }
          } else {
            item.error = t('已取消替换');
          }
        } else {
          item.error = readError(error, t('上传失败'));
        }
        item.status = 'failed';
        item.progress = 100;
      }
    }
    pagination.page = 1;
    await reload();
    await loadDirectories();
  } finally {
    uploading.value = false;
  }
}

async function closeFloatPanel() {
  if (uploading.value) {
    const confirmed = await confirmAction(
      t('正在上传中，隐藏窗口不会取消上传，确定隐藏吗？'),
      { title: t('确认隐藏上传进度') },
    );
    if (!confirmed) {
      return;
    }
  }
  showFloatPanel.value = false;
  if (!uploading.value) {
    uploadQueue.value = [];
  }
}

function openDetail(row: KnowledgeDocumentItem) {
  void router.push({ name: 'KnowledgeDocumentDetail', params: { id: row.id } });
}

function confirmDelete(row: KnowledgeDocumentItem) {
  deleteTarget.value = row;
  deleteConfirmVisible.value = true;
}

function confirmBatchDelete() {
  if (!selectedDocumentKeys.value.length) return;
  batchDeleteConfirmVisible.value = true;
}

function closeDeleteConfirm() {
  if (deleteSubmitting.value) return;
  deleteConfirmVisible.value = false;
  deleteTarget.value = null;
}

async function submitDeleteDocument() {
  const target = deleteTarget.value;
  if (!target || deleteSubmitting.value) return;
  deleteSubmitting.value = true;
  try {
    await deleteKnowledgeDocument(target.id);
    message.success(t('已删除文档并同步失效检索索引'));
    deleteConfirmVisible.value = false;
    deleteTarget.value = null;
    await reload();
    await loadDirectories();
  } catch (error) {
    message.error(readError(error, t('删除失败')));
  } finally {
    deleteSubmitting.value = false;
  }
}

function closeBatchDeleteConfirm() {
  if (batchDeleteSubmitting.value) return;
  batchDeleteConfirmVisible.value = false;
}

async function submitBatchDeleteDocuments() {
  const ids = selectedDocumentKeys.value.map(String).filter(Boolean);
  if (!ids.length || batchDeleteSubmitting.value) return;
  batchDeleteSubmitting.value = true;
  try {
    await Promise.all(ids.map((id) => deleteKnowledgeDocument(id)));
    message.success(`${t('已删除')} ${ids.length} ${t('个文档并同步失效检索索引')}`);
    selectedDocumentKeys.value = [];
    batchDeleteConfirmVisible.value = false;
    await reload();
    await loadDirectories();
  } catch (error) {
    message.error(readError(error, t('批量删除失败')));
  } finally {
    batchDeleteSubmitting.value = false;
  }
}

async function retryParse(row: KnowledgeDocumentItem) {
  try {
    await retryKnowledgeDocumentParse(row.id);
    message.success(t('已重新提交学习任务'));
    await reload({ silent: true });
    syncProcessingPoll();
  } catch (error) {
    message.error(readError(error, t('重新学习失败')));
  }
}

// ================== 知识目录相关的业务状态与逻辑 ==================
const directories = ref<KnowledgeDirectoryNode[]>([]);
const treeKeyword = ref('');
const selectedDirKeys = ref<string[]>(['root']);
const expandedDirKeys = ref<string[]>([]);
const uploadDirectoryId = ref<string>('root');
const restoringListState = ref(false);

const selectedDirId = computed(() => {
  const key = selectedDirKeys.value[0] || 'root';
  return key === 'root' ? '' : key;
});
const selectedDirectory = computed(() => selectedDirId.value ? findDirectoryById(directories.value, selectedDirId.value) : null);
const selectedDirectoryDocumentCount = computed(() => {
  const target = selectedDirectory.value;
  return target ? Number(target.totalDocumentCount ?? target.documentCount ?? 0) : 0;
});
const deleteDirectoryDisabled = computed(() => !selectedDirId.value || selectedDirectoryDocumentCount.value > 0);
const deleteDirectoryDisabledReason = computed(() => {
  if (!selectedDirId.value) {
    return t('请选择目录');
  }
  if (selectedDirectoryDocumentCount.value > 0) {
    return t('该目录或其子目录下存在知识文档，无法删除');
  }
  return t('删除');
});

const selectedDirectoryId = computed(() => {
  const key = selectedDirKeys.value[0] || 'root';
  return key === 'root' ? null : key;
});

const treeOptions = computed<TreeOption[]>(() => {
  const nodes = toTreeOptions(directories.value);
  return [
    {
      key: 'root',
      label: `${t('全部文档')} (${stats.value.total})`,
      rawName: t('全部文档'),
      totalDocumentCount: stats.value.total,
      isRoot: true,
      children: nodes,
    }
  ];
});

const directoryOptionsWithRoot = computed<SelectOption[]>(() => {
  return flattenDirectoryOptions(directories.value, true);
});

const directoryOptions = computed<SelectOption[]>(() => {
  return flattenDirectoryOptions(directories.value, false);
});

const directoryPathMap = computed(() => {
  const paths = new Map<string, string>();
  const visit = (nodes: KnowledgeDirectoryNode[], lineage: string[] = []) => {
    for (const node of nodes) {
      const nextLineage = [...lineage, node.name];
      paths.set(node.id, nextLineage.join(' / '));
      visit(node.children || [], nextLineage);
    }
  };
  visit(directories.value);
  return paths;
});

const selectedMoveBlockedDirectoryIds = computed(() => {
  if (!selectedDirId.value || selectedDirId.value === 'root') {
    return new Set<string>();
  }
  const target = findDirectoryById(directories.value, selectedDirId.value);
  return new Set(target ? collectDirectoryIds([target]) : [selectedDirId.value]);
});

const moveDirectoryOptions = computed<SelectOption[]>(() => {
  return flattenDirectoryOptions(directories.value, true, selectedMoveBlockedDirectoryIds.value);
});

function toTreeOptions(nodes: KnowledgeDirectoryNode[]): TreeOption[] {
  return nodes.map((node) => ({
    key: node.id,
    label: `${node.name} (${node.totalDocumentCount})`,
    rawName: node.name,
    totalDocumentCount: node.totalDocumentCount,
    children: toTreeOptions(node.children || []),
  }));
}

function renderTreeLabel(info: { option: TreeOption & { rawName?: string; totalDocumentCount?: number; isRoot?: boolean } }) {
  const nodeId = String(info.option.key);
  const name = info.option.rawName || String(info.option.label || '');
  const count = Number(info.option.totalDocumentCount ?? 0);
  const isRoot = info.option.isRoot || false;
  return h('div', { class: 'dept-node-label' }, [
    h('span', { class: 'dept-node-title' }, `${name} (${count})`),
    h('span', { class: 'dept-node-actions' }, [
      h(
        'button',
        {
          class: 'dept-node-action',
          title: t('新增子目录'),
          onClick: (event: MouseEvent) => {
            event.preventDefault();
            event.stopPropagation();
            selectedDirKeys.value = [nodeId];
            openCreateDir(nodeId);
          },
        },
        '+',
      ),
      !isRoot ? h(
        'button',
        {
          class: 'dept-node-action',
          title: t('编辑目录'),
          onClick: (event: MouseEvent) => {
            event.preventDefault();
            event.stopPropagation();
            selectedDirKeys.value = [nodeId];
            openEditDir(nodeId);
          },
        },
        '✎',
      ) : null,
    ]),
  ]);
}

function flattenDirectoryOptions(nodes: KnowledgeDirectoryNode[], includeRoot: boolean, excludeIds: Set<string> = new Set()): SelectOption[] {
  const result: SelectOption[] = includeRoot ? [{ label: t('根目录'), value: 'root' }] : [];
  const dfs = (items: KnowledgeDirectoryNode[], lineage: string[] = []) => {
    for (const item of items) {
      if (excludeIds.has(item.id)) {
        continue;
      }
      const nextLineage = [...lineage, item.name];
      result.push({ label: nextLineage.join(' / '), value: item.id });
      dfs(item.children || [], nextLineage);
    }
  };
  dfs(nodes);
  return result;
}

function collectDirectoryIds(nodes: KnowledgeDirectoryNode[]): string[] {
  const ids: string[] = [];
  const dfs = (items: KnowledgeDirectoryNode[]) => {
    for (const item of items) {
      ids.push(item.id);
      dfs(item.children || []);
    }
  };
  dfs(nodes);
  return ids;
}

function handleSelectDirectory(keys: Array<string | number>) {
  const nextKeys = keys.map(String);
  selectedDirKeys.value = nextKeys.length ? nextKeys : ['root'];
}

function handleExpandDirectories(keys: Array<string | number>) {
  expandedDirKeys.value = keys.map(String);
}

watch(selectedDirectoryId, () => {
  if (restoringListState.value) {
    return;
  }
  pagination.page = 1;
  persistListState();
  void reload();
});

const dirEditorVisible = ref(false);
const dirEditorMode = ref<'create' | 'edit'>('create');
const dirForm = ref({
  id: '',
  name: '',
  parentId: null as string | null,
});
const dirEditorTitle = computed(() => dirEditorMode.value === 'create' ? t('新增目录') : t('编辑目录'));

const dirMoveVisible = ref(false);
const moveForm = ref({
  parentId: null as string | null,
});

function openCreateDir(parentId?: string | null) {
  dirEditorMode.value = 'create';
  const resolvedParentId = parentId || selectedDirId.value || null;
  dirForm.value = {
    id: '',
    name: '',
    parentId: resolvedParentId === 'root' ? null : resolvedParentId,
  };
  dirEditorVisible.value = true;
}

function openEditDir(dirId?: string | null) {
  const targetId = dirId || selectedDirId.value;
  if (!targetId || targetId === 'root') return;
  const target = findDirectoryById(directories.value, targetId);
  if (!target) return;
  dirEditorMode.value = 'edit';
  dirForm.value = {
    id: target.id,
    name: target.name,
    parentId: target.parentId,
  };
  dirEditorVisible.value = true;
}

function openMoveDir() {
  if (!selectedDirId.value || selectedDirId.value === 'root') return;
  moveForm.value.parentId = null;
  dirMoveVisible.value = true;
}

function findDirectoryById(nodes: KnowledgeDirectoryNode[], id: string): KnowledgeDirectoryNode | null {
  for (const node of nodes) {
    if (node.id === id) return node;
    const sub = findDirectoryById(node.children || [], id);
    if (sub) return sub;
  }
  return null;
}

function persistListState() {
  try {
    window.localStorage.setItem(
      LIST_STATE_CACHE_KEY,
      JSON.stringify({
        selectedDirKey: selectedDirKeys.value[0] || 'root',
        page: pagination.page,
        pageSize: pagination.pageSize,
        searchScope: filters.searchScope,
      }),
    );
  } catch {
    // localStorage can be unavailable in restricted browser modes.
  }
}

function restoreListState() {
  try {
    const raw = window.localStorage.getItem(LIST_STATE_CACHE_KEY);
    if (!raw) {
      return;
    }
    const parsed = JSON.parse(raw) as { selectedDirKey?: unknown; page?: unknown; pageSize?: unknown; searchScope?: unknown };
    const selectedDirKey = typeof parsed.selectedDirKey === 'string' && parsed.selectedDirKey ? parsed.selectedDirKey : 'root';
    const page = Number(parsed.page);
    const pageSize = Number(parsed.pageSize);
    selectedDirKeys.value = [selectedDirKey];
    if (Number.isInteger(page) && page > 0) {
      pagination.page = page;
    }
    if (Number.isInteger(pageSize) && [10, 12, 20, 50].includes(pageSize)) {
      pagination.pageSize = pageSize;
    }
    if (parsed.searchScope === 'current' || parsed.searchScope === 'all') {
      filters.searchScope = parsed.searchScope;
    }
  } catch {
    window.localStorage.removeItem(LIST_STATE_CACHE_KEY);
  }
}

async function saveDirectory() {
  if (!dirForm.value.name.trim()) {
    message.warning(t('请填写目录名称'));
    return;
  }
  loading.value = true;
  try {
    if (dirEditorMode.value === 'create') {
      const parentId = dirForm.value.parentId === 'root' ? null : dirForm.value.parentId;
      await createDirectory({
        name: dirForm.value.name.trim(),
        parentId,
      });
      message.success(t('目录已创建'));
    } else {
      await updateDirectory(dirForm.value.id, {
        name: dirForm.value.name.trim(),
      });
      message.success(t('目录已更新'));
    }
    dirEditorVisible.value = false;
    await loadDirectories();
    await reload();
  } catch (error) {
    message.error(readError(error, t('保存失败')));
  } finally {
    loading.value = false;
  }
}

async function saveMoveDirectory() {
  if (!selectedDirId.value || selectedDirId.value === 'root') return;
  const parentId = moveForm.value.parentId === 'root' ? null : moveForm.value.parentId;
  loading.value = true;
  try {
    await moveDirectory(selectedDirId.value, { parentId });
    message.success(t('目录已移动'));
    dirMoveVisible.value = false;
    await loadDirectories();
    await reload();
  } catch (error) {
    message.error(readError(error, t('移动失败')));
  } finally {
    loading.value = false;
  }
}

async function deleteSelectedDir() {
  if (!selectedDirId.value || selectedDirId.value === 'root') return;
  const target = selectedDirectory.value;
  if (!target) return;
  if (selectedDirectoryDocumentCount.value > 0) {
    message.warning(t('该目录或其子目录下存在知识文档，无法删除'));
    return;
  }
  const confirmed = await confirmAction(
    t('确认删除目录「{name}」？', { name: target.name }),
    { title: t('删除目录') },
  );
  if (!confirmed) return;
  
  try {
    await deleteDirectory(selectedDirId.value);
    message.success(t('目录已删除'));
    selectedDirKeys.value = ['root'];
    await loadDirectories();
    await reload();
  } catch (error) {
    message.error(readError(error, t('删除失败')));
  }
}

async function loadDirectories() {
  try {
    const data = await fetchDirectoryTree();
    directories.value = data;
    if (selectedDirId.value && !findDirectoryById(data, selectedDirId.value)) {
      selectedDirKeys.value = ['root'];
      pagination.page = 1;
      persistListState();
    }
    expandedDirKeys.value = ['root', ...collectDirIds(data)];
  } catch (error) {
    console.error(error);
  }
}

function collectDirIds(nodes: KnowledgeDirectoryNode[]): string[] {
  const ids: string[] = [];
  const dfs = (items: KnowledgeDirectoryNode[]) => {
    for (const item of items) {
      ids.push(item.id);
      if (item.children?.length) {
        dfs(item.children);
      }
    }
  };
  dfs(nodes);
  return ids;
}

async function reload(options: { silent?: boolean } = {}) {
  if (!options.silent) {
    loading.value = true;
  }
  persistListState();
  try {
    const keyword = appliedKeyword.value;
    const [statsResult, listResult] = await Promise.all([
      fetchKnowledgeDocumentStats(),
      fetchKnowledgeDocuments({
        page: pagination.page,
        pageSize: pagination.pageSize,
        keyword,
        fileType: filters.fileType,
        statusValue: filters.statusValue,
        directoryId: keyword ? undefined : selectedDirectoryId.value || undefined,
        directoryScopeId:
          keyword && filters.searchScope === 'current'
            ? selectedDirectoryId.value || undefined
            : undefined,
        sortField: 'updatedAt',
        sortOrder: 'descend',
      }),
    ]);
    stats.value = statsResult;
    documents.value = listResult.items;
    const visibleIds = new Set(listResult.items.map((item) => item.id));
    selectedDocumentKeys.value = selectedDocumentKeys.value.filter((id) => visibleIds.has(String(id)));
    pagination.total = listResult.total;
  } catch (error) {
    if (options.silent) {
      console.warn(readError(error, t('知识文档加载失败')));
    } else {
      message.error(readError(error, t('知识文档加载失败')));
    }
  } finally {
    if (!options.silent) {
      loading.value = false;
    }
  }
}

async function initializePage() {
  restoringListState.value = true;
  restoreListState();
  await nextTick();
  restoringListState.value = false;
  await loadDirectories();
  await reload();
}

onMounted(initializePage);
onActivated(initializePage);
onDeactivated(stopProcessingPoll);
onUnmounted(stopProcessingPoll);

watch(documents, syncProcessingPoll, { deep: true });
</script>

<style scoped>
.knowledge-page {
  height: calc(100vh - 92px);
  min-height: 0;
  min-width: 0;
  max-width: 100%;
  display: flex;
  flex-direction: column;
  gap: 16px;
  overflow: hidden;
}

.shell-card {
  border: 1px solid #e6ebf5;
  border-radius: 14px;
  background: #fff;
  box-shadow: 0 6px 20px rgba(16, 38, 84, 0.05);
}

.metrics-row {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
  padding: 12px;
}

.metric-card {
  border-radius: 8px;
}

.list-workspace {
  width: calc(100% - 24px);
  margin: -16px 12px 0;
  flex: 1;
  min-height: 0;
  min-width: 0;
  max-width: calc(100% - 24px);
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.metric-card {
  position: relative;
  border: 1px solid #e6ebf5;
  background: #fff;
  box-shadow: 0 4px 12px rgba(29, 54, 110, 0.04);
}

.metric-main {
  display: flex;
  align-items: flex-start;
  gap: 12px;
}

.metric-body {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.metric-icon {
  width: 44px;
  height: 44px;
  border-radius: 50%;
  display: grid;
  place-items: center;
}

.metric-icon :deep(svg) {
  width: 20px;
  height: 20px;
  fill: none;
  stroke: currentColor;
  stroke-width: 2;
  stroke-linecap: round;
  stroke-linejoin: round;
}

.metric-icon-total {
  color: #2d63ff;
  background: #eaf0ff;
}

.metric-icon-indexed {
  color: #0f9964;
  background: #e8f8ef;
}

.metric-icon-storage {
  color: #7456e0;
  background: #f0ebff;
}

.metric-icon-failed {
  color: #b42318;
  background: #fff1f2;
}

.metric-label {
  color: #606f8a;
  font-size: 12px;
  line-height: 1.3;
}

.metric-value {
  color: #0f1f45;
  font-size: 24px;
  font-weight: 600;
  line-height: 1.1;
}

.metric-help-icon {
  position: absolute;
  top: 12px;
  right: 12px;
  display: inline-flex;
  width: 20px;
  height: 20px;
  align-items: center;
  justify-content: center;
  color: #93a1b7;
  cursor: help;
  transition: color 0.2s ease;
}

.metric-help-icon svg {
  width: 18px;
  height: 18px;
  fill: none;
  stroke: currentColor;
  stroke-width: 2;
  stroke-linecap: round;
  stroke-linejoin: round;
  shape-rendering: geometricPrecision;
}

.metric-help-icon:hover,
.metric-help-icon:focus {
  color: #366aff;
}

.metric-help-tooltip {
  position: absolute;
  top: 26px;
  right: 0;
  z-index: 20;
  width: max-content;
  max-width: 240px;
  padding: 7px 9px;
  border-radius: 6px;
  background: rgba(15, 23, 42, 0.94);
  color: #fff;
  font-size: 12px;
  line-height: 1.5;
  pointer-events: none;
  opacity: 0;
  transform: translateY(-2px);
  transition: opacity 0.15s ease, transform 0.15s ease;
  white-space: normal;
}

.metric-help-tooltip::before {
  position: absolute;
  top: -4px;
  right: 7px;
  width: 8px;
  height: 8px;
  background: rgba(15, 23, 42, 0.94);
  content: "";
  transform: rotate(45deg);
}

.metric-help-icon:hover .metric-help-tooltip,
.metric-help-icon:focus .metric-help-tooltip {
  opacity: 1;
  transform: translateY(0);
}

.filter-toolbar {
  align-items: center;
  display: flex;
  justify-content: space-between;
  gap: 14px;
  width: max-content;
  min-width: 100%;
  flex-wrap: nowrap;
}

.filter-left,
.filter-right {
  display: flex;
  align-items: center;
  flex: 0 0 auto;
  gap: 10px;
  flex-wrap: nowrap;
}

.document-search-group {
  width: 390px;
}

.search-scope-select {
  width: 158px;
  flex: 0 0 158px;
}

.compact-filter-select {
  width: 112px;
  flex: 0 0 112px;
}

.keyword-input {
  min-width: 180px;
}

.button-icon {
  display: inline-flex;
  width: 16px;
  height: 16px;
}

.button-icon svg {
  width: 16px;
  height: 16px;
  fill: none;
  stroke: currentColor;
  stroke-width: 2;
  stroke-linecap: round;
  stroke-linejoin: round;
}

.list-filter-row {
  padding: 0 0 10px;
  margin: 0 0 12px;
  border-bottom: 1px solid #edf1f7;
  overflow-x: auto;
  overflow-y: hidden;
  scrollbar-width: thin;
  scrollbar-color: #c8d3e5 transparent;
}

.list-filter-row::-webkit-scrollbar {
  height: 6px;
}

.list-filter-row::-webkit-scrollbar-thumb {
  border-radius: 3px;
  background: #c8d3e5;
}

.list-body {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-height: 0;
  overflow: hidden;
}

.document-list-spin {
  flex: 1;
  min-height: 0;
}

.document-list-spin :deep(.n-spin-container),
.document-list-spin :deep(.n-spin-content) {
  height: 100%;
  min-height: 0;
}

.document-list-spin :deep(.n-spin-content) {
  display: flex;
  flex-direction: column;
}

.table-scroll-shell {
  flex: 1;
  min-height: 0;
  overflow: hidden;
}

.documents-table {
  height: 100%;
  min-height: 0;
}

.documents-table :deep(.n-data-table-wrapper),
.documents-table :deep(.n-data-table-base-table),
.documents-table :deep(.n-data-table-base-table-body) {
  min-height: 0;
}

:deep(.doc-cell) {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 3px;
}

:deep(.doc-title-link) {
  max-width: 100%;
  padding: 0;
  border: 0;
  background: transparent;
  color: #17233d;
  font-size: 14px;
  font-weight: 400;
  overflow: hidden;
  cursor: pointer;
  text-overflow: ellipsis;
  white-space: nowrap;
  text-align: left;
}

:deep(.doc-title-link:hover) {
  color: #366aff;
}

:deep(.doc-directory-path) {
  display: inline-flex;
  align-items: center;
  align-self: flex-start;
  max-width: 100%;
  min-width: 0;
  padding: 2px 6px;
  border-radius: 4px;
  background: #f1f5fb;
  color: #64748b;
  font-size: 12px;
  line-height: 1.4;
}

:deep(.doc-directory-icon) {
  display: inline-flex;
  flex: 0 0 auto;
  width: 13px;
  height: 13px;
  margin-right: 4px;
  color: #5b7fbd;
}

:deep(.doc-directory-icon svg) {
  width: 100%;
  height: 100%;
  fill: none;
  stroke: currentColor;
  stroke-width: 1.8;
  stroke-linecap: round;
  stroke-linejoin: round;
}

:deep(.doc-directory-label) {
  flex: 0 0 auto;
  color: #52657f;
  font-weight: 600;
}

:deep(.doc-directory-value) {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.table-pagination {
  display: flex;
  justify-content: flex-end;
  padding: 16px 2px 0;
}

.upload-picker {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.upload-drop {
  width: 100%;
  min-height: 220px;
  padding: 28px;
  border: 1px dashed #b8c7e6;
  border-radius: 8px;
  background: #f8fbff;
  color: inherit;
  cursor: pointer;
  display: grid;
  place-content: center;
  justify-items: center;
  gap: 10px;
  text-align: center;
  transition:
    border-color 0.2s ease,
    background-color 0.2s ease;
}

.upload-drop:hover {
  border-color: #366aff;
  background: #f3f7ff;
}

.upload-picker.is-dragging .upload-drop {
  border-color: #366aff;
  background: #eef4ff;
  box-shadow: inset 0 0 0 1px rgba(54, 106, 255, 0.18);
}

.upload-drop-icon {
  display: grid;
  width: 54px;
  height: 54px;
  place-items: center;
  border-radius: 12px;
  background: #eaf0ff;
  color: #366aff;
}

.upload-drop-icon svg {
  width: 26px;
  height: 26px;
  fill: none;
  stroke: currentColor;
  stroke-width: 2;
  stroke-linecap: round;
  stroke-linejoin: round;
}

.upload-drop-title {
  color: #17233d;
  font-size: 16px;
  font-weight: 800;
}

.upload-drop-copy {
  max-width: 320px;
  color: #687789;
  font-size: 13px;
  line-height: 1.6;
}

.upload-queue-panel {
  min-width: 0;
  overflow: hidden;
  border: 1px solid #edf1f7;
  border-radius: 8px;
  background: #fff;
}

.upload-queue-head {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto auto;
  align-items: center;
  gap: 10px;
  padding: 10px 12px;
  border-bottom: 1px solid #edf1f7;
}

.upload-queue-title {
  min-width: 0;
  color: #17233d;
  font-size: 14px;
  font-weight: 700;
}

.upload-queue-count {
  color: #687789;
  font-size: 12px;
  white-space: nowrap;
}

.upload-queue-clear,
.upload-queue-remove {
  border: 0;
  background: transparent;
  color: #687789;
  cursor: pointer;
}

.upload-queue-clear {
  min-height: 28px;
  padding: 0 6px;
  font-size: 12px;
}

.upload-queue-clear:hover,
.upload-queue-remove:hover {
  color: #e5484d;
}

.upload-queue-clear:disabled,
.upload-queue-remove:disabled {
  color: #c2cad8;
  cursor: not-allowed;
}

.upload-queue-list {
  max-height: min(260px, 34vh);
  overflow-y: auto;
  overscroll-behavior: contain;
  padding: 8px;
  scrollbar-gutter: stable;
  scrollbar-width: thin;
  scrollbar-color: #c9d3e4 transparent;
}

.upload-queue-list::-webkit-scrollbar {
  width: 8px;
}

.upload-queue-list::-webkit-scrollbar-track {
  background: transparent;
}

.upload-queue-list::-webkit-scrollbar-thumb {
  border: 2px solid #fff;
  border-radius: 999px;
  background: #c9d3e4;
}

.upload-queue-list::-webkit-scrollbar-thumb:hover {
  background: #9eadc4;
}

.upload-queue-item {
  display: grid;
  grid-template-columns: 34px minmax(0, 1fr) 32px;
  align-items: start;
  gap: 10px;
  padding: 10px 8px;
  border-radius: 8px;
}

.upload-queue-item + .upload-queue-item {
  border-top: 1px solid #f2f4f8;
}

.upload-queue-item:hover {
  background: #f8fbff;
}

.upload-queue-file-icon {
  display: grid;
  width: 34px;
  height: 34px;
  place-items: center;
  border-radius: 8px;
  background: #eef4ff;
  color: #366aff;
}

.upload-queue-file-icon svg {
  width: 18px;
  height: 18px;
  fill: none;
  stroke: currentColor;
  stroke-width: 2;
  stroke-linecap: round;
  stroke-linejoin: round;
}

.upload-queue-file-main {
  min-width: 0;
}

.upload-queue-file-name {
  overflow: hidden;
  color: #17233d;
  font-size: 13px;
  font-weight: 600;
  line-height: 1.35;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.upload-queue-file-path,
.upload-file-path {
  overflow: hidden;
  margin-top: 2px;
  color: #8a96a8;
  font-size: 12px;
  line-height: 1.35;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.upload-queue-file-meta {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-top: 3px;
  color: #687789;
  font-size: 12px;
}

.upload-queue-progress {
  margin-top: 8px;
}

.upload-queue-remove {
  display: grid;
  width: 32px;
  height: 32px;
  place-items: center;
  border-radius: 6px;
}

.upload-queue-remove:hover {
  background: #fff1f2;
}

.upload-queue-remove svg {
  width: 15px;
  height: 15px;
  fill: none;
  stroke: currentColor;
  stroke-width: 2;
  stroke-linecap: round;
  stroke-linejoin: round;
}

.upload-float-panel {
  position: fixed;
  right: 24px;
  bottom: 24px;
  z-index: 1000;
  width: 380px;
  max-height: 400px;
  display: flex;
  flex-direction: column;
  padding: 16px;
  border: 1px solid rgba(226, 232, 240, 0.8);
  border-radius: 12px;
  background: rgba(255, 255, 255, 0.95);
  backdrop-filter: blur(8px);
  box-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.1), 0 10px 10px -5px rgba(0, 0, 0, 0.04);
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  animation: slide-in 0.3s ease-out;
}

@keyframes slide-in {
  from {
    transform: translateY(20px);
    opacity: 0;
  }
  to {
    transform: translateY(0);
    opacity: 1;
  }
}

.upload-progress-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding-bottom: 12px;
  border-bottom: 1px solid #f1f5f9;
  margin-bottom: 12px;
}

.upload-progress-title-wrap {
  display: flex;
  align-items: center;
  gap: 8px;
}

.upload-progress-icon {
  display: flex;
  color: #366aff;
}

.upload-progress-title {
  color: #1e293b;
  font-size: 15px;
  font-weight: 600;
}

.upload-progress-count {
  color: #64748b;
  font-size: 13px;
  font-weight: 500;
}

.upload-progress-close {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  border: none;
  border-radius: 6px;
  background: transparent;
  color: #64748b;
  cursor: pointer;
  transition: all 0.2s ease;
}

.upload-progress-close:hover {
  background: #f1f5f9;
  color: #0f172a;
}

.upload-progress-list {
  flex: 1;
  min-height: 0;
  max-height: 280px;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding-right: 4px;
}

.upload-progress-list::-webkit-scrollbar {
  width: 6px;
}
.upload-progress-list::-webkit-scrollbar-track {
  background: transparent;
}
.upload-progress-list::-webkit-scrollbar-thumb {
  background: #cbd5e1;
  border-radius: 3px;
}
.upload-progress-list::-webkit-scrollbar-thumb:hover {
  background: #94a3b8;
}

.upload-progress-item {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  padding: 12px;
  border: 1px solid #f1f5f9;
  border-radius: 8px;
  background: #f8fafc;
  transition: all 0.2s ease;
}

.upload-progress-item:hover {
  border-color: #e2e8f0;
  background: #f1f5f9;
}

.upload-file-icon {
  display: flex;
  color: #64748b;
  padding-top: 2px;
}

.upload-file-main {
  flex: 1;
  min-width: 0;
}

.upload-file-name {
  color: #1e293b;
  font-size: 13px;
  font-weight: 600;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  line-height: 1.4;
}

.upload-file-meta {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-top: 2px;
  color: #64748b;
  font-size: 11px;
}

.meta-divider {
  color: #cbd5e1;
}

.status-text {
  font-weight: 500;
}

.status-success {
  color: #10b981;
}

.status-failed {
  color: #ef4444;
}

.status-uploading {
  color: #3b82f6;
}

.progress-bar-container {
  margin-top: 8px;
}

.upload-progress-bar {
  margin-top: 0;
}

.upload-item-action {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 20px;
  height: 20px;
  margin-top: 2px;
}

.status-icon {
  display: flex;
  align-items: center;
  justify-content: center;
}

.success-icon {
  color: #10b981;
}

.error-icon {
  color: #ef4444;
}

.spinning-icon {
  color: #3b82f6;
}

.spinning-icon .spinner {
  animation: spin 1s linear infinite;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}

.pending-icon {
  color: #94a3b8;
}

.hidden-file-input {
  display: none;
}

.knowledge-layout {
  height: 100%;
  display: grid;
  grid-template-columns: clamp(200px, 17vw, 250px) minmax(0, 1fr);
  gap: 14px;
  min-width: 0;
  max-width: 100%;
  overflow: hidden;
}

.dept-panel {
  border: 1px solid #eceff5;
  border-radius: 10px;
  padding: 10px;
  display: flex;
  flex-direction: column;
  gap: 10px;
  min-width: 0;
  overflow: hidden;
}

.panel-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.panel-title {
  font-size: 14px;
  font-weight: 600;
}

.tree-wrap {
  flex: 1;
  min-height: 0;
  overflow: auto;
}

:deep(.dept-node-label) {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  width: 100%;
}

:deep(.dept-node-title) {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

:deep(.dept-node-actions) {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  opacity: 0;
  transition: opacity 0.15s ease;
}

:deep(.n-tree-node-content:hover .dept-node-actions) {
  opacity: 1;
}

:deep(.dept-node-action) {
  width: 18px;
  height: 18px;
  border: 1px solid #d9dce4;
  border-radius: 4px;
  background: #fff;
  color: #51607a;
  font-size: 11px;
  line-height: 1;
  cursor: pointer;
  padding: 0;
}

:deep(.dept-node-action:hover) {
  border-color: #9fb5ff;
  color: #366aff;
}

.list-panel {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
  min-width: 0;
  max-width: 100%;
  overflow: hidden;
}

.delete-confirm {
  display: flex;
  gap: 14px;
  align-items: flex-start;
}

.delete-confirm-icon {
  display: flex;
  width: 42px;
  height: 42px;
  flex: 0 0 auto;
  align-items: center;
  justify-content: center;
  border-radius: 10px;
  background: #fff1f0;
  color: #d03050;
}

.delete-confirm-icon svg {
  width: 21px;
  height: 21px;
  fill: none;
  stroke: currentColor;
  stroke-width: 2;
  stroke-linecap: round;
  stroke-linejoin: round;
}

.delete-confirm-body {
  min-width: 0;
}

.delete-confirm-title {
  margin-bottom: 6px;
  overflow-wrap: anywhere;
  color: #1f2937;
  font-size: 15px;
  font-weight: 650;
  line-height: 1.45;
}

.delete-confirm-copy {
  color: #64748b;
  font-size: 13px;
  line-height: 1.7;
}
</style>
