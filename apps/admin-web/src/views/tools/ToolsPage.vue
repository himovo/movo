<template>
  <div class="page-stack tools-page">
    <div class="metrics-row">
      <n-card v-for="item in metricCards" :key="item.label" class="metric-card" :bordered="false" size="small">
        <div class="metric-main">
          <span class="metric-icon" :class="`metric-icon-${item.key}`">
            <svg
              v-if="item.key === 'total'"
              class="metric-icon-svg"
              viewBox="0 0 512 512"
              fill="none"
              xmlns="http://www.w3.org/2000/svg"
            >
              <path
                d="M393.87 190a32.1 32.1 0 0 1-45.25 0l-26.57-26.57a32.09 32.09 0 0 1 0-45.26L382.19 58a1 1 0 0 0-.3-1.64c-38.82-16.64-89.15-8.16-121.11 23.57c-30.58 30.35-32.32 76-21.12 115.84a31.93 31.93 0 0 1-9.06 32.08L64 380a48.17 48.17 0 1 0 68 68l153.86-167a31.93 31.93 0 0 1 31.6-9.13c39.54 10.59 84.54 8.6 114.72-21.19c32.49-32 39.5-88.56 23.75-120.93a1 1 0 0 0-1.6-.26z"
                stroke="currentColor"
                stroke-width="32"
                stroke-linecap="round"
                stroke-miterlimit="10"
              />
              <circle cx="96" cy="416" r="16" fill="currentColor" />
            </svg>
            <svg
              v-else-if="item.key === 'enabled'"
              class="metric-icon-svg"
              viewBox="0 0 24 24"
              fill="none"
              xmlns="http://www.w3.org/2000/svg"
            >
              <path
                d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10s10-4.48 10-10S17.52 2 12 2zm0 18c-4.41 0-8-3.59-8-8s3.59-8 8-8s8 3.59 8 8s-3.59 8-8 8zm3.88-11.71L10 14.17l-1.88-1.88a.996.996 0 1 0-1.41 1.41l2.59 2.59c.39.39 1.02.39 1.41 0L17.3 9.7a.996.996 0 0 0 0-1.41c-.39-.39-1.03-.39-1.42 0z"
                fill="currentColor"
              />
            </svg>
            <svg
              v-else-if="item.key === 'mcp'"
              class="metric-icon-svg"
              viewBox="0 0 32 32"
              fill="none"
              xmlns="http://www.w3.org/2000/svg"
            >
              <path d="M29 26a2.97 2.97 0 0 0-1.855.66L25 25.423v-1.606a3 3 0 1 0-2 0v1.606l-2.145 1.239A2.97 2.97 0 0 0 19 26a3.02 3.02 0 1 0 2.925 2.353L24 27.154l2.075 1.198A2.998 2.998 0 1 0 29 26zm-10 4a1 1 0 1 1 1-1a1 1 0 0 1-1 1zm5-10a1 1 0 1 1-1 1a1 1 0 0 1 1-1zm5 10a1 1 0 1 1 1-1a1 1 0 0 1-1 1z" fill="currentColor" />
              <circle cx="7" cy="20" r="2" fill="currentColor" />
              <path d="M14 20a4 4 0 1 1 4-4a4.012 4.012 0 0 1-4 4zm0-6a2 2 0 1 0 2 2a2.006 2.006 0 0 0-2-2z" fill="currentColor" />
              <circle cx="21" cy="12" r="2" fill="currentColor" />
              <path d="M13.02 28.271L3 22.427V9.574l11-6.416l11.496 6.706l1.008-1.728l-12-7a1 1 0 0 0-1.008 0l-12 7A1 1 0 0 0 1 9v14a1 1 0 0 0 .496.864L12.013 30z" fill="currentColor" />
            </svg>
            <svg
              v-else-if="item.key === 'pass'"
              class="metric-icon-svg"
              viewBox="0 0 1024 1024"
              fill="none"
              xmlns="http://www.w3.org/2000/svg"
            >
              <path d="M866.9 169.9L527.1 54.1C523 52.7 517.5 52 512 52s-11 .7-15.1 2.1L157.1 169.9c-8.3 2.8-15.1 12.4-15.1 21.2v482.4c0 8.8 5.7 20.4 12.6 25.9L499.3 968c3.5 2.7 8 4.1 12.6 4.1s9.2-1.4 12.6-4.1l344.7-268.6c6.9-5.4 12.6-17 12.6-25.9V191.1c.2-8.8-6.6-18.3-14.9-21.2zM810 654.3L512 886.5L214 654.3V226.7l298-101.6l298 101.6v427.6z" fill-opacity=".8" fill="currentColor" />
              <path d="M214 226.7v427.6l298 232.2l298-232.2V226.7L512 125.1L214 226.7zM632.8 328H688c6.5 0 10.3 7.4 6.5 12.7L481.9 633.4a16.1 16.1 0 0 1-26 0l-126.4-174c-3.8-5.3 0-12.7 6.5-12.7h55.2c5.2 0 10 2.5 13 6.6l64.7 89.1l150.9-207.8c3-4.1 7.9-6.6 13-6.6z" fill-opacity=".1" fill="currentColor" />
              <path d="M404.2 453.3c-3-4.1-7.8-6.6-13-6.6H336c-6.5 0-10.3 7.4-6.5 12.7l126.4 174a16.1 16.1 0 0 0 26 0l212.6-292.7c3.8-5.3 0-12.7-6.5-12.7h-55.2c-5.1 0-10 2.5-13 6.6L468.9 542.4l-64.7-89.1z" fill-opacity=".8" fill="currentColor" />
            </svg>
            <template v-else>{{ item.icon }}</template>
          </span>
          <div class="metric-body">
            <div class="metric-label">{{ item.label }}</div>
            <div class="metric-value">{{ item.value }}</div>
          </div>
        </div>
        <div class="metric-note">{{ item.note }}</div>
      </n-card>
    </div>

    <n-card class="list-card shell-card" :bordered="false" size="large">
      <div class="list-filter-row">
        <div class="filter-toolbar">
          <n-space align="center" :size="10" class="filter-left">
            <n-input v-model:value="filters.keyword" clearable :placeholder="t('搜索名称、描述或 URL')" class="keyword-input" />
            <n-select v-model:value="filters.type" clearable :options="typeOptions" :placeholder="t('类型')" style="width: 140px" />
            <n-select v-model:value="filters.status" clearable :options="statusOptions" :placeholder="t('状态')" style="width: 140px" />
            <n-select
              v-model:value="filters.testStatus"
              clearable
              :options="testStatusOptions"
              :placeholder="t('测试结果')"
              style="width: 140px"
            />
          </n-space>
          <n-space :size="10" class="filter-right">
            <n-button secondary @click="loadRows">{{ t('刷新') }}</n-button>
            <n-button @click="goCreate('mcp')">{{ t('新增 MCP 服务') }}</n-button>
            <n-button type="primary" strong @click="goCreate('http')">{{ t('新增 HTTP 工具') }}</n-button>
          </n-space>
        </div>
      </div>

      <div class="list-body">
        <n-spin :show="loading">
          <div v-if="filteredRows.length" class="tool-grid">
            <div v-for="row in filteredRows" :key="row.id" class="tool-card" role="button" tabindex="0" @click="goEdit(row.id)" @keydown.enter="goEdit(row.id)">
              <div class="card-head">
                <n-tag :type="row.type === 'mcp' ? 'info' : 'success'" size="small" :bordered="false">
                  {{ row.type === 'mcp' ? t('MCP 服务') : t('HTTP 工具') }}
                </n-tag>
                <n-space align="center" :size="8">
                  <n-tag
                    :type="row.lastTestStatus === 'passed' ? 'success' : row.lastTestStatus === 'failed' ? 'error' : 'default'"
                    size="small"
                    :bordered="false"
                  >
                    {{ row.lastTestStatus === 'passed' ? t('测试通过') : row.lastTestStatus === 'failed' ? t('测试失败') : t('未测试') }}
                  </n-tag>
                  <span class="status-switch-label">{{ row.status === 'active' ? t('启用') : t('禁用') }}</span>
                  <n-switch
                    :value="row.status === 'active'"
                    size="small"
                    @click.stop
                    @update:value="(value: boolean) => toggleStatus(row, value)"
                  />
                </n-space>
              </div>

              <div class="card-title">{{ row.name || t('未命名工具') }}</div>
              <div class="card-desc">{{ row.description || t('未填写工具说明') }}</div>

              <div class="tag-row">
                <n-tag v-for="tag in row.tags" :key="tag" size="small" :bordered="false" class="tool-tag">{{ tag }}</n-tag>
                <span v-if="!row.tags.length" class="no-tag">{{ t('无标签') }}</span>
              </div>

              <div class="card-footrow">
                <div class="card-footnote">{{ t('最近测试：') }}{{ formatAdminDateTime(row.lastTestAt, row.lastTestMessage || t('暂无记录')) }}</div>
                <n-button size="small" tertiary type="error" @click.stop="askRemove(row)">{{ t('删除') }}</n-button>
              </div>
            </div>
          </div>

          <div v-else class="empty-shell">
            <div class="empty-visual">
              <span>API</span>
              <span>MCP</span>
              <span>HTTP</span>
            </div>
            <div class="empty-title">{{ t('暂未配置工具') }}</div>
            <div class="empty-desc">{{ t('连接第一个 HTTP 工具或 MCP 服务，扩展平台能力。') }}</div>
            <n-space justify="center">
              <n-button type="primary" @click="goCreate('http')">{{ t('新增 HTTP 工具') }}</n-button>
              <n-button @click="goCreate('mcp')">{{ t('新增 MCP 服务') }}</n-button>
            </n-space>
          </div>
        </n-spin>
      </div>
    </n-card>

    <n-modal
      v-model:show="deleteConfirmVisible"
      preset="dialog"
      type="warning"
      :title="t('删除工具连接')"
      :positive-text="t('删除')"
      :negative-text="t('取消')"
      :positive-button-props="{ type: 'error', loading: deleting }"
      @positive-click="confirmRemove"
    >
      {{ t('确定删除「{name}」吗？删除后不可恢复。', { name: pendingDeleteRow?.name || t('未命名工具') }) }}
    </n-modal>

    <n-modal
      v-model:show="statusConfirmVisible"
      preset="dialog"
      type="warning"
      :title="pendingStatusValue ? t('启用') : t('禁用')"
      :positive-text="pendingStatusValue ? t('确认启用') : t('确认禁用')"
      :negative-text="t('取消')"
      :positive-button-props="{ type: pendingStatusValue ? 'primary' : 'warning', loading: statusUpdating }"
      @positive-click="confirmToggleStatus"
    >
      {{ pendingStatusText }}
    </n-modal>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';
