<script setup lang="ts">
import { t } from '@/composables/i18n';
import { computed, h, onMounted, ref, watch } from 'vue';
import { NButton, NTag, type DataTableColumns } from 'naive-ui';
import PageIntro from '@/components/PageIntro.vue';
import { useAuditViewport } from './useAuditViewport';
import { useAuditExport } from './useAuditExport';
import AuditDetailDrawer from './AuditDetailDrawer.vue';
import { fetchSystemAuditLogs, fetchSystemAuditOverview, type AuditFilters, type AuditCategory, type SystemAuditLog, type SystemAuditOverview } from '@/api/systemAudit';
import { formatAdminDateTime } from '@/composables/adminTimezone';

const pageRoot = ref<HTMLElement | null>(null);
const viewportHeight = useAuditViewport(pageRoot);
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
  { label: t('legacy.management_actions'), value: 'management' },
  { label: t('legacy.agent_activity'), value: 'agent' },
  { label: t('legacy.legacy_records'), value: 'legacy' },
];
const resultOptions = [{ label: t('legacy.success_51991a5'), value: 'success' }, { label: t('legacy.failed_denied'), value: 'failed' }];
const moduleOptions = [
  { label: t('legacy.models'), value: 'models' },
  { label: t('legacy.skill_management'), value: 'skills' },
  { label: t('legacy.tools_mcp'), value: 'tools' },
  { label: t('legacy.knowledge_documents'), value: 'knowledge' },
  { label: t('legacy.organizations_users'), value: 'directory' },
  { label: t('legacy.position_roles'), value: 'position-roles' },
  { label: t('legacy.traffic_allocation'), value: 'traffic-allocations' },
  { label: t('legacy.system_settings'), value: 'settings' },
  { label: t('legacy.accounts_org_groups'), value: 'organizations' },
];
const actionLabels: Record<string, string> = {
  create_or_execute: t('legacy.create_execute'), update: t('legacy.update'), delete: t('legacy.delete'),
  'capability.used': t('legacy.use_capability'), 'capability.denied': t('legacy.permission_denials'),
  create: t('legacy.create'), copy: t('legacy.copy'), enable: t('legacy.active'), disable: t('legacy.disabled'), assign: t('legacy.assign_position_role'), bulk_assign: t('legacy.bulk_assign_position_roles'),
  grant_override: t('legacy.create_temporary_authorization'), revoke_override: t('legacy.revoke_temporary_authorization'),
};
const categoryLabel = (value: AuditCategory) => ({ management: t('legacy.management_actions'), agent: t('legacy.agent_activity'), legacy: t('legacy.legacy_records') }[value]);

const metrics = computed(() => [
  { label: t('legacy.management_actions'), value: overview.value.managementOperations, hint: t('legacy.last_24_hours') },
  { label: t('legacy.failed_actions'), value: overview.value.failedOperations, hint: t('legacy.last_24_hours'), danger: overview.value.failedOperations > 0 },
  { label: t('legacy.agent_activity'), value: overview.value.agentActivities, hint: t('legacy.last_24_hours') },
  { label: t('legacy.permission_denials'), value: overview.value.permissionDenials, hint: t('legacy.last_24_hours'), danger: overview.value.permissionDenials > 0 },
]);

function openDetail(row: SystemAuditLog) { selected.value = row; detailVisible.value = true; }

const columns: DataTableColumns<SystemAuditLog> = [
  { title: t('legacy.time'), key: 'occurredAt', width: 170, render: row => formatAdminDateTime(row.occurredAt, '-') },
  { title: t('legacy.type'), key: 'category', width: 140, render: row => h(NTag, { bordered: false, type: row.category === 'agent' ? 'info' : 'default' }, { default: () => categoryLabel(row.category) }) },
  { title: t('legacy.module'), key: 'module', width: 150, ellipsis: { tooltip: true } },
  { title: t('legacy.actions'), key: 'action', width: 150, render: row => actionLabels[row.action] || row.action },
  { title: t('legacy.actor_employee'), key: 'actor', width: 160, ellipsis: { tooltip: true } },
  { title: t('legacy.object'), key: 'target', ellipsis: { tooltip: true } },
  { title: t('legacy.result'), key: 'result', width: 90, render: row => h(NTag, { bordered: false, type: row.result === 'success' ? 'success' : 'error' }, { default: () => row.result === 'success' ? t('legacy.success_51991a5') : t('legacy.failed') }) },
  { title: t('legacy.actions'), key: 'detail', width: 80, render: row => h(NButton, { text: true, type: 'primary', onClick: () => openDetail(row) }, { default: () => t('legacy.details') }) },
];

