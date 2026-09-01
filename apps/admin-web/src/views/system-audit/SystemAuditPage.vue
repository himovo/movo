<script setup lang="ts">
import { t } from '@/composables/i18n';
import { computed, h, onMounted, ref, watch } from 'vue';
import { NButton, NTag, type DataTableColumns } from 'naive-ui';
import PageIntro from '@/components/PageIntro.vue';
import AuditDetailDrawer from './AuditDetailDrawer.vue';
import { fetchSystemAuditLogs, fetchSystemAuditOverview, type AuditCategory, type SystemAuditLog, type SystemAuditOverview } from '@/api/systemAudit';
import { formatAdminDateTime } from '@/composables/adminTimezone';

const loading = ref(false);
const rows = ref<SystemAuditLog[]>([]);
const total = ref(0);
const page = ref(1);
const pageSize = 20;
const category = ref<AuditCategory>('management');
const keyword = ref('');
const result = ref<'' | 'success' | 'failed'>('');
const module = ref('');
const selected = ref<SystemAuditLog | null>(null);
const detailVisible = ref(false);
const overview = ref<SystemAuditOverview>({ managementOperations: 0, failedOperations: 0, agentActivities: 0, permissionDenials: 0 });

const categoryOptions = [
  { label: t('管理操作'), value: 'management' },
  { label: t('Agent 活动'), value: 'agent' },
  { label: t('历史记录'), value: 'legacy' },
];
const resultOptions = [{ label: t('成功'), value: 'success' }, { label: t('失败 / 拒绝'), value: 'failed' }];
const moduleOptions = [
  { label: t('模型中心'), value: 'models' },
  { label: t('Skill 管理'), value: 'skills' },
  { label: t('工具与 MCP'), value: 'tools' },
  { label: t('知识文档'), value: 'knowledge' },
  { label: t('组织与用户'), value: 'directory' },
  { label: t('用户岗位角色'), value: 'position-roles' },
  { label: t('流量分配'), value: 'traffic-allocations' },
  { label: t('系统设置'), value: 'settings' },
  { label: t('账号组与账号'), value: 'organizations' },
];
const actionLabels: Record<string, string> = {
  create_or_execute: t('新增 / 执行'), update: t('修改'), delete: t('删除'),
  'capability.used': t('使用能力'), 'capability.denied': t('权限拒绝'),
  create: t('创建'), copy: t('复制'), enable: t('启用'), disable: t('停用'), assign: t('分配岗位'), bulk_assign: t('批量分配岗位'),
  grant_override: t('创建临时授权'), revoke_override: t('撤销临时授权'),
};
const categoryLabel = (value: AuditCategory) => ({ management: t('管理操作'), agent: t('Agent 活动'), legacy: t('历史记录') }[value]);

const metrics = computed(() => [
  { label: t('管理操作'), value: overview.value.managementOperations, hint: t('近 24 小时') },
  { label: t('失败操作'), value: overview.value.failedOperations, hint: t('近 24 小时'), danger: overview.value.failedOperations > 0 },
  { label: t('Agent 活动'), value: overview.value.agentActivities, hint: t('近 24 小时') },
  { label: t('权限拒绝'), value: overview.value.permissionDenials, hint: t('近 24 小时'), danger: overview.value.permissionDenials > 0 },
]);

function openDetail(row: SystemAuditLog) { selected.value = row; detailVisible.value = true; }

const columns: DataTableColumns<SystemAuditLog> = [
  { title: t('时间'), key: 'occurredAt', width: 170, render: row => formatAdminDateTime(row.occurredAt, '-') },
  { title: t('类型'), key: 'category', width: 110, render: row => h(NTag, { bordered: false, type: row.category === 'agent' ? 'info' : 'default' }, { default: () => categoryLabel(row.category) }) },
  { title: t('模块'), key: 'module', width: 150, ellipsis: { tooltip: true } },
  { title: t('操作'), key: 'action', width: 150, render: row => actionLabels[row.action] || row.action },
  { title: t('操作者 / 员工'), key: 'actor', width: 160, ellipsis: { tooltip: true } },
  { title: t('对象'), key: 'target', ellipsis: { tooltip: true } },
  { title: t('结果'), key: 'result', width: 90, render: row => h(NTag, { bordered: false, type: row.result === 'success' ? 'success' : 'error' }, { default: () => row.result === 'success' ? t('成功') : t('失败') }) },
  { title: t('操作'), key: 'detail', width: 80, render: row => h(NButton, { text: true, type: 'primary', onClick: () => openDetail(row) }, { default: () => t('详情') }) },
];

