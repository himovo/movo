<template src="./KnowledgeDocumentsPageTemplate.html"></template>

<script setup lang="ts">
import { useKnowledgeListState } from './useKnowledgeListState';
import { useKnowledgeUploadQueue } from './useKnowledgeUploadQueue';
import { toTreeOptions, flattenDirectoryOptions, collectDirectoryIds, findDirectoryById, collectDirIds } from './knowledgeDirectoryHelpers';
import { acceptTypes, fileQueueKey, getFileRelativePath, isSupportedUploadFile, readDroppedUploadCandidates, type UploadFileCandidate, type UploadQueueItem, type UploadStatus } from './knowledgeUploadFiles';
import { computed, h, nextTick, onActivated, onDeactivated, onMounted, onUnmounted, reactive, ref, watch } from 'vue';
import { useRouter } from 'vue-router';
import type { DataTableColumns, DataTableRowKey, SelectOption, TreeOption } from 'naive-ui';
import { NButton, NDropdown, NInputGroup, NProgress, NSpace, NTag, useDialog, useMessage } from 'naive-ui';
import axios from 'axios';
import adminProductUiExtension from '@movo-admin-product-extension';
import FileIcon from '@/components/FileIcon.vue';
import DocumentStatus from '@/components/DocumentStatus.vue';
import { t } from '@/composables/i18n';
import { localizedServerText } from '@/utils/serverText';
import { formatAdminDateTime } from '@/composables/adminTimezone';
import {
  deleteKnowledgeDocument,
  fetchKnowledgeDocuments,
  fetchKnowledgeDocumentStats,
  uploadKnowledgeDocument,
  type KnowledgeDocumentItem,
  type KnowledgeDocumentStats,
} from '@/api/knowledge-documents';
import { retryKnowledgeDocument } from '@/utils/knowledgeDocumentRetry';
import {
  fetchDirectoryTree,
  createDirectory,
  updateDirectory,
  moveDirectory,
  deleteDirectory,
  type KnowledgeDirectoryNode,
} from '@/api/knowledge-directories';

const router = useRouter();
const message = useMessage();
const dialog = useDialog();
const loading = ref(false);
const uploading = ref(false);
const documents = ref<KnowledgeDocumentItem[]>([]);
const stats = ref<KnowledgeDocumentStats>({ total: 0, indexed: 0, failed: 0, local: 0, oss: 0, totalSize: 0 });
const uploadVisible = ref(false);
const ProductKnowledgeDirectoryPermissions = adminProductUiExtension.knowledgeDirectoryPermissions;
const directoryPermissionVisible = ref(false);
const permissionDirectoryId = ref('root');
const permissionDirectoryName = ref('');
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

const statusOptions = computed(() => [
  { label: t('additional.learning_succeeded'), value: 'indexed' },
  { label: t('legacy.learning_failed'), value: 'failed' },
]);

const searchScopeOptions = computed(() => selectedDirectoryId.value
  ? [
      { label: t('legacy.current_directory_and_subdirectories'), value: 'current' },
      { label: t('legacy.all_folders'), value: 'all' },
    ]
  : [{ label: t('legacy.all_folders'), value: 'all' }]);

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
  { label: t('legacy.image'), value: 'image' },
]);

const uploadFinishedCount = computed(() =>
  uploadQueue.value.filter((item) => item.status === 'success' || item.status === 'failed').length,
);

const batchDeleteButtonText = computed(() =>
  selectedDocumentKeys.value.length ? `${t('additional.delete_in_bulk')} ${selectedDocumentKeys.value.length} ${t('additional.items')}` : t('additional.delete_in_bulk'),
);

const selectedBatchDeleteTitle = computed(() => `${t('additional.selected')} ${selectedDocumentKeys.value.length} ${t('additional.documents')}`);
const documentTableScrollX = 1078;
const tableScrollbarProps = { trigger: 'none' as const };

