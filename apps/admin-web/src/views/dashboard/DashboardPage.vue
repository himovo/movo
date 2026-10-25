<template>
  <div class="dashboard-page">
    <n-spin :show="loading">
      <section class="metrics-grid">
        <article v-for="metric in metricCards" :key="metric.key" class="metric-card">
          <div class="metric-head">
            <span class="metric-icon" v-html="metric.icon"></span>
            <span class="metric-label">{{ metric.label }}</span>
          </div>
          <div class="metric-value">{{ metric.value }}</div>
          <div class="metric-note">{{ metric.note }}</div>
        </article>
      </section>

      <section class="content-grid observation-grid">
        <n-card class="panel-card span-8 activity-panel" :bordered="false" size="large">
          <template #header>
            <div class="panel-header">
              <span>{{ t('legacy.recent_activities') }}</span>
              <n-button quaternary size="small" @click="go('/token-stats')">{{ t('legacy.view_all') }}</n-button>
            </div>
          </template>

          <div v-if="recentActivity.length" class="activity-table">
            <div class="table-row table-head">
              <span>{{ t('legacy.task') }}</span>
              <span>{{ t('legacy.model') }}</span>
              <span>{{ t('legacy.status') }}</span>
              <span>{{ t('Token') }}</span>
              <span>{{ t('legacy.duration') }}</span>
            </div>
            <div v-for="(item, index) in visibleRecentActivity" :key="item.requestId || item.sessionId || `activity-${index}`" class="table-row">
              <div class="activity-main">
                <strong>{{ item.title ? translateSourceText(item.title) : t('legacy.llm_call') }}</strong>
                <small>{{ item.userName || t('legacy.unknown_user') }} · {{ item.departmentName || t('legacy.no_dept') }} · {{ formatTime(item.createdAt) }}</small>
              </div>
              <span class="table-muted table-model" :title="item.modelName || t('legacy.default_model')">{{ item.modelName || t('legacy.default_model') }}</span>
              <n-tag size="small" :type="item.status === 'failed' ? 'error' : 'success'" :bordered="false">
                {{ item.status === 'failed' ? t('legacy.failed') : t('legacy.success') }}
              </n-tag>
              <span>{{ formatNumber(item.totalTokens) }}</span>
              <span>{{ formatDuration(item.durationMs) }}</span>
            </div>
          </div>
          <div v-else class="empty-state">
            <div class="empty-icon">
              <svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
                <path d="M4 19V5" />
                <path d="M4 19h16" />
                <path d="M8 15v-4" />
                <path d="M12 15V8" />
                <path d="M16 15v-2" />
              </svg>
            </div>
            <div class="empty-title">{{ t('legacy.no_activity_log') }}</div>
            <div class="empty-copy">{{ t('legacy.no_llm_calls_yet_recent_activity_will_be_shown') }}</div>
          </div>
        </n-card>

        <div class="span-4 side-stack">
          <section class="deployment-card" :class="`health-${healthStatus}`">
            <div class="deployment-head">
              <div class="deployment-title">
                <span class="health-dot" aria-hidden="true"></span>
                <strong>{{ overview?.billing.orgName || t('legacy.org_space') }}</strong>
              </div>
              <component :is="ProductDashboardEditionBadge" v-if="ProductDashboardEditionBadge" />
              <n-tag v-else size="small" :bordered="false" :type="editionTagType">{{ productEditionLabel }}</n-tag>
            </div>
            <div class="deployment-status">
              <strong>{{ healthLabel }}</strong>
              <span>{{ healthNote }}</span>
            </div>
            <div class="deployment-facts">
              <span><strong>{{ overview?.billing.currentMembersCount ?? 0 }}</strong> {{ memberCapacityLabel }}</span>
              <span><strong>{{ overview?.billing.isOwnModel ? t('legacy.enabled_d78cde0') : t('legacy.disabled_b9004e6') }}</strong> {{ t('legacy.own_models') }}</span>
            </div>
            <component
              :is="ProductDashboardBillingActions"
              v-if="ProductDashboardBillingActions && overview"
              :billing="overview.billing"
            />
          </section>

          <n-card class="panel-card todo-panel" :bordered="false" size="large">
            <template #header>
              <div class="panel-header">
                <span>{{ t('legacy.todo_list') }}</span>
                <n-button quaternary size="small" @click="loadOverview">{{ t('legacy.refresh') }}</n-button>
              </div>
            </template>

            <div v-if="todos.length" class="todo-list">
              <button v-for="todo in todos" :key="todo.title" class="todo-item" type="button" @click="go(todo.route)">
                <span class="todo-mark" :class="`todo-${todo.level}`"></span>
                <span class="todo-copy">
                  <strong>{{ translateDashboardText(todo.title) }}</strong>
                  <small>{{ translateDashboardText(todo.description) }}</small>
                </span>
                <span class="todo-arrow">›</span>
              </button>
            </div>
            <div v-else class="empty-state compact">
              <div class="empty-title">{{ t('legacy.no_pending_actions') }}</div>
              <div class="empty-copy">{{ t('legacy.everything_looks_good_no_issues_found_with_models_skills') }}</div>
            </div>
          </n-card>

        </div>
      </section>

      <section class="content-grid">
        <n-card class="panel-card span-8" :bordered="false" size="large">
          <template #header>{{ t('legacy.core_assets') }}</template>
          <div class="asset-grid">
            <button v-for="asset in assetCards" :key="asset.key" class="asset-card" type="button" @click="go(asset.route)">
              <div class="asset-title">{{ asset.title }}</div>
              <div class="asset-value">{{ asset.value }}</div>
              <div class="asset-lines">
                <span v-for="line in asset.lines" :key="line">{{ line }}</span>
              </div>
            </button>
          </div>
        </n-card>

        <n-card class="panel-card span-4" :bordered="false" size="large">
          <template #header>{{ t('legacy.quick_actions') }}</template>
          <div class="quick-grid">
            <n-button v-for="action in quickActions" :key="action.label" secondary @click="go(action.route)">
              <template #icon>
                <span class="button-icon" v-html="action.icon"></span>
              </template>
              {{ action.label }}
            </n-button>
          </div>
        </n-card>

      </section>

      <n-alert v-if="errorText" type="warning" :bordered="false" closable @close="errorText = ''">
        {{ errorText }}
      </n-alert>
    </n-spin>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';
