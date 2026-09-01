<template>
  <div class="page-stack traffic-page">
    <div class="metrics-row">
      <n-card v-for="item in metricCards" :key="item.key" class="metric-card" :bordered="false" size="small">
        <div class="metric-main">
          <span class="metric-icon" :class="`metric-icon-${item.key}`" v-html="item.icon"></span>
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
            <n-input v-model:value="filters.keyword" :placeholder="t('搜索姓名 / 手机号 / 邮箱')" clearable class="keyword-input" />
          </n-space>
          <n-space :size="10" class="filter-right">
            <n-button secondary :loading="loading" @click="reload">{{ t('刷新') }}</n-button>
            <n-button secondary @click="openSettings">{{ t('设置企业额度') }}</n-button>
            <n-button secondary @click="openLogs">{{ t('分配记录') }}</n-button>
          </n-space>
        </div>
      </div>

      <div class="table-shell">
        <n-spin :show="loading" class="table-spin">
          <n-data-table
            class="allocation-table"
            flex-height
            :columns="columns"
            :data="users"
            :bordered="false"
            :pagination="pagination"
          />
        </n-spin>
      </div>
    </n-card>
  </div>

  <n-modal v-model:show="settingsVisible" preset="card" :title="t('额度设置')" style="width: 760px">
    <n-form class="settings-form" label-placement="top">
      <n-grid :cols="2" :x-gap="14" :y-gap="10" responsive="screen">
        <n-grid-item>
          <n-form-item :label="t('企业本周期总额度')">
            <n-input-number v-model:value="orgForm.totalTokens" :min="0" :show-button="false" class="wide-input" />
          </n-form-item>
        </n-grid-item>
        <n-grid-item>
          <n-form-item :label="t('企业重置周期')">
            <n-select v-model:value="orgForm.period" :options="periodOptions" />
          </n-form-item>
        </n-grid-item>
        <n-grid-item>
          <n-form-item :label="t('新成员默认额度')">
            <n-input-number
              v-model:value="defaultForm.quotaTokens"
              :min="0"
              :max="orgForm.totalTokens || 0"
              :show-button="false"
              class="wide-input"
            />
          </n-form-item>
        </n-grid-item>
        <n-grid-item>
          <n-form-item :label="t('成员重置周期')">
            <n-select v-model:value="defaultForm.period" :options="periodOptions" />
          </n-form-item>
        </n-grid-item>
      </n-grid>
      <div class="period-hint">
        {{ t('企业重置周期用于企业共享总额度；成员重置周期用于每位成员的个人额度，并同步应用到已有成员。') }}
        <br />
        {{ t('周期按企业时区的自然时间计算：自然月为每月 1 日 00:00 至下月 1 日 00:00，自然日为当天 00:00 至次日 00:00，自然小时为整点到下一整点。') }}
        <span v-if="overview?.orgPolicy.periodStartAt">
          {{ t('当前周期') }}：{{ formatDateTime(overview.orgPolicy.periodStartAt) }} - {{ formatDateTime(overview.orgPolicy.resetAt) }}
        </span>
      </div>
    </n-form>
    <template #footer>
      <n-space justify="end">
        <n-button @click="settingsVisible = false">{{ t('取消') }}</n-button>
        <n-button type="primary" :loading="savingPolicy" @click="savePolicies">{{ t('保存设置') }}</n-button>
      </n-space>
    </template>
  </n-modal>

  <n-modal v-model:show="editorVisible" preset="card" :title="t('设置用户额度')" style="width: 560px">
    <n-form :model="userForm" label-placement="left" label-width="110">
      <n-form-item :label="t('用户')">
        <div class="user-inline">
          <strong>{{ currentUser?.name || currentUser?.loginName }}</strong>
          <span>{{ currentUser?.departmentName || t('未分配部门') }}</span>
        </div>
      </n-form-item>
      <n-form-item :label="t('本周期额度')">
        <n-input-number
          v-model:value="userForm.quotaTokens"
          :min="0"
          :max="overview?.orgPolicy.totalTokens || 0"
          :show-button="false"
          class="wide-input"
        />
      </n-form-item>
      <n-form-item :label="t('重置周期')">
        <n-select v-model:value="userForm.period" :options="periodOptions" />
      </n-form-item>
      <n-form-item :label="t('备注')">
        <n-input v-model:value="userForm.reason" type="textarea" :rows="3" :placeholder="t('记录本次调整原因')" />
      </n-form-item>
    </n-form>
    <template #footer>
      <n-space justify="end">
        <n-button @click="editorVisible = false">{{ t('取消') }}</n-button>
        <n-button type="primary" :loading="savingUser" @click="saveUserPolicy">{{ t('保存') }}</n-button>
      </n-space>
    </template>
  </n-modal>

  <n-drawer v-model:show="logsVisible" :width="620" placement="right">
    <n-drawer-content :title="t('分配记录')" closable>
      <n-spin :show="logsLoading">
        <n-timeline>
          <n-timeline-item
            v-for="log in logs"
            :key="log.id"
            type="info"
            :title="`${log.userName || log.userId} ${formatDelta(log.deltaTokens)}`"
            :content="log.reason || t('无备注')"
            :time="formatDateTime(log.createdAt)"
          />
        </n-timeline>
        <n-empty v-if="!logs.length" :description="t('暂无分配记录')" />
      </n-spin>
      <div v-if="logsTotal > logsPageSize" class="logs-pagination">
        <span>{{ t('共 {count} 条记录', { count: logsTotal }) }}</span>
        <n-pagination
          v-model:page="logsPage"
          :page-size="logsPageSize"
          :item-count="logsTotal"
          size="small"
          @update:page="loadLogs"
        />
      </div>
    </n-drawer-content>
  </n-drawer>