const metricCards = computed(() => [
  {
    key: 'total',
    icon: '<svg viewBox="0 0 24 24"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" /><path d="M14 2v6h6" /><path d="M16 13H8" /><path d="M16 17H8" /></svg>',
    label: t('legacy.documents_e6994dd'),
    value: stats.value.total,
    note: t('additional.knowledge_documents_under_the_current_primary_account'),
  },
  {
    key: 'indexed',
    icon: '<svg viewBox="0 0 24 24"><path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20" /><path d="M4 4.5A2.5 2.5 0 0 1 6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5z" /><path d="M9 10l2 2 4-4" /></svg>',
    label: t('legacy.learned'),
    value: stats.value.indexed,
    note: t('legacy.automatically_updated_after_parsing_and_learning_completes'),
  },
  {
    key: 'storage',
    icon: '<svg viewBox="0 0 24 24"><ellipse cx="12" cy="5" rx="9" ry="3" /><path d="M3 5v14c0 1.7 4 3 9 3s9-1.3 9-3V5" /><path d="M3 12c0 1.7 4 3 9 3s9-1.3 9-3" /></svg>',
    label: t('legacy.total_document_size'),
    value: formatFileSize(stats.value.totalSize),
    note: t('additional.total_file_size_of_all_knowledge_documents_under_the'),
  },
  {
    key: 'failed',
    icon: '<svg viewBox="0 0 24 24"><path d="M10.3 3.9L1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z" /><path d="M12 9v4" /><path d="M12 17h.01" /></svg>',
    label: t('legacy.failed_10fbe09'),
    value: stats.value.failed,
    note: t('legacy.number_of_documents_that_failed_during_parsing_or_learning'),
  },
]);