import { useRouter } from 'vue-router';
import { apiClient } from '@/api/client';
import { t, translateSourceText, useLocale } from '@/composables/i18n';
import { formatAdminShortDateTime } from '@/composables/adminTimezone';
import { translateDashboardText } from './dashboardText';
import adminProductUiExtension from '@movo-admin-product-extension';

type HealthStatus = 'healthy' | 'warning' | 'critical';
type TodoLevel = 'error' | 'warning' | 'info';

interface DashboardOverview {
  billing: {
    orgName: string;
    edition: 'community' | 'cloud';
    tier: string;
    billingEnabled: boolean;
    currentMembersCount: number;
    userLimit: number | null;
    totalPoints: number;
    usedPoints: number;
    remainingPoints: number;
    isOwnModel: boolean;
  };
  health: {
    status: HealthStatus;
    warnings: string[];
  };
  metrics: {
    calls24h: number;
    tokens24h: number;
    costs24hByCurrency: Record<'CNY' | 'USD', number>;
    pricedCalls24hByCurrency: Record<'CNY' | 'USD', number>;
    unpricedCalls24h: number;
    activeUsers24h: number;
    activeDepartments24h: number;
    failedCalls24h: number;
    successRate24h: number | null;
    avgDurationMs24h: number;
    lastCalledAt: string | null;
  };
  assets: {
    users: { total: number; disabled: number; departments: number };
    models: { total: number; active: number; failedHealth: number };
    skills: { total: number; enabled: number; workflow: number; writingStyle: number };
    tools: { total: number; active: number; mcp: number; failed: number; untested: number };
  };
  todos: Array<{ level: TodoLevel; title: string; description: string; route: string }>;
  recentActivity: Array<{
    requestId: string;
    sessionId: string;
    userName: string;
    departmentName: string;
    modelName: string;
    title: string;
    status: string;
    totalTokens: number;
    durationMs: number;
    createdAt: string | null;
  }>;
}