import { useRouter } from 'vue-router';
import { useMessage } from 'naive-ui';
import { t } from '@/composables/i18n';
import { formatAdminDateTime } from '@/composables/adminTimezone';
import { deleteTool, fetchTools, patchTool, type ExternalToolItem, type TestStatus, type ToolStatus, type ToolType } from '@/api/tools';
import { mcpActivationError, toolStatusConfirmText } from '@/utils/toolActivation';

const router = useRouter();
const message = useMessage();
const rows = ref<ExternalToolItem[]>([]);
const loading = ref(false);
const deleting = ref(false);
const statusUpdating = ref(false);
const deleteConfirmVisible = ref(false);
const pendingDeleteRow = ref<ExternalToolItem | null>(null);
const statusConfirmVisible = ref(false);
const pendingStatusRow = ref<ExternalToolItem | null>(null);
const pendingStatusValue = ref(false);
const pendingStatusText = ref('');

const filters = ref({
  keyword: '',
  type: null as ToolType | null,
  status: null as ToolStatus | null,
  testStatus: null as TestStatus | null,
});

const typeOptions = computed(() => [
  { label: t('HTTP 工具'), value: 'http' },
  { label: t('MCP 服务'), value: 'mcp' },
]);

const statusOptions = computed(() => [
  { label: t('启用'), value: 'active' },
  { label: t('禁用'), value: 'disabled' },
]);