const columns = computed<DataTableColumns<KnowledgeDocumentItem>>(() => [
  {
    type: 'selection',
    width: 48,
    fixed: 'left',
  },
  {
    title: t('additional.document'),
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
              h('span', { class: 'doc-directory-label' }, `${t('additional.folder')}：`),
              h('span', { class: 'doc-directory-value' }, directoryPath),
            ])
          : null,
      ]);
    },
  },
  {
    title: t('legacy.type'),
    key: 'fileExt',
    width: 80,
    align: 'center',
    render(row) {
      return h(FileIcon, { ext: row.fileExt });
    },
  },
  {
    title: t('legacy.size_fd20702'),
    key: 'fileSize',
    width: 110,
    render(row) {
      return formatFileSize(row.fileSize);
    },
  },
  {
    title: t('legacy.status'),
    key: 'status',
    width: 140,
    render(row) {
      return h(DocumentStatus, { row, onRetry: () => retryParse(row) });
    },
  },
  {
    title: t('legacy.updated_at'),
    key: 'updatedAt',
    width: 150,
    render(row) {
      return formatAdminDateTime(row.updatedAt, '-');
    },
  },
  {
    title: t('legacy.actions'),
    key: 'actions',
    width: 250,
    render(row) {
      return h(NSpace, { size: 6 }, {
        default: () => [
          h(NButton, { size: 'small', tertiary: true, onClick: () => openDetail(row) }, {
            default: () => actionContent('preview', t('legacy.preview')),
          }),
          h(NButton, { size: 'small', tertiary: true, type: 'error', onClick: () => confirmDelete(row) }, {
            default: () => actionContent('delete', t('legacy.delete')),
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
    pending: t('additional.waiting_to_upload'),
    uploading: t('legacy.uploading'),
    success: t('legacy.success'),
    failed: t('legacy.failed'),
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
  const name = String(row.name || row.originalFilename || t('legacy.unnamed_document')).trim();
  const ext = String(row.fileExt || '').trim().replace(/^\./, '');
  if (!ext) {
    return name;
  }
  return name.toLowerCase().endsWith(`.${ext.toLowerCase()}`) ? name : `${name}.${ext}`;
}

function formatDirectoryPath(directoryId?: string) {
  const path = directoryPathMap.value.get(directoryId || '');
  return path ? `${t('legacy.root_folder')} / ${path}` : t('legacy.root_folder');
}

function readError(error: unknown, fallback: string) {
  if (axios.isAxiosError(error)) {
    return localizedServerText(error.response?.data?.detail || error.message, fallback);
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

function isDuplicateFilenameError(error: unknown) {
  return axios.isAxiosError(error)
    && error.response?.status === 409
    && error.response?.data?.detail?.code === 'DUPLICATE_FILENAME';
}

function confirmAction(content: string, options: { title?: string; positiveText?: string } = {}) {
  return new Promise<boolean>((resolve) => {
    dialog.warning({
      title: options.title || t('legacy.confirm_action'),
      content,
      positiveText: options.positiveText || t('legacy.confirm'),
      negativeText: t('legacy.cancel'),
      onPositiveClick: () => resolve(true),
      onNegativeClick: () => resolve(false),
      onClose: () => resolve(false),
    });
  });
}

function confirmDuplicateReplace(filename: string) {
  return confirmAction(
    t('additional.a_document_named_already_exists_upload_and_replace_the', { name: filename }),
    {
      title: t('additional.a_file_with_the_same_name_already_exists'),
      positiveText: t('additional.upload_and_replace'),
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
    message.warning(t('additional.select_documents_to_upload'));
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
              item.error = readError(replaceError, t('additional.replacement_failed'));
            }
          } else {
            item.error = t('additional.replacement_cancelled');
          }
        } else {
          item.error = readError(error, t('legacy.upload_failed'));
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
      t('additional.an_upload_is_in_progress_hiding_this_window_will'),
      { title: t('additional.hide_upload_progress') },
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
    message.success(t('additional.document_deleted_and_search_index_invalidated'));
    deleteConfirmVisible.value = false;
    deleteTarget.value = null;
    await reload();
    await loadDirectories();
  } catch (error) {
    message.error(readError(error, t('legacy.failed_to_delete')));
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
    message.success(`${t('legacy.deleted')} ${ids.length} ${t('additional.documents_deleted_and_search_indexes_invalidated')}`);
    selectedDocumentKeys.value = [];
    batchDeleteConfirmVisible.value = false;
    await reload();
    await loadDirectories();
  } catch (error) {
    message.error(readError(error, t('additional.bulk_deletion_failed')));
  } finally {
    batchDeleteSubmitting.value = false;
  }
}

async function retryParse(row: KnowledgeDocumentItem) {
  try {
    await retryKnowledgeDocument(row);
    message.success(t('additional.learning_task_resubmitted'));
    await reload({ silent: true });
    syncProcessingPoll();
  } catch (error) {
    message.error(readError(error, t('additional.failed_to_relearn')));
  }
}

// Knowledge directory state and behavior.
const directories = ref<KnowledgeDirectoryNode[]>([]);
const treeKeyword = ref('');
const selectedDirKeys = ref<string[]>(['root']);
const { persistListState, restoreListState } = useKnowledgeListState({ selectedDirKeys, pagination, filters });
const expandedDirKeys = ref<string[]>([]);
const uploadDirectoryId = ref<string>('root');
const { openUpload, triggerFilePicker, handleFileChange, appendUploadFiles, appendUploadCandidates, handleUploadDragEnter, handleUploadDragOver, handleUploadDragLeave, handleUploadDrop, removeUploadItem, clearUploadQueue } = useKnowledgeUploadQueue({ uploadQueue, showFloatPanel, fileInputRef, uploadDirectoryId, selectedDirKeys, uploadVisible, uploadDragging, uploading, message });
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
    return t('additional.select_a_folder');
  }
  if (selectedDirectoryDocumentCount.value > 0) {
    return t('additional.this_folder_or_its_subfolders_contain_knowledge_documents_and');
  }
  return t('legacy.delete');
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
      label: `${t('legacy.all_documents')} (${stats.value.total})`,
      rawName: t('legacy.all_documents'),
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

function renderTreeLabel(info: { option: TreeOption & { rawName?: string; totalDocumentCount?: number; isRoot?: boolean } }) {
  const nodeId = String(info.option.key);
  const name = info.option.rawName || String(info.option.label || '');
  const count = Number(info.option.totalDocumentCount ?? 0);
  const isRoot = info.option.isRoot || false;
  const menuOptions = [
    { label: t('legacy.new_subdirectory'), key: 'create' },
    ...(!isRoot ? [{ label: t('legacy.edit_directory'), key: 'edit' }] : []),
    ...(ProductKnowledgeDirectoryPermissions ? [{ label: t('additional.permission_settings'), key: 'permissions' }] : []),
  ];
  const handleMenu = (key: string) => {
    selectedDirKeys.value = [nodeId];
    if (key === 'create') openCreateDir(nodeId);
    if (key === 'edit') openEditDir(nodeId);
    if (key === 'permissions') openDirectoryPermissions(nodeId, name);
  };
  return h('div', { class: 'dept-node-label' }, [
    h('span', { class: 'dept-node-title' }, `${name} (${count})`),
    h('span', { class: 'dept-node-actions' }, [
      h(NDropdown, { options: menuOptions, trigger: 'click', onSelect: handleMenu }, {
        default: () => h('button', {
          class: 'dept-node-action',
          title: t('additional.folder_actions'),
          onClick: (event: MouseEvent) => {
            event.preventDefault();
            event.stopPropagation();
          },
        }, '•••'),
      }),
    ]),
  ]);
}

function openDirectoryPermissions(directoryId: string, directoryName: string) {
  permissionDirectoryId.value = directoryId;
  permissionDirectoryName.value = directoryName;
  directoryPermissionVisible.value = true;
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
const dirEditorTitle = computed(() => dirEditorMode.value === 'create' ? t('legacy.new_directory') : t('legacy.edit_directory'));

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

async function saveDirectory() {
  if (!dirForm.value.name.trim()) {
    message.warning(t('additional.enter_a_folder_name_8fc7792'));
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
      message.success(t('additional.folder_created'));
    } else {
      await updateDirectory(dirForm.value.id, {
        name: dirForm.value.name.trim(),
      });
      message.success(t('additional.folder_updated'));
    }
    dirEditorVisible.value = false;
    await loadDirectories();
    await reload();
  } catch (error) {
    message.error(readError(error, t('legacy.failed_to_save')));
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
    message.success(t('additional.folder_moved'));
    dirMoveVisible.value = false;
    await loadDirectories();
    await reload();
  } catch (error) {
    message.error(readError(error, t('additional.move_failed')));
  } finally {
    loading.value = false;
  }
}

async function deleteSelectedDir() {
  if (!selectedDirId.value || selectedDirId.value === 'root') return;
  const target = selectedDirectory.value;
  if (!target) return;
  if (selectedDirectoryDocumentCount.value > 0) {
    message.warning(t('additional.this_folder_or_its_subfolders_contain_knowledge_documents_and'));
    return;
  }
  const confirmed = await confirmAction(
    t('additional.delete_folder', { name: target.name }),
    { title: t('legacy.delete_directory') },
  );
  if (!confirmed) return;
  
  try {
    await deleteDirectory(selectedDirId.value);
    message.success(t('additional.folder_deleted'));
    selectedDirKeys.value = ['root'];
    await loadDirectories();
    await reload();
  } catch (error) {
    message.error(readError(error, t('legacy.failed_to_delete')));
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
      console.warn(readError(error, t('additional.failed_to_load_knowledge_documents')));
    } else {
      message.error(readError(error, t('additional.failed_to_load_knowledge_documents')));
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

<style scoped src="./KnowledgeDocumentsPageStyles1.css"></style>
<style scoped src="./KnowledgeDocumentsPageStyles2.css"></style>