const router = useRouter();
const { locale } = useLocale();
const ProductDashboardBillingActions = adminProductUiExtension.dashboardBillingActions;
const overview = ref<DashboardOverview | null>(null);
const loading = ref(false);
const errorText = ref('');

const emptyMetrics = {
  calls24h: 0,
  tokens24h: 0,
  costs24hByCurrency: { CNY: 0, USD: 0 },
  pricedCalls24hByCurrency: { CNY: 0, USD: 0 },
  unpricedCalls24h: 0,
  activeUsers24h: 0,
  activeDepartments24h: 0,
  failedCalls24h: 0,
  successRate24h: null,
  avgDurationMs24h: 0,
  lastCalledAt: null,
};

const metrics = computed(() => overview.value?.metrics || emptyMetrics);
const assets = computed(() => overview.value?.assets);
const todos = computed(() => overview.value?.todos || []);
const recentActivity = computed(() => overview.value?.recentActivity || []);
const visibleRecentActivity = computed(() => recentActivity.value.slice(0, 4));
const healthStatus = computed<HealthStatus>(() => overview.value?.health.status || 'healthy');
const isCommunity = computed(() => overview.value?.billing.edition === 'community');
const ProductDashboardEditionBadge = adminProductUiExtension.dashboardEditionBadge;
const productEditionLabel = computed(() => {
  const extensionLabel = adminProductUiExtension.productEditionLabel;
  return extensionLabel ? translateSourceText(extensionLabel) : tierLabel.value;
});
const editionTagType = computed(() => adminProductUiExtension.productEditionTagType || (isCommunity.value ? 'success' : 'info'));
const tierLabel = computed(() => {
  if (isCommunity.value) return t('legacy.community_edition');
  const tier = overview.value?.billing.tier;
  if (tier === 'plus') return t('legacy.plus_personal');
  if (tier === 'pro') return t('legacy.pro_team');
  if (tier === 'enterprise') return t('legacy.enterprise');
  return t('legacy.free_edition');
});
const memberCapacityLabel = computed(() => {
  const limit = overview.value?.billing.userLimit;
  return limit === null || limit === undefined ? t('legacy.members_unlimited') : t('additional.members', { count: limit });
});
const healthLabel = computed(() => {
  if (healthStatus.value === 'critical') return t('legacy.need_action');
  if (healthStatus.value === 'warning') return t('legacy.to_be_confirmed');
  return t('legacy.healthy');
});
const healthNote = computed(() => {
  const warnings = overview.value?.health.warnings || [];
  if (!warnings.length) return t('legacy.no_anomalies_detected_in_the_last_24h');
  return warnings.slice(0, 2).map(w => translateSourceText(w)).join(locale.value === 'zh-CN' ? '、' : ', ');
});