const testStatusOptions = computed(() => [
  { label: t('通过'), value: 'passed' },
  { label: t('失败'), value: 'failed' },
  { label: t('未测试'), value: 'untested' },
]);

const filteredRows = computed(() => {
  const keyword = filters.value.keyword.trim().toLowerCase();
  return rows.value.filter((row) => {
    const keywordHit = !keyword
      || row.name.toLowerCase().includes(keyword)
      || row.description.toLowerCase().includes(keyword)
      || row.usageHint.toLowerCase().includes(keyword);
    const typeHit = !filters.value.type || row.type === filters.value.type;
    const statusHit = !filters.value.status || row.status === filters.value.status;
    const testHit = !filters.value.testStatus || row.lastTestStatus === filters.value.testStatus;
    return keywordHit && typeHit && statusHit && testHit;
  });
});

const metricCards = computed(() => {
  const total = rows.value.length;
  const enabled = rows.value.filter((row) => row.status === 'active').length;
  const mcpCount = rows.value.filter((row) => row.type === 'mcp').length;
  const passedCount = rows.value.filter((row) => row.lastTestStatus === 'passed').length;
  return [
    { key: 'total', icon: '工', label: t('工具总数'), value: total, note: t('包含 HTTP 工具与 MCP 服务') },
    { key: 'enabled', icon: '启', label: t('已启用'), value: enabled, note: total ? t('启用率 {count}%', { count: Math.round((enabled / total) * 100) }) : t('当前暂无工具') },
    { key: 'mcp', icon: '服', label: t('MCP 服务'), value: mcpCount, note: total ? t('占比 {count}%', { count: Math.round((mcpCount / total) * 100) }) : t('当前暂无 MCP 服务') },
    { key: 'pass', icon: '测', label: t('测试通过'), value: passedCount, note: t('最近测试通过数量') },
  ];
});