async function load() {
  loading.value = true;
  try {
    const [summary, data] = await Promise.all([
      fetchSystemAuditOverview(),
      fetchSystemAuditLogs({ category: category.value, page: page.value, pageSize, keyword: keyword.value.trim(), result: result.value, module: category.value === 'management' ? module.value : '' }),
    ]);
    overview.value = summary;
    rows.value = data.items;
    total.value = data.total;
  } finally { loading.value = false; }
}

function applyFilters() { page.value = 1; void load(); }
watch(page, load);
watch(category, () => { module.value = ''; applyFilters(); });
onMounted(load);
</script>

<template>
  <div class="page-stack audit-page">
    <n-card class="audit-card" :bordered="false" size="large">
      <div class="audit-content">
        <div class="page-head"><PageIntro :title="t('系统审计')" :description="t('集中查看管理后台操作、Agent 能力使用和权限拒绝记录。')" :tags="[t('企业留痕'), t('统一审计')]" /><n-button type="primary" secondary :loading="loading" @click="load">刷新</n-button></div>
        <div class="metric-grid">
          <div v-for="item in metrics" :key="item.label" class="metric-card"><span>{{ item.label }}</span><strong :class="{ danger: item.danger }">{{ item.value }}</strong><small>{{ item.hint }}</small></div>
        </div>
        <div class="audit-table-card">
          <div class="toolbar">
            <n-space :size="10" wrap>
              <n-select v-model:value="category" :options="categoryOptions" style="width: 140px" />
              <n-input v-model:value="keyword" clearable :placeholder="t('搜索操作者、对象或操作')" style="width: 260px" @keyup.enter="applyFilters" />
              <n-select v-model:value="result" clearable :options="resultOptions" :placeholder="t('全部结果')" style="width: 140px" @update:value="applyFilters" />
              <n-select v-if="category === 'management'" v-model:value="module" clearable :options="moduleOptions" :placeholder="t('全部模块')" style="width: 170px" @update:value="applyFilters" />
              <n-button @click="applyFilters">{{ t('查询') }}</n-button>
            </n-space>
          </div>
          <n-data-table :columns="columns" :data="rows" :loading="loading" :bordered="false" :pagination="false" :scroll-x="1120" />
          <div class="pager-row"><span>{{ t('共 {count} 条', { count: total }) }}</span><n-pagination v-model:page="page" :page-size="pageSize" :item-count="total" /></div>
        </div>
      </div>
    </n-card>
    <AuditDetailDrawer v-model:show="detailVisible" :record="selected" />
  </div>
</template>

<style scoped>
.audit-page { min-height: calc(100vh - 98px); }
.audit-card { min-width: 0; border-radius: 8px; }
.audit-content { display: grid; gap: 18px; min-width: 0; }
.page-head { display: flex; align-items: center; justify-content: space-between; gap: 20px; }
.metric-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 14px; }
.metric-card { display: grid; gap: 4px; padding: 16px 18px; border: 1px solid #edf0f5; border-radius: 10px; background: #fafbfc; }
.metric-card span, .metric-card small, .pager-row { color: #667085; }
.metric-card strong { color: #172033; font-size: 28px; line-height: 1.2; }
.metric-card strong.danger { color: #d03050; }
.audit-table-card { overflow: hidden; border: 1px solid #edf0f5; border-radius: 10px; }
.toolbar, .pager-row { padding: 14px 16px; }
.toolbar { border-bottom: 1px solid #edf0f5; }
.pager-row { display: flex; align-items: center; justify-content: space-between; border-top: 1px solid #edf0f5; }
@media (max-width: 980px) { .metric-grid { grid-template-columns: repeat(2, 1fr); } .page-head { align-items: flex-start; flex-direction: column; } }
</style>