const icons = {
  calls: '<svg viewBox="0 0 24 24" fill="none"><path d="M4 5h16v14H4z"/><path d="M8 9h8"/><path d="M8 13h5"/></svg>',
  tokens: '<svg viewBox="0 0 24 24" fill="none"><path d="M12 3 4 7l8 4 8-4-8-4Z"/><path d="m4 12 8 4 8-4"/><path d="m4 17 8 4 8-4"/></svg>',
  users: '<svg viewBox="0 0 24 24" fill="none"><path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M22 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg>',
  success: '<svg viewBox="0 0 24 24" fill="none"><path d="M20 6 9 17l-5-5"/><path d="M21 12a9 9 0 1 1-3-6.7"/></svg>',
  cost: '<svg viewBox="0 0 24 24" fill="none"><path d="M12 2v20"/><path d="M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6"/></svg>',
  speed: '<svg viewBox="0 0 24 24" fill="none"><path d="M12 14l4-4"/><path d="M3.34 19a10 10 0 1 1 17.32 0"/></svg>',
  plus: '<svg viewBox="0 0 24 24" fill="none"><path d="M12 5v14"/><path d="M5 12h14"/></svg>',
  chart: '<svg viewBox="0 0 24 24" fill="none"><path d="M4 19V5"/><path d="M4 19h16"/><path d="M8 16v-5"/><path d="M12 16V8"/><path d="M16 16v-3"/></svg>',
};

const metricCards = computed(() => [
  {
    key: 'calls',
    label: t('legacy.calls_24h'),
    value: formatNumber(metrics.value.calls24h),
    note: t('legacy.failed_times', { count: metrics.value.failedCalls24h }),
    icon: icons.calls,
  },
  {
    key: 'tokens',
    label: t('legacy.tokens_consumed'),
    value: formatCompact(metrics.value.tokens24h),
    note: t('legacy.last_24_hours_total'),
    icon: icons.tokens,
  },
  {
    key: 'users',
    label: t('legacy.active_users'),
    value: formatNumber(metrics.value.activeUsers24h),
    note: t('legacy.active_departments', { count: metrics.value.activeDepartments24h }),
    icon: icons.users,
  },
  {
    key: 'success',
    label: t('legacy.success_rate'),
    value: metrics.value.successRate24h === null ? '—' : `${metrics.value.successRate24h}%`,
    note: metrics.value.lastCalledAt ? t('legacy.last_called', { time: formatTime(metrics.value.lastCalledAt) }) : t('legacy.no_calls'),
    icon: icons.success,
  },
  {
    key: 'cost',
    label: t('legacy.cost_24h'),
    value: formatCurrencyCosts(metrics.value.costs24hByCurrency, metrics.value.pricedCalls24hByCurrency),
    note: metrics.value.unpricedCalls24h ? t('tokenStats.unpriced', { count: metrics.value.unpricedCalls24h }) : t('tokenStats.currentRate'),
    icon: icons.cost,
  },
  {
    key: 'speed',
    label: t('legacy.avg_duration'),
    value: formatDuration(metrics.value.avgDurationMs24h),
    note: t('legacy.timed_calls_only'),
    icon: icons.speed,
  },
]);

const assetCards = computed(() => {
  const current = assets.value;
  return [
    {
      key: 'models',
      title: t('legacy.models'),
      value: current ? formatNumber(current.models.total) : '0',
      lines: current
        ? [t('legacy.organization_models') + ' ' + current.models.total, t('legacy.active') + ' ' + current.models.active, t('legacy.failed_5caf279') + ' ' + current.models.failedHealth]
        : [t('legacy.no_data')],
      route: '/models',
    },
    {
      key: 'skills',
      title: t('legacy.skills'),
      value: current ? formatNumber(current.skills.total) : '0',
      lines: current
        ? [t('legacy.active') + ' ' + current.skills.enabled, t('legacy.workflow') + ' ' + current.skills.workflow, t('legacy.writing_guidelines') + ' ' + current.skills.writingStyle]
        : [t('legacy.no_data')],
      route: '/skills',
    },
    {
      key: 'tools',
      title: t('legacy.tools_mcp'),
      value: current ? formatNumber(current.tools.total) : '0',
      lines: current
        ? [t('legacy.active') + ' ' + current.tools.active, 'MCP ' + current.tools.mcp, t('legacy.failed') + ' ' + current.tools.failed + ' / ' + t('legacy.not_set') + ' ' + current.tools.untested]
        : [t('legacy.no_data')],
      route: '/tools',
    },
    {
      key: 'users',
      title: t('legacy.users'),
      value: current ? formatNumber(current.users.total) : '0',
      lines: current ? [t('legacy.dept') + ' ' + current.users.departments, t('legacy.disabled') + ' ' + current.users.disabled] : [t('legacy.no_data')],
      route: '/organizations/users',
    },
  ];
});

