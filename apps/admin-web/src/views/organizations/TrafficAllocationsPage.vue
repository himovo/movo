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
            <n-input v-model:value="filters.keyword" :placeholder="t('additional.search_name_phone_number_email')" clearable class="keyword-input" />
          </n-space>
          <n-space :size="10" class="filter-right">
            <n-button secondary :loading="loading" @click="reload">{{ t('legacy.refresh') }}</n-button>
            <n-button secondary @click="openSettings">{{ t('legacy.set_enterprise_quota') }}</n-button>
            <n-button secondary @click="openLogs">{{ t('legacy.allocation_records') }}</n-button>
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

  <n-modal v-model:show="settingsVisible" preset="card" :title="t('legacy.quota_settings')" style="width: 760px">
    <n-form class="settings-form" label-placement="top">
      <n-grid :cols="2" :x-gap="14" :y-gap="10" responsive="screen">
        <n-grid-item>
          <n-form-item :label="t('legacy.enterprise_quota_this_period')">
            <n-input-number v-model:value="orgForm.totalTokens" :min="0" :show-button="false" class="wide-input" />
          </n-form-item>
        </n-grid-item>
        <n-grid-item>
          <n-form-item :label="t('legacy.enterprise_reset_period')">
            <n-select v-model:value="orgForm.period" :options="periodOptions" />
          </n-form-item>
        </n-grid-item>
        <n-grid-item>
          <n-form-item :label="t('legacy.default_new_member_quota')">
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
          <n-form-item :label="t('legacy.member_reset_period')">
            <n-select v-model:value="defaultForm.period" :options="periodOptions" />
          </n-form-item>
        </n-grid-item>
      </n-grid>
      <div class="period-hint">
        {{ t('legacy.the_organization_reset_period_applies_to_the_shared_organization') }}
        <br />
        {{ t('legacy.periods_use_the_enterprise_timezone_calendar_month_runs_from') }}
        <span v-if="overview?.orgPolicy.periodStartAt">
          {{ t('legacy.current_period') }}：{{ formatDateTime(overview.orgPolicy.periodStartAt) }} - {{ formatDateTime(overview.orgPolicy.resetAt) }}
        </span>
      </div>
    </n-form>
    <template #footer>
      <n-space justify="end">
        <n-button @click="settingsVisible = false">{{ t('legacy.cancel') }}</n-button>
        <n-button type="primary" :loading="savingPolicy" @click="savePolicies">{{ t('legacy.save_settings') }}</n-button>
      </n-space>
    </template>
  </n-modal>

  <n-modal v-model:show="editorVisible" preset="card" :title="t('legacy.set_user_quota')" style="width: 560px">
    <n-form :model="userForm" label-placement="left" label-width="110">
      <n-form-item :label="t('legacy.user_9ba763e')">
        <div class="user-inline">
          <strong>{{ currentUser?.name || currentUser?.loginName }}</strong>
          <span>{{ currentUser?.departmentName || t('legacy.no_dept') }}</span>
        </div>
      </n-form-item>
      <n-form-item :label="t('legacy.quota_this_period')">
        <n-input-number
          v-model:value="userForm.quotaTokens"
          :min="0"
          :max="overview?.orgPolicy.totalTokens || 0"
          :show-button="false"
          class="wide-input"
        />
      </n-form-item>
      <n-form-item :label="t('legacy.reset_period')">
        <n-select v-model:value="userForm.period" :options="periodOptions" />
      </n-form-item>
      <n-form-item :label="t('legacy.note')">
        <n-input v-model:value="userForm.reason" type="textarea" :rows="3" :placeholder="t('legacy.record_the_reason_for_this_adjustment')" />
      </n-form-item>
    </n-form>
    <template #footer>
      <n-space justify="end">
        <n-button @click="editorVisible = false">{{ t('legacy.cancel') }}</n-button>
        <n-button type="primary" :loading="savingUser" @click="saveUserPolicy">{{ t('legacy.save') }}</n-button>
      </n-space>
    </template>
  </n-modal>

  <n-drawer v-model:show="logsVisible" :width="620" placement="right">
    <n-drawer-content :title="t('legacy.allocation_records')" closable>
      <n-spin :show="logsLoading">
        <n-timeline>
          <n-timeline-item
            v-for="log in logs"
            :key="log.id"
            type="info"
            :title="`${log.userName || log.userId} ${formatDelta(log.deltaTokens)}`"
            :content="log.reason || t('legacy.no_note')"
            :time="formatDateTime(log.createdAt)"
          />
        </n-timeline>
        <n-empty v-if="!logs.length" :description="t('legacy.no_allocation_records')" />
      </n-spin>
      <div v-if="logsTotal > logsPageSize" class="logs-pagination">
        <span>{{ t('legacy.total_records', { count: logsTotal }) }}</span>
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
  { label: t('legacy.calendar_month_1st_day_00_00'), value: 'monthly' },
  { label: t('legacy.calendar_day_daily_00_00'), value: 'daily' },
  { label: t('legacy.clock_hour_top_of_each_hour'), value: 'hourly' },
]);
function formatTokens(value: number) {
  const amount = Number(value || 0);
  if (amount >= 100000000) return `${(amount / 100000000).toFixed(1)} 亿`;
  if (amount >= 10000) return `${(amount / 10000).toFixed(1)} 万`;
  return amount.toLocaleString('zh-CN');
}