function goCreate(type: ToolType) {
  router.push({ path: '/tools/new', query: { type } });
}

function goEdit(id: string) {
  router.push(`/tools/${id}/edit`);
}

async function loadRows() {
  loading.value = true;
  try {
    rows.value = await fetchTools();
  } catch (error: any) {
    message.error(error?.response?.data?.detail || t('加载工具连接失败'));
  } finally {
    loading.value = false;
  }
}

async function toggleStatus(row: ExternalToolItem, enabled: boolean) {
  const error = mcpActivationError({ ...row, status: enabled ? 'active' : 'disabled' });
  if (error) {
    message.warning(error);
    return;
  }
  pendingStatusRow.value = row;
  pendingStatusValue.value = enabled;
  pendingStatusText.value = toolStatusConfirmText(row, enabled);
  statusConfirmVisible.value = true;
}

async function confirmToggleStatus() {
  if (!pendingStatusRow.value) return false;
  statusUpdating.value = true;
  try {
    await patchTool(pendingStatusRow.value.id, { status: pendingStatusValue.value ? 'active' : 'disabled' });
    message.success(pendingStatusValue.value ? t('工具已启用') : t('工具已禁用'));
    statusConfirmVisible.value = false;
    pendingStatusRow.value = null;
    await loadRows();
  } catch (error: any) {
    message.error(error?.response?.data?.detail || t('状态更新失败'));
    return false;
  } finally {
    statusUpdating.value = false;
  }
  return true;
}

function askRemove(row: ExternalToolItem) {
  pendingDeleteRow.value = row;
  deleteConfirmVisible.value = true;
}

async function confirmRemove() {
  if (!pendingDeleteRow.value) return false;
  deleting.value = true;
  try {
    await deleteTool(pendingDeleteRow.value.id);
    message.success(t('工具连接已删除'));
    deleteConfirmVisible.value = false;
    pendingDeleteRow.value = null;
    await loadRows();
  } catch (error: any) {
    message.error(error?.response?.data?.detail || t('删除失败'));
    return false;
  } finally {
    deleting.value = false;
  }
  return true;
}

onMounted(loadRows);
</script>