const quickActions = computed(() => [
  { label: t('legacy.new_model'), route: '/models', icon: icons.plus },
  { label: t('legacy.add_skill'), route: '/skills', icon: icons.plus },
  { label: t('legacy.new_tool'), route: '/tools/new', icon: icons.plus },
  { label: t('legacy.users'), route: '/organizations/users', icon: icons.users },
  { label: t('legacy.token_stats'), route: '/token-stats', icon: icons.chart },
]);

async function loadOverview() {
  loading.value = true;
  errorText.value = '';
  try {
    const { data } = await apiClient.get<DashboardOverview>('/api/dashboard/overview');
    overview.value = data;
  } catch (err: any) {
    errorText.value = err?.response?.data?.detail || err?.message || t('legacy.failed_to_load_dashboard_data');
    overview.value = null;
  } finally {
    loading.value = false;
  }
}

function go(route: string) {
  router.push(route);
}

function formatNumber(value: number) {
  return new Intl.NumberFormat('zh-CN').format(Number(value || 0));
}

function formatCompact(value: number) {
  const amount = Number(value || 0);
  if (locale.value === 'en-US') {
    if (amount >= 1000000000) return `${(amount / 1000000000).toFixed(1)}B`;
    if (amount >= 1000000) return `${(amount / 1000000).toFixed(1)}M`;
    if (amount >= 1000) return `${(amount / 1000).toFixed(1)}K`;
    return formatNumber(amount);
  }
  if (amount >= 100000000) return `${(amount / 100000000).toFixed(1)} 亿`;
  if (amount >= 10000) return `${(amount / 10000).toFixed(1)} 万`;
  return formatNumber(amount);
}

function formatCost(value: number) {
  const amount = Number(value || 0);
  return amount > 0 && amount < 0.0001 ? amount.toFixed(8) : amount.toFixed(amount < 0.01 ? 4 : 2);
}

function formatCurrencyCosts(costs: Record<'CNY' | 'USD', number>, pricedCalls: Record<'CNY' | 'USD', number>) {
  const parts = (['CNY', 'USD'] as const)
    .filter((currency) => Number(costs?.[currency] || 0) > 0 || Number(pricedCalls?.[currency] || 0) > 0)
    .map((currency) => `${currency === 'CNY' ? '¥' : '$'}${formatCost(costs[currency])}`);
  return parts.length ? parts.join(' + ') : t('tokenStats.unpricedTotal');
}

function formatDuration(value: number) {
  const ms = Number(value || 0);
  if (!ms) return '—';
  if (ms < 1000) return `${ms}ms`;
  return `${(ms / 1000).toFixed(2)}s`;
}

function formatTime(value: string | null) {
  return formatAdminShortDateTime(value, t('legacy.none_5dbd015'));
}

onMounted(loadOverview);
</script>

<style scoped>
.dashboard-page {
  height: calc(100vh - 64px);
  overflow-y: auto;
  padding: 18px;
  background: #f4f7fb;
}