function periodLabel(value: string) {
  if (value === 'daily') return t('legacy.calendar_day');
  if (value === 'hourly') return t('legacy.clock_hour');
  return t('legacy.calendar_month');
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
  if (amount === 0) return t('legacy.quota_unchanged');
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
      label: t('legacy.enterprise_quota'),
      value: formatTokens(org?.totalTokens || 0),
      note: `${periodLabel(org?.period || 'monthly')} · ${t('legacy.next_reset')} ${formatDateTime(org?.resetAt)}`,
      icon: '<svg viewBox="0 0 24 24"><path d="M4 19h16M6 17V9m6 8V5m6 12v-6" /></svg>',
    },
    {
      key: 'used',
      label: t('legacy.used_this_period'),
      value: formatTokens(org?.usedTokens || 0),
      note: `${t('legacy.remaining')} ${formatTokens(org?.remainingTokens || 0)} Token`,
      icon: '<svg viewBox="0 0 24 24"><path d="M12 3v18M6 8h9a3 3 0 0 1 0 6H9" /></svg>',
    },
    {
      key: 'default',
      label: t('legacy.default_member_quota'),
      value: formatTokens(def?.quotaTokens || 0),
      note: `${periodLabel(def?.period || 'monthly')} · ${def?.status === 'active' ? t('legacy.active') : t('legacy.disabled_be70be5')}`,
      icon: '<svg viewBox="0 0 24 24"><path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2M9 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8Zm13 10v-2a4 4 0 0 0-3-3.87" /></svg>',
    },
    {
      key: 'policy',
      label: t('legacy.custom_quota_users'),
      value: String(overview.value?.assignedPolicyCount || 0),
      note: `${t('legacy.custom_quota_allocated')} ${formatTokens(overview.value?.assignedTokens || 0)} Token`,
      icon: '<svg viewBox="0 0 24 24"><path d="m9 12 2 2 4-5M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z" /></svg>',
    },
  ];
});

const columns: DataTableColumns<UserAllocationItem> = [
  {
    title: t('legacy.user_9ba763e'),
    key: 'name',
    render(row) {
      return h('div', { class: 'user-cell' }, [
        h('div', { class: 'user-main-line' }, [
          h('strong', row.name || row.loginName || '-'),
          row.loginName && row.loginName !== row.name
            ? h('span', { class: 'login-name' }, row.loginName)
            : null,
        ]),
        h(
          'div',
          {
            class: 'user-contact-line',
          },
          userContactText(row),
        ),
        h(
          'span',
          {
            class: 'user-department',
          },
          row.departmentName || t('legacy.no_dept'),
        ),
      ]);
    },
  },
  {
    title: t('legacy.allocated_quota'),
    key: 'quotaTokens',
    render: (row) => `${formatTokens(row.quotaTokens)} Token`,
  },
  {
    title: t('legacy.used_remaining'),
    key: 'usage',
    render(row) {
      return h('div', { class: 'usage-cell' }, [
        h(NProgress, { type: 'line', percentage: percent(row), height: 6, showIndicator: false, borderRadius: 4 }),
        h('span', `${formatTokens(row.usedTokens)} / ${formatTokens(row.remainingTokens)}`),
      ]);
    },
  },
  {
    title: t('legacy.period'),
    key: 'period',
    render: (row) => periodLabel(row.period),
  },
  {
    title: t('legacy.actions'),
    key: 'actions',
    width: 120,
    render(row) {
      return h(NSpace, { size: 8 }, () => [
        h(NButton, { size: 'small', tertiary: true, onClick: () => openEditor(row) }, () => t('legacy.set_personal_quota')),
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
    message.warning(t('additional.enter_the_organization_s_total_quota_for_this_period'));
    return;
  }
  if (isQuotaBlank(defaultForm.quotaTokens)) {
    message.warning(t('additional.enter_the_default_quota_for_new_members'));
    return;
  }
  if (!orgForm.totalTokens && defaultForm.quotaTokens > 0) {
    message.warning(t('legacy.enterprise_quota_is_0_so_member_quota_cannot_be'));
    return;
  }
  savingPolicy.value = true;
  try {
    await updateOrgQuotaPolicy(orgForm);
    await updateDefaultQuotaPolicy(defaultForm);
    message.success(t('legacy.saved_successfully'));
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
    message.warning(t('legacy.enterprise_quota_is_0_so_user_quota_cannot_be'));
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
    message.warning(t('additional.enter_the_quota_for_this_period'));
    return;
  }
  if (!overview.value?.orgPolicy.totalTokens && userForm.quotaTokens > 0) {
    message.warning(t('legacy.enterprise_quota_is_0_so_user_quota_cannot_be'));
    return;
  }
  savingUser.value = true;
  try {
    await updateUserQuotaPolicy(currentUser.value.userId, { userId: currentUser.value.userId, ...userForm });
    message.success(t('legacy.saved_successfully'));
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
  color: #8b97a8;
  font-size: 14px;
  line-height: 20px;
  word-break: break-all;
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