function currentFilters(): AuditFilters {
  return { category: category.value, keyword: keyword.value.trim(), result: result.value || '', module: category.value === 'management' ? module.value || '' : '' };
}
const { exporting, exportExcel } = useAuditExport(currentFilters);

async function load() {
  loading.value = true;
  try {
    const [summary, data] = await Promise.all([
      fetchSystemAuditOverview(),
      fetchSystemAuditLogs({ ...currentFilters(), page: page.value, pageSize }),
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
  <div ref="pageRoot" class="page-stack audit-page" :style="viewportHeight === undefined ? undefined : { height: `${viewportHeight}px` }">
    <n-card class="audit-card" :bordered="false" size="large">
      <div class="audit-content">
        <div class="page-head"><PageIntro :title="t('legacy.system_audit')" :description="t('legacy.review_admin_actions_agent_capability_use_and_permission_denials')" :tags="[t('legacy.enterprise_audit_trail'), t('legacy.unified_audit')]" /><div class="head-actions"><n-button type="primary" secondary :loading="loading" @click="load">{{ t('legacy.refresh') }}
        </n-button></div></div>
        <div class="metric-grid">
          <div v-for="item in metrics" :key="item.label" class="metric-card"><span>{{ item.label }}</span><strong :class="{ danger: item.danger }">{{ item.value }}</strong><small>{{ item.hint }}</small></div>
        </div>
        <div class="audit-table-card">
          <div class="toolbar">
            <n-space :size="10" wrap>
              <n-select v-model:value="category" :options="categoryOptions" style="width: 140px" />
              <n-input v-model:value="keyword" clearable :placeholder="t('legacy.search_actor_target_or_action')" style="width: 260px" @keyup.enter="applyFilters" />
              <n-select v-model:value="result" clearable :options="resultOptions" :placeholder="t('legacy.all_results')" style="width: 140px" @update:value="applyFilters" />
              <n-select v-if="category === 'management'" v-model:value="module" clearable :options="moduleOptions" :placeholder="t('legacy.all_modules')" style="width: 170px" @update:value="applyFilters" />
              <n-button @click="applyFilters">{{ t('legacy.query') }}</n-button>
            </n-space>
            <n-button class="export-action" :loading="exporting" :title="t('audit.exportHint')" @click="exportExcel">{{ t('audit.exportExcel') }}</n-button>
          </div>
          <n-data-table class="audit-records" flex-height :columns="columns" :data="rows" :loading="loading" :bordered="false" :pagination="false" :scroll-x="1120" />
          <div class="pager-row"><span>{{ t('legacy.total_items', { count: total }) }}</span><n-pagination v-model:page="page" :page-size="pageSize" :item-count="total" /></div>
        </div>
      </div>
    </n-card>
    <AuditDetailDrawer v-model:show="detailVisible" :record="selected" />
  </div>
</template>

<style scoped>
.audit-page { height: calc(100vh - 98px); min-height: 0; overflow: hidden; }
.audit-card { flex: 1; min-height: 0; min-width: 0; border-radius: 8px; }
.audit-card :deep(.n-card__content) { display:flex; flex-direction:column; min-height:0; }
.audit-content { display: grid; grid-template-rows:auto auto minmax(0,1fr); flex:1; gap: 18px; min-width: 0; min-height:0; }
.page-head { display: flex; align-items: center; justify-content: space-between; gap: 20px; }
.head-actions { display: flex; flex: none; gap: 10px; }
.metric-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 14px; }
.metric-card { display: grid; gap: 4px; padding: 16px 18px; border: 1px solid #edf0f5; border-radius: 10px; background: #fafbfc; }
.metric-card span, .metric-card small, .pager-row { color: #667085; }
.metric-card strong { color: #172033; font-size: 28px; line-height: 1.2; }
.metric-card strong.danger { color: #d03050; }
.audit-table-card { display:flex; flex-direction:column; min-height:0; overflow: hidden; border: 1px solid #edf0f5; border-radius: 10px; }
.audit-records { flex:1; min-height:0; }
.toolbar, .pager-row { flex:none; padding: 14px 16px; }
.toolbar { display:flex; align-items:center; justify-content:space-between; gap:12px; flex-wrap:wrap; border-bottom: 1px solid #edf0f5; }
.pager-row { display: flex; align-items: center; justify-content: space-between; border-top: 1px solid #edf0f5; }
@media (max-width: 980px) { .metric-grid { grid-template-columns: repeat(2, 1fr); } .page-head { align-items: flex-start; flex-direction: column; } }
</style>