</template>

<script setup lang="ts">
import { computed, h, onMounted, reactive, ref, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { NButton, NPagination, NProgress, NSpace, NSpin, NTimeline, NTimelineItem, useMessage, type DataTableColumns } from 'naive-ui';
import { t } from '@/composables/i18n';
import { formatAdminShortDateTime } from '@/composables/adminTimezone';
import {
  fetchAllocationLogs,
  fetchTrafficAllocationOverview,
  fetchUserAllocations,
  updateDefaultQuotaPolicy,
  updateOrgQuotaPolicy,
  updateUserQuotaPolicy,
  type AllocationLogItem,
  type QuotaPeriod,
  type QuotaStatus,
  type TrafficAllocationOverview,
  type UserAllocationItem,
} from '@/api/traffic-allocations';

const message = useMessage();
const route = useRoute();
const router = useRouter();
const loading = ref(false);
const savingPolicy = ref(false);
const savingUser = ref(false);
const settingsVisible = ref(false);
const editorVisible = ref(false);
const logsVisible = ref(false);
const overview = ref<TrafficAllocationOverview | null>(null);
const users = ref<UserAllocationItem[]>([]);
const logs = ref<AllocationLogItem[]>([]);
const logsLoading = ref(false);
const logsPage = ref(1);
const logsPageSize = 20;
const logsTotal = ref(0);
const currentUser = ref<UserAllocationItem | null>(null);

const filters = reactive({ keyword: '' });
const orgForm = reactive({ totalTokens: 0, period: 'monthly' as QuotaPeriod, timezone: 'Asia/Shanghai', status: 'active' as QuotaStatus });
const defaultForm = reactive({ quotaTokens: 0, period: 'monthly' as QuotaPeriod, status: 'active' as QuotaStatus });
const userForm = reactive({ quotaTokens: 0, period: 'monthly' as QuotaPeriod, reason: '' });

const periodOptions = computed(() => [
  { label: t('自然月重置（每月 1 日 00:00）'), value: 'monthly' },
  { label: t('自然日重置（每天 00:00）'), value: 'daily' },
  { label: t('自然小时重置（每小时整点）'), value: 'hourly' },
]);
function formatTokens(value: number) {
  const amount = Number(value || 0);
  if (amount >= 100000000) return `${(amount / 100000000).toFixed(1)} 亿`;
  if (amount >= 10000) return `${(amount / 10000).toFixed(1)} 万`;
  return amount.toLocaleString('zh-CN');
}

function periodLabel(value: string) {
  if (value === 'daily') return t('自然日');
  if (value === 'hourly') return t('自然小时');
  return t('自然月');
}

function formatDateTime(value?: string) {
  return formatAdminShortDateTime(value, '-');
}

function percent(row: UserAllocationItem) {
  if (!row.quotaTokens) return 0;
  return Math.max(0, Math.min(100, Math.round((row.usedTokens / row.quotaTokens) * 100)));
}

function formatDelta(value: number) {
  const amount = Number(value || 0);
  if (amount === 0) return t('额度未变化');
  return `${amount > 0 ? '+' : ''}${formatTokens(amount)} Token`;
}

function isQuotaBlank(value: unknown) {
  return value === null || value === undefined || value === '';
}

function userContactParts(row: UserAllocationItem) {
  return [row.email, row.mobile].filter((item) => String(item || '').trim());
}

function userContactText(row: UserAllocationItem) {
  const parts = userContactParts(row);
  return parts.length ? parts.join(' / ') : '-';
}

const metricCards = computed(() => {
  const org = overview.value?.orgPolicy;
  const def = overview.value?.defaultPolicy;
  return [
    {
      key: 'pool',
      label: t('企业总额度'),
      value: formatTokens(org?.totalTokens || 0),
      note: `${periodLabel(org?.period || 'monthly')} · ${t('下次重置')} ${formatDateTime(org?.resetAt)}`,
      icon: '<svg viewBox="0 0 24 24"><path d="M4 19h16M6 17V9m6 8V5m6 12v-6" /></svg>',
    },
    {
      key: 'used',
      label: t('本周期已用'),
      value: formatTokens(org?.usedTokens || 0),
      note: `${t('剩余')} ${formatTokens(org?.remainingTokens || 0)} Token`,
      icon: '<svg viewBox="0 0 24 24"><path d="M12 3v18M6 8h9a3 3 0 0 1 0 6H9" /></svg>',
    },
    {
      key: 'default',
      label: t('默认成员额度'),
      value: formatTokens(def?.quotaTokens || 0),
      note: `${periodLabel(def?.period || 'monthly')} · ${def?.status === 'active' ? t('启用') : t('禁用')}`,
      icon: '<svg viewBox="0 0 24 24"><path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2M9 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8Zm13 10v-2a4 4 0 0 0-3-3.87" /></svg>',
    },
    {
      key: 'policy',
      label: t('自定义额度用户'),
      value: String(overview.value?.assignedPolicyCount || 0),
      note: `${t('已分配专属额度')} ${formatTokens(overview.value?.assignedTokens || 0)} Token`,
      icon: '<svg viewBox="0 0 24 24"><path d="m9 12 2 2 4-5M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z" /></svg>',
    },
  ];
});

const columns: DataTableColumns<UserAllocationItem> = [
  {
    title: t('用户'),
    key: 'name',
    render(row) {
      return h('div', { class: 'user-cell' }, [
        h('div', { class: 'user-main-line', style: 'display:flex;align-items:center;gap:8px;min-width:0;' }, [
          h(
            'strong',
            {
              style: 'color:#0f172a;font-weight:650;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;',
            },
            row.name || row.loginName || '-',
          ),
          row.loginName && row.loginName !== row.name
            ? h('span', { class: 'login-name', style: 'flex:0 0 auto;color:#a3adbd;font-size:14px;' }, row.loginName)
            : null,
        ]),
        h(
          'div',
          {
            class: 'user-contact-line',
            style: 'color:#8b97a8;font-size:14px;line-height:20px;word-break:break-all;',
          },
          userContactText(row),
        ),
        h(
          'span',
          {
            class: 'user-department',
            style:
              'width:fit-content;max-width:100%;border-radius:4px;background:#f6f8fb;color:#8b97a8;font-size:14px;line-height:22px;padding:0 6px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;',
          },
          row.departmentName || t('未分配部门'),
        ),
      ]);
    },
  },
  {
    title: t('分配额度'),
    key: 'quotaTokens',
    render: (row) => `${formatTokens(row.quotaTokens)} Token`,
  },
  {
    title: t('已用 / 剩余'),
    key: 'usage',
    render(row) {
      return h('div', { class: 'usage-cell' }, [
        h(NProgress, { type: 'line', percentage: percent(row), height: 6, showIndicator: false, borderRadius: 4 }),
        h('span', `${formatTokens(row.usedTokens)} / ${formatTokens(row.remainingTokens)}`),
      ]);
    },
  },
  {
    title: t('周期'),
    key: 'period',
    render: (row) => periodLabel(row.period),
  },
  {
    title: t('操作'),
    key: 'actions',
    width: 120,
    render(row) {
      return h(NSpace, { size: 8 }, () => [
        h(NButton, { size: 'small', tertiary: true, onClick: () => openEditor(row) }, () => t('设置个人额度')),
      ]);
    },
  },
];

const pagination = { pageSize: 12 };

function syncForms() {
  if (!overview.value) return;
  Object.assign(orgForm, overview.value.orgPolicy);
  Object.assign(defaultForm, overview.value.defaultPolicy);
}

async function reload() {
  loading.value = true;
  try {
    const [nextOverview, nextUsers] = await Promise.all([
      fetchTrafficAllocationOverview(),
      fetchUserAllocations({ keyword: filters.keyword }),
    ]);
    overview.value = nextOverview;
    users.value = nextUsers;
    syncForms();
  } finally {
    loading.value = false;
  }
}

function consumeOpenQuotaQuery() {
  if (route.query.open !== 'quota') return;
  openSettings();
  const nextQuery = { ...route.query };
  delete nextQuery.open;
  router.replace({ path: route.path, query: nextQuery });
}

async function savePolicies() {
  if (isQuotaBlank(orgForm.totalTokens)) {
    message.warning(t('请填写企业本周期总额度'));
    return;
  }
  if (isQuotaBlank(defaultForm.quotaTokens)) {
    message.warning(t('请填写新成员默认额度'));
    return;
  }
  if (!orgForm.totalTokens && defaultForm.quotaTokens > 0) {
    message.warning(t('企业总额度为 0，不能为成员分配额度'));
    return;
  }
  savingPolicy.value = true;
  try {
    await updateOrgQuotaPolicy(orgForm);
    await updateDefaultQuotaPolicy(defaultForm);
    message.success(t('保存成功'));
    settingsVisible.value = false;
    await reload();
  } finally {
    savingPolicy.value = false;
  }
}

function openSettings() {
  syncForms();
  settingsVisible.value = true;
}

function openEditor(row: UserAllocationItem) {
  if (!overview.value?.orgPolicy.totalTokens) {
    message.warning(t('企业总额度为 0，不能为用户分配额度'));
    return;
  }
  currentUser.value = row;
  Object.assign(userForm, {
    quotaTokens: row.quotaTokens,
    period: row.period,
    reason: '',
  });
  editorVisible.value = true;
}

async function saveUserPolicy() {
  if (!currentUser.value) return;
  if (isQuotaBlank(userForm.quotaTokens)) {
    message.warning(t('请填写本周期额度'));
    return;
  }
  if (!overview.value?.orgPolicy.totalTokens && userForm.quotaTokens > 0) {
    message.warning(t('企业总额度为 0，不能为用户分配额度'));
    return;
  }
  savingUser.value = true;
  try {
    await updateUserQuotaPolicy(currentUser.value.userId, { userId: currentUser.value.userId, ...userForm });
    message.success(t('保存成功'));
    editorVisible.value = false;
    await reload();
  } finally {
    savingUser.value = false;
  }
}

async function openLogs() {
  logsVisible.value = true;
  logsPage.value = 1;
  await loadLogs();
}

async function loadLogs() {
  logsLoading.value = true;
  try {
    const result = await fetchAllocationLogs({ page: logsPage.value, pageSize: logsPageSize });
    logs.value = result.items;
    logsTotal.value = result.total;
  } finally {
    logsLoading.value = false;
  }
}

watch(() => filters.keyword, () => reload());
watch(
  () => route.query.open,
  () => consumeOpenQuotaQuery(),
);
onMounted(async () => {
  await reload();
  consumeOpenQuotaQuery();
});
</script>

<style scoped>
.traffic-page {
  height: calc(100vh - 64px);
  min-height: 0;
  gap: 16px;
  overflow: hidden;
}

.metrics-row {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
  padding: 12px;
}

.metric-card {
  border: 1px solid #e6ebf5;
  background: #fff;
  border-radius: 8px;
  box-shadow: 0 4px 12px rgba(29, 54, 110, 0.04);
}

.metric-main {
  display: flex;
  gap: 12px;
  align-items: center;
}

.metric-icon {
  display: inline-flex;
  width: 42px;
  height: 42px;
  align-items: center;
  justify-content: center;
  border-radius: 8px;
  color: #2563eb;
  background: #eff6ff;
}

.metric-icon :deep(svg),
.metric-icon svg {
  width: 22px;
  height: 22px;
  stroke: currentColor;
  fill: none;
  stroke-width: 2;
  stroke-linecap: round;
  stroke-linejoin: round;
}

.metric-label,
.metric-note {
  color: #64748b;
  font-size: 12px;
}

.metric-value {
  margin-top: 4px;
  color: #0f172a;
  font-size: 24px;
  font-weight: 700;
}

.list-card {
  width: calc(100% - 24px);
  margin: -16px 12px 0;
  flex: 1;
  min-height: 0;
  overflow: hidden;
  border-radius: 8px;
  box-shadow: 0 4px 12px rgba(29, 54, 110, 0.04);
}

.list-card :deep(.n-card__content) {
  height: 100%;
  display: flex;
  flex-direction: column;
}

.settings-form {
  padding-top: 2px;
}

.period-hint {
  margin-top: 2px;
  color: #64748b;
  font-size: 12px;
  line-height: 1.6;
}

.period-hint span {
  display: block;
  color: #334155;
}

.wide-input {
  width: 100%;
}

.list-filter-row {
  padding: 16px 0 12px;
  border-bottom: 1px solid #edf1f7;
  margin-bottom: 12px;
}

.table-shell {
  height: max(360px, calc(100vh - 250px));
  min-height: 0;
  overflow: hidden;
}

.table-spin,
.table-spin :deep(.n-spin-content),
.allocation-table {
  height: 100%;
}

.filter-toolbar {
  display: flex;
  justify-content: space-between;
  gap: 12px;
}

.keyword-input {
  width: 280px;
}

.user-cell {
  display: flex;
  flex-direction: column;
  gap: 6px;
  min-width: 260px;
}

.user-main-line {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.user-main-line strong {
  color: #0f172a;
  font-weight: 650;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.login-name {
  flex: 0 0 auto;
  color: #a3adbd;
  font-size: 14px;
}

.user-contact-line {
  display: flex;
  flex-wrap: wrap;
  gap: 4px 10px;
  min-width: 0;
}

.user-contact-item {
  color: #8b97a8;
  font-size: 14px;
  line-height: 20px;
  word-break: break-all;
}

.user-department {
  width: fit-content;
  max-width: 100%;
  border-radius: 4px;
  background: #f6f8fb;
  color: #8b97a8;
  font-size: 14px;
  line-height: 22px;
  padding: 0 6px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.usage-cell span {
  color: #64748b;
  font-size: 12px;
}

.usage-cell {
  display: grid;
  gap: 6px;
  min-width: 180px;
}

.user-inline {
  display: flex;
  flex-direction: column;
  gap: 3px;
}

.user-inline span {
  color: #64748b;
  font-size: 12px;
}

.logs-pagination {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding-top: 14px;
  border-top: 1px solid #edf1f7;
  color: #64748b;
  font-size: 12px;
}

@media (max-width: 1100px) {
  .metrics-row {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .filter-toolbar {
    flex-direction: column;
    align-items: stretch;
  }
}
</style>
