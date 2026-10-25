<template>
  <div class="document-picker">
    <button type="button" class="picker-trigger" @click.stop="openPicker">
      <span class="trigger-icon" aria-hidden="true">▤</span>
      <span class="trigger-copy"><strong>{{ selectedName || t('legacy.find_a_document_by_folder_or_name') }}</strong>
        <small>{{ selectedName ? t('legacy.click_to_change_the_knowledge_document') : t('legacy.choose_from_organization_knowledge_documents') }}</small></span>
      <span class="trigger-arrow" aria-hidden="true">›</span>
    </button>
    <n-modal v-model:show="visible" preset="card" class="picker-modal" :title="t('legacy.select_knowledge_document')" :style="{ width: 'min(760px, calc(100vw - 32px))' }">
      <div class="picker-filters">
        <n-select :value="directoryId" :options="directoryOptions"
          filterable size="medium" :aria-label="t('legacy.filter_folders')" :placeholder="t('legacy.select_folder')"
          @update:value="setDirectory" />
        <n-input v-model:value="keyword" clearable size="medium" :aria-label="t('legacy.search_documents')"
          :placeholder="t('legacy.search_document_name_or_filename')" @keyup.enter="search" />
        <n-button type="primary" secondary @click="search">{{ t('legacy.search') }}</n-button>
      </div>
      <div class="result-heading"><strong>{{ t('legacy.documents') }}</strong><span>{{ t('legacy.total') }} {{ total }} {{ t('legacy.parsed_documents_only') }}</span></div>
      <div class="result-list" :class="{ loading }">
        <div v-if="loading" class="empty-state">{{ t('legacy.searching_documents') }}</div>
        <div v-else-if="error" class="empty-state error-state">{{ error }} <button type="button" @click="load">{{ t('legacy.retry') }}</button></div>
        <div v-else-if="!items.length" class="empty-state">{{ t('legacy.no_documents_found_try_another_folder_or_keyword') }}</div>
        <button v-for="item in items" v-else :key="item.id" type="button" class="document-row"
          :class="{ selected: pendingId === item.id, unavailable: !isAvailable(item) }"
          :disabled="!isAvailable(item)" @click="choose(item)">
          <span class="document-icon" aria-hidden="true">▤</span>
          <span class="document-copy"><strong>{{ item.name }}</strong>
            <small>{{ directoryLabel(item.directoryId) }}
              <span v-if="item.updatedAt"> · {{ item.updatedAt.slice(0, 10) }}</span></small></span>
          <span class="document-status" :class="{ ready: isAvailable(item) }">{{ isAvailable(item) ? t('legacy.optional') : t('legacy.not_parsed') }}</span>
          <span class="document-check" aria-hidden="true">{{ pendingId === item.id ? '✓' : '' }}</span>
        </button>
      </div>
      <div class="picker-footer">
        <div class="footer-selection">{{ t('legacy.selected') }}<strong>{{ pendingName || t('legacy.none_selected') }}</strong></div>
        <n-pagination :page="page" :page-size="pageSize" :item-count="total" simple
          @update:page="setPage" />
        <n-button @click="visible = false">{{ t('legacy.cancel') }}</n-button>
        <n-button type="primary" :disabled="!pendingId" @click="confirm">{{ t('legacy.use_this_document') }}</n-button>
      </div>
    </n-modal>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import { fetchDirectoryTree, type KnowledgeDirectoryNode } from '../../api/knowledge-directories';
import { fetchKnowledgeDocument, fetchKnowledgeDocuments, type KnowledgeDocumentItem } from '../../api/knowledge-documents';
import { t } from '../../composables/i18n';

const props = defineProps<{ value: string }>();
const emit = defineEmits<{ 'update:value': [value: string] }>();
const visible = ref(false);
const directoryId = ref('all');
const directories = ref<KnowledgeDirectoryNode[]>([]);
const keyword = ref('');
const page = ref(1);
const pageSize = 20;
const total = ref(0);
const items = ref<KnowledgeDocumentItem[]>([]);
const selectedName = ref('');
const pendingId = ref('');
const pendingName = ref('');
const loading = ref(false);
const error = ref('');
let requestId = 0;