<style scoped>
.tools-page {
  height: calc(100vh - 92px);
  min-height: 0;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.shell-card {
  border-radius: 14px;
  border: 1px solid #e6ebf5;
  background: #fff;
  box-shadow: 0 6px 20px rgba(16, 38, 84, 0.05);
}

.hero-block {
  padding: 20px 22px;
}

.hero-breadcrumb {
  color: #8692aa;
  font-size: 13px;
}

.hero-title {
  margin-top: 8px;
  color: #111b3a;
  font-size: 36px;
  line-height: 1.15;
  font-weight: 800;
}

.hero-subtitle {
  margin-top: 8px;
  color: #5f6f85;
  font-size: 15px;
}

.metrics-row {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
  padding: 12px;
}

.metric-card,
.list-card {
  border-radius: 8px;
}

.list-card {
  width: calc(100% - 24px);
  margin: -16px 12px 0;
  flex: 1;
  min-height: 0;
  overflow: hidden;
}

.list-card :deep(.n-card__content) {
  height: 100%;
  display: flex;
  flex-direction: column;
}

.metric-card {
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
  font-size: 13px;
  font-weight: 700;
}

.metric-icon-svg {
  width: 20px;
  height: 20px;
}

.metric-icon-total {
  color: #2d63ff;
  background: #eaf0ff;
}

.metric-icon-enabled {
  color: #0f9964;
  background: #e8f8ef;
}

.metric-icon-mcp {
  color: #7456e0;
  background: #f0ebff;
}

.metric-icon-pass {
  color: #d9860a;
  background: #fff2df;
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

.metric-note {
  margin-top: 6px;
  color: #708099;
  font-size: 12px;
}

.filter-toolbar {
  align-items: center;
  display: flex;
  justify-content: space-between;
  gap: 14px;
}

.filter-left {
  flex-wrap: wrap;
}

.keyword-input {
  width: 360px;
}

.filter-right {
  flex-wrap: wrap;
}

.list-head {
  margin-bottom: 12px;
}

.list-filter-row {
  padding: 0 44px 12px;
  margin: 0 -44px 12px;
  border-bottom: 1px solid #edf1f7;
}

.list-body {
  flex: 1;
  min-height: 0;
  overflow: auto;
}

.tool-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
  gap: 12px;
}

.tool-card {
  min-height: 188px;
  padding: 14px;
  border: 1px solid rgba(28, 45, 82, 0.08);
  border-radius: 8px;
  background: #fff;
  box-shadow:
    0 8px 18px rgba(15, 31, 69, 0.06),
    0 1px 2px rgba(15, 31, 69, 0.04);
  display: flex;
  flex-direction: column;
  gap: 10px;
  cursor: pointer;
  outline: none;
  transition:
    border-color 0.2s ease,
    box-shadow 0.2s ease,
    transform 0.2s ease;
}

.tool-card:hover,
.tool-card:focus-visible {
  border-color: rgba(54, 106, 255, 0.36);
  box-shadow:
    0 14px 34px rgba(33, 58, 126, 0.14),
    0 4px 10px rgba(33, 58, 126, 0.08);
  transform: translateY(-2px);
}

.card-head,
.card-footrow {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}

.card-title {
  color: #17233d;
  font-size: 16px;
  font-weight: 800;
}

.card-desc {
  color: #5f6f85;
  font-size: 13px;
  line-height: 1.55;
  display: -webkit-box;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 3;
  overflow: hidden;
}

.card-footnote,
.no-tag {
  color: #7a8797;
  font-size: 12px;
}

.status-switch-label {
  color: #5f6f85;
  font-size: 12px;
  white-space: nowrap;
}

.tag-row {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  min-height: 24px;
}

.tool-tag {
  background: #f1f5f9;
}

.card-footrow {
  margin-top: auto;
  min-height: 28px;
}

.card-footnote {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.card-footrow :deep(.n-button[type="error"]),
.card-footrow :deep(.n-button--error-type) {
  opacity: 0;
  pointer-events: none;
  transform: translateX(4px);
  transition:
    opacity 0.16s ease,
    transform 0.16s ease;
}

.tool-card:hover .card-footrow :deep(.n-button[type="error"]),
.tool-card:hover .card-footrow :deep(.n-button--error-type) {
  opacity: 1;
  pointer-events: auto;
  transform: translateX(0);
}

.empty-shell {
  min-height: 320px;
  border: 1px dashed #d8e2f2;
  border-radius: 12px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  text-align: center;
  background: linear-gradient(180deg, #fbfdff, #fff);
}

.empty-visual {
  display: flex;
  gap: 8px;
}

.empty-visual span {
  width: 54px;
  height: 36px;
  border-radius: 10px;
  border: 1px solid #d8e2f2;
  background: #fff;
  color: #2d63ff;
  display: grid;
  place-items: center;
  font-weight: 700;
  font-size: 12px;
}

.empty-title {
  color: #101c3d;
  font-size: 24px;
  line-height: 1.2;
  font-weight: 800;
}

.empty-desc {
  color: #65748c;
  font-size: 14px;
}

@media (max-width: 1200px) {
  .metrics-row,
  .tool-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .hero-title {
    font-size: 30px;
  }
}

@media (max-width: 768px) {
  .metrics-row,
  .tool-grid {
    grid-template-columns: minmax(0, 1fr);
  }

  .filter-toolbar {
    flex-direction: column;
    align-items: stretch;
  }

  .keyword-input {
    width: 100%;
  }

  .hero-title {
    font-size: 26px;
  }
}
</style>