.side-stack {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.observation-grid {
  align-items: stretch;
}

.activity-panel,
.observation-grid .side-stack {
  height: clamp(380px, 38vh, 420px);
}

.activity-panel :deep(.n-card__content) {
  min-height: 0;
  overflow: hidden;
}

.todo-panel :deep(.n-card__content) {
  min-height: 0;
  overflow-y: auto;
}

.todo-panel {
  min-height: 0;
  flex: 1;
}

.todo-panel .empty-state.compact {
  min-height: 120px;
}

.deployment-card {
  padding: 14px 16px;
  border: 1px solid #dbe5f5;
  border-radius: 12px;
  background: linear-gradient(135deg, #ffffff 0%, #f5f8ff 100%);
  box-shadow: 0 8px 22px rgba(28, 55, 104, 0.06);
}

.deployment-head,
.deployment-title,
.deployment-facts {
  display: flex;
  align-items: center;
}

.deployment-head {
  justify-content: space-between;
  gap: 10px;
}

.deployment-title {
  min-width: 0;
  gap: 10px;
}

.deployment-title strong {
  overflow: hidden;
  color: #15213b;
  font-size: 14px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.deployment-status {
  display: flex;
  align-items: baseline;
  gap: 8px;
  margin-top: 9px;
}

.deployment-status strong {
  flex: 0 0 auto;
  color: #17366f;
  font-size: 13px;
}

.deployment-status span {
  overflow: hidden;
  color: #64748b;
  font-size: 12px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.deployment-facts {
  flex-wrap: wrap;
  gap: 6px 16px;
  margin-top: 10px;
  padding-top: 10px;
  border-top: 1px solid #e6edf7;
  color: #64748b;
  font-size: 12px;
}

.deployment-facts strong {
  color: #17366f;
}

.health-dot {
  flex: 0 0 auto;
  width: 9px;
  height: 9px;
  border-radius: 999px;
  background: #10b981;
  box-shadow: 0 0 0 4px rgba(16, 185, 129, 0.13);
}

.health-warning .health-dot {
  background: #f59e0b;
  box-shadow: 0 0 0 4px rgba(245, 158, 11, 0.14);
}

.health-critical .health-dot {
  background: #ef4444;
  box-shadow: 0 0 0 4px rgba(239, 68, 68, 0.13);
}

.metrics-grid {
  display: grid;
  grid-template-columns: repeat(6, minmax(0, 1fr));
  gap: 12px;
  margin-bottom: 14px;
}

.metric-card,
.asset-card,
.todo-item {
  transition: border-color 0.2s ease, background-color 0.2s ease, box-shadow 0.2s ease;
}

.metric-card {
  min-height: 132px;
  padding: 14px;
  border: 1px solid #dfe7f3;
  border-radius: 12px;
  background: #ffffff;
}

.metric-head {
  display: flex;
  align-items: center;
  gap: 8px;
  color: #64748b;
}

.metric-icon,
.button-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
}

.metric-icon {
  width: 30px;
  height: 30px;
  border-radius: 8px;
  background: #eef4ff;
  color: #2563eb;
}

.metric-icon :deep(svg),
.button-icon :deep(svg),
.empty-icon svg {
  width: 16px;
  height: 16px;
  stroke: currentColor;
  stroke-width: 2;
  stroke-linecap: round;
  stroke-linejoin: round;
}

.metric-label {
  font-size: 13px;
  font-weight: 700;
}

.metric-value {
  margin-top: 16px;
  color: #0f172a;
  font-size: 25px;
  font-weight: 800;
  line-height: 1.1;
}

.metric-note {
  margin-top: 8px;
  color: #64748b;
  font-size: 12px;
}

.content-grid {
  display: grid;
  grid-template-columns: repeat(12, minmax(0, 1fr));
  gap: 14px;
  margin-bottom: 14px;
}

.span-8 {
  grid-column: span 8;
}

.span-4 {
  grid-column: span 4;
}

.panel-card {
  border-radius: 12px;
  box-shadow: 0 8px 22px rgba(28, 55, 104, 0.06);
}

.panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  width: 100%;
}

.activity-table {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.table-row {
  display: grid;
  grid-template-columns: minmax(240px, 1fr) 150px 74px 88px 70px;
  gap: 12px;
  align-items: center;
  min-height: 54px;
  padding: 10px 8px;
  border-bottom: 1px solid #eef2f7;
  color: #1f2a44;
  font-size: 13px;
}

.table-head {
  min-height: 34px;
  color: #64748b;
  font-size: 12px;
  font-weight: 800;
}

.activity-main {
  min-width: 0;
}

.activity-main strong,
.activity-main small {
  display: block;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.activity-main strong {
  color: #13213d;
}

.activity-main small,
.table-muted {
  color: #64748b;
}

.table-model {
  display: block;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.todo-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.todo-item {
  display: grid;
  grid-template-columns: 10px minmax(0, 1fr) 18px;
  gap: 10px;
  align-items: center;
  width: 100%;
  padding: 12px;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  background: #ffffff;
  cursor: pointer;
  text-align: left;
}

.todo-item:hover,
.asset-card:hover {
  border-color: #9db8f8;
  background: #f8fbff;
  box-shadow: 0 8px 20px rgba(37, 99, 235, 0.08);
}

.todo-mark {
  width: 8px;
  height: 34px;
  border-radius: 999px;
  background: #3b82f6;
}

.todo-error {
  background: #ef4444;
}

.todo-warning {
  background: #f59e0b;
}

.todo-info {
  background: #3b82f6;
}

.todo-copy {
  min-width: 0;
}

.todo-copy strong,
.todo-copy small {
  display: block;
}

.todo-copy strong {
  color: #14213d;
  font-size: 13px;
}

.todo-copy small {
  margin-top: 2px;
  color: #64748b;
  font-size: 12px;
  line-height: 1.4;
}

.todo-arrow {
  color: #94a3b8;
  font-size: 20px;
}

.asset-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
}

.asset-card {
  min-height: 146px;
  padding: 14px;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  background: #ffffff;
  cursor: pointer;
  text-align: left;
}

.asset-title {
  color: #64748b;
  font-size: 13px;
  font-weight: 700;
}

.asset-value {
  margin-top: 10px;
  color: #0f172a;
  font-size: 30px;
  font-weight: 800;
  line-height: 1;
}

.asset-lines {
  display: flex;
  flex-direction: column;
  gap: 3px;
  margin-top: 14px;
  color: #64748b;
  font-size: 12px;
}

.quick-grid {
  display: grid;
  grid-template-columns: 1fr;
  gap: 10px;
}

.button-icon {
  width: 16px;
  height: 16px;
}

.empty-state {
  display: grid;
  place-items: center;
  min-height: 260px;
  padding: 30px;
  color: #64748b;
  text-align: center;
}

.empty-state.compact {
  min-height: 220px;
}

.empty-icon {
  display: grid;
  place-items: center;
  width: 46px;
  height: 46px;
  border-radius: 10px;
  background: #eef4ff;
  color: #2563eb;
}

.empty-title {
  margin-top: 12px;
  color: #17233f;
  font-size: 15px;
  font-weight: 800;
}

.empty-copy {
  max-width: 360px;
  margin-top: 6px;
  font-size: 13px;
  line-height: 1.5;
}

@media (max-width: 1400px) {
  .metrics-grid {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }

  .asset-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 900px) {
  .dashboard-page {
    height: auto;
    min-height: calc(100vh - 64px);
    padding: 12px;
  }

  .metrics-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .span-8,
  .span-4 {
    grid-column: 1 / -1;
  }

  .activity-panel,
  .observation-grid .side-stack {
    height: auto;
  }

  .activity-panel :deep(.n-card__content),
  .todo-panel :deep(.n-card__content) {
    overflow-y: visible;
  }

  .table-head {
    display: none;
  }

  .table-row {
    grid-template-columns: minmax(0, 1fr) auto;
  }

  .table-row > :nth-child(2),
  .table-row > :nth-child(4),
  .table-row > :nth-child(5) {
    display: none;
  }
}

@media (max-width: 520px) {
  .metrics-grid,
  .asset-grid {
    grid-template-columns: 1fr;
  }

  .deployment-status span {
    white-space: normal;
  }
}

@media (prefers-reduced-motion: reduce) {
  .metric-card,
  .asset-card,
  .todo-item {
    transition: none;
  }
}
</style>