const directoryOptions = computed(() => {
  const options = [{ label: t('legacy.all_folders'), value: 'all' }];
  const visit = (nodes: KnowledgeDirectoryNode[], parents: string[] = []) => {
    for (const node of nodes) {
      const path = [...parents, node.name];
      options.push({ label: path.join(' / '), value: node.id });
      visit(node.children || [], path);
    }
  };
  visit(directories.value);
  return options;
});
function directoryLabel(id?: string) {
  return directoryOptions.value.find(item => item.value === id)?.label || t('legacy.root_folder');
}
function isAvailable(item: KnowledgeDocumentItem) {
  return item.parseStatus === 'succeeded' && !item.deletedAt;
}
async function resolveSelected() {
  if (!props.value) { selectedName.value = ''; return; }
  const item = await fetchKnowledgeDocument(props.value).catch(() => null);
  selectedName.value = item?.name || t('legacy.selected_document');
}
async function openPicker() {
  pendingId.value = props.value || '';
  pendingName.value = selectedName.value;
  visible.value = true;
  await Promise.all([
    fetchDirectoryTree().then(data => { directories.value = data; }).catch(() => { directories.value = []; }),
    load(),
  ]);
}
async function load() {
  const current = ++requestId;
  loading.value = true;
  error.value = '';
  try {
    const result = await fetchKnowledgeDocuments({
      page: page.value, pageSize, keyword: keyword.value.trim(),
      directoryScopeId: directoryId.value === 'all' ? undefined : directoryId.value,
      sortField: 'updatedAt', sortOrder: 'descend',
    });
    if (current !== requestId) return;
    items.value = result.items;
    total.value = result.total;
  } catch {
    if (current !== requestId) return;
    error.value = t('legacy.failed_to_load_documents');
    items.value = [];
  } finally {
    if (current === requestId) loading.value = false;
  }
}
function setDirectory(value: string) { directoryId.value = value; page.value = 1; void load(); }
function search() { page.value = 1; void load(); }
function setPage(value: number) { page.value = value; void load(); }
function choose(item: KnowledgeDocumentItem) { pendingId.value = item.id; pendingName.value = item.name; }
function confirm() { if (!pendingId.value) return; selectedName.value = pendingName.value; emit('update:value', pendingId.value); visible.value = false; }
watch(() => props.value, () => { void resolveSelected(); }, { immediate: true });
</script>

<style scoped>
.picker-trigger { display:flex; align-items:center; gap:11px; width:100%; min-height:58px; padding:10px 13px; border:1px solid #cfdcf6; border-radius:10px; background:#f8faff; text-align:left; cursor:pointer; }
.picker-trigger:hover { border-color:#7395ec; background:#f2f6ff; }
.picker-trigger:focus-visible { outline:2px solid #4775e7; outline-offset:2px; }
.trigger-icon, .document-icon { display:grid; place-items:center; flex:0 0 32px; height:32px; border-radius:9px; background:#e9f0ff; color:#4473da; font-size:18px; }
.trigger-copy, .document-copy { display:grid; gap:3px; min-width:0; }
.trigger-copy strong { color:#28446d; font-size:13px; }
.trigger-copy small, .document-copy small { color:#718199; font-size:11px; }
.trigger-arrow { margin-left:auto; color:#7385a3; font-size:24px; }
.picker-filters { display:grid; grid-template-columns:minmax(150px, 220px) minmax(180px, 1fr) auto; gap:9px; margin-bottom:18px; }
.picker-filters > .n-input:first-child { grid-column:1 / 3; }
.result-heading { display:flex; justify-content:space-between; gap:10px; margin-bottom:8px; color:#304159; font-size:12px; }
.result-heading span { color:#8290a4; }
.result-list { min-height:150px; max-height:340px; overflow:auto; border:1px solid #e3eaf4; border-radius:10px; }
.empty-state { padding:55px 16px; color:#7c8aa0; text-align:center; font-size:13px; }
.error-state { color:#b45309; }
.error-state button { margin-left:6px; border:0; background:none; color:#3768dc; cursor:pointer; }
.document-row { display:flex; align-items:center; gap:10px; width:100%; min-height:61px; padding:9px 13px; border:0; border-bottom:1px solid #edf1f7; background:#fff; text-align:left; cursor:pointer; }
.document-row:last-child { border-bottom:0; }
.document-row:hover, .document-row.selected { background:#f4f7ff; }
.document-row.unavailable { opacity:.55; cursor:not-allowed; }
.document-copy { flex:1; overflow:hidden; }
.document-copy strong { overflow:hidden; color:#2d3c55; text-overflow:ellipsis; white-space:nowrap; font-size:13px; }
.document-status { color:#9b6b26; font-size:11px; white-space:nowrap; }
.document-status.ready { color:#258260; }
.document-check { width:18px; color:#4775e7; font-weight:800; }
.picker-footer { display:flex; align-items:center; gap:9px; flex-wrap:wrap; padding-top:15px; }
.footer-selection { flex:1; min-width:130px; overflow:hidden; color:#738198; font-size:12px; white-space:nowrap; text-overflow:ellipsis; }
.footer-selection strong { color:#2e4263; }
@media (max-width:650px) { .picker-filters { grid-template-columns:1fr auto; } .picker-filters > .n-select { grid-column:1 / -1; } .picker-filters > .n-input:first-child { grid-column:1; } .picker-footer .n-pagination { order:3; width:100%; } }
</style>
