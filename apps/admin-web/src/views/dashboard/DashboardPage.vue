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
              <span>{{ t('最近运行观察') }}</span>
              <n-button quaternary size="small" @click="go('/token-stats')">{{ t('查看全部') }}</n-button>
            </div>
          </template>

          <div v-if="recentActivity.length" class="activity-table">
            <div class="table-row table-head">
              <span>{{ t('任务') }}</span>
              <span>{{ t('模型') }}</span>
              <span>{{ t('状态') }}</span>
              <span>{{ t('Token') }}</span>
              <span>{{ t('耗时') }}</span>
            </div>
            <div v-for="(item, index) in visibleRecentActivity" :key="item.requestId || item.sessionId || `activity-${index}`" class="table-row">
              <div class="activity-main">
                <strong>{{ item.title ? t(item.title) : t('LLM 调用') }}</strong>
                <small>{{ item.userName || t('未知用户') }} · {{ item.departmentName || t('未分配部门') }} · {{ formatTime(item.createdAt) }}</small>
              </div>
              <span class="table-muted table-model" :title="item.modelName || t('默认模型')">{{ item.modelName || t('默认模型') }}</span>
              <n-tag size="small" :type="item.status === 'failed' ? 'error' : 'success'" :bordered="false">
                {{ item.status === 'failed' ? t('失败') : t('完成') }}
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
            <div class="empty-title">{{ t('暂无运行记录') }}</div>
            <div class="empty-copy">{{ t('当前组织还没有 LLM 调用数据，产生调用后会在这里展示最近活动。') }}</div>
          </div>
        </n-card>

        <div class="span-4 side-stack">
          <section class="deployment-card" :class="`health-${healthStatus}`">
            <div class="deployment-head">
              <div class="deployment-title">
                <span class="health-dot" aria-hidden="true"></span>
                <strong>{{ overview?.billing.orgName || t('组织空间') }}</strong>
              </div>
              <n-tag size="small" :bordered="false" :type="isCommunity ? 'success' : 'info'">{{ tierLabel }}</n-tag>
            </div>
            <div class="deployment-status">
              <strong>{{ healthLabel }}</strong>
              <span>{{ healthNote }}</span>
            </div>
            <div class="deployment-facts">
              <span><strong>{{ overview?.billing.currentMembersCount ?? 0 }}</strong> {{ memberCapacityLabel }}</span>
              <span><strong>{{ overview?.billing.isOwnModel ? t('已开启') : t('未开启') }}</strong> {{ t('自有模型') }}</span>
            </div>
            <div v-if="canUpgradePro" class="deployment-upgrade">
              <span>{{ t('升级后最多 {count} 人', { count: proUserLimit }) }}</span>
              <n-button size="tiny" type="primary" secondary :loading="upgradingPro" @click="upgradeToPro">{{ t('升级专业版') }}</n-button>
            </div>
            <div v-if="pendingBillingOrder" class="billing-order-note">
              <strong>{{ t('支付订单已创建') }}</strong>
              <span>{{ pendingBillingOrder.planName }} · {{ pendingBillingOrder.amountText }}</span>
            </div>
          </section>

          <n-card class="panel-card todo-panel" :bordered="false" size="large">
            <template #header>
              <div class="panel-header">
                <span>{{ t('待处理事项') }}</span>
                <n-button quaternary size="small" @click="loadOverview">{{ t('刷新') }}</n-button>
              </div>
            </template>

            <div v-if="todos.length" class="todo-list">
              <button v-for="todo in todos" :key="todo.title" class="todo-item" type="button" @click="go(todo.route)">
                <span class="todo-mark" :class="`todo-${todo.level}`"></span>
                <span class="todo-copy">
                  <strong>{{ t(todo.title) }}</strong>
                  <small>{{ t(todo.description) }}</small>
                </span>
                <span class="todo-arrow">›</span>
              </button>
            </div>
            <div v-else class="empty-state compact">
              <div class="empty-title">{{ t('暂无待处理事项') }}</div>
              <div class="empty-copy">{{ t('模型、Skill、工具与近 24 小时运行状态未发现需要立即处理的问题。') }}</div>
            </div>
          </n-card>

        </div>
      </section>

      <section class="content-grid">
        <n-card class="panel-card span-8" :bordered="false" size="large">
          <template #header>{{ t('核心资产状态') }}</template>
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
          <template #header>{{ t('快捷操作') }}</template>
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
import { useMessage } from 'naive-ui';
import { useRouter } from 'vue-router';
import { apiClient } from '@/api/client';
import { t } from '@/composables/i18n';
import { formatAdminShortDateTime } from '@/composables/adminTimezone';

type HealthStatus = 'healthy' | 'warning' | 'critical';
type TodoLevel = 'error' | 'warning' | 'info';

interface BillingOrder {
  orderNo: string;
  planName: string;
  amountText: string;
  status: string;
  paymentUrl: string;
}

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
    cost24h: number;
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
const message = useMessage();
const overview = ref<DashboardOverview | null>(null);
const loading = ref(false);
const upgradingPro = ref(false);
const pendingBillingOrder = ref<BillingOrder | null>(null);
const errorText = ref('');

const emptyMetrics = {
  calls24h: 0,
  tokens24h: 0,
  cost24h: 0,
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
const tierLabel = computed(() => {
  if (isCommunity.value) return t('社区版');
  const tier = overview.value?.billing.tier;
  if (tier === 'plus') return t('Plus 个人版');
  if (tier === 'pro') return t('专业团队版');
  if (tier === 'enterprise') return t('企业定制版');
  return t('免费版');
});
const canUpgradePro = computed(() => {
  const tier = overview.value?.billing.tier;
  return Boolean(overview.value?.billing.billingEnabled) && tier !== 'pro' && tier !== 'enterprise';
});
const memberCapacityLabel = computed(() => {
  const limit = overview.value?.billing.userLimit;
  return limit === null || limit === undefined ? t('名成员 · 不限人数') : t(' / {count} 名成员', { count: limit });
});
const proUserLimit = 50;
const healthLabel = computed(() => {
  if (healthStatus.value === 'critical') return t('需要处理');
  if (healthStatus.value === 'warning') return t('有待确认');
  return t('运行正常');
});
const healthNote = computed(() => {
  const warnings = overview.value?.health.warnings || [];
  if (!warnings.length) return t('模型、工具与近 24 小时调用未发现明显异常');
  return warnings.slice(0, 2).map(w => t(w)).join('、');
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
    label: t('近 24h 调用'),
    value: formatNumber(metrics.value.calls24h),
    note: t('失败 {count} 次', { count: metrics.value.failedCalls24h }),
    icon: icons.calls,
  },
  {
    key: 'tokens',
    label: t('Token 消耗'),
    value: formatCompact(metrics.value.tokens24h),
    note: t('近 24 小时累计'),
    icon: icons.tokens,
  },
  {
    key: 'users',
    label: t('活跃用户'),
    value: formatNumber(metrics.value.activeUsers24h),
    note: t('{count} 个活跃部门', { count: metrics.value.activeDepartments24h }),
    icon: icons.users,
  },
  {
    key: 'success',
    label: t('成功率'),
    value: metrics.value.successRate24h === null ? '—' : `${metrics.value.successRate24h}%`,
    note: metrics.value.lastCalledAt ? t('最近 {time}', { time: formatTime(metrics.value.lastCalledAt) }) : t('暂无调用'),
    icon: icons.success,
  },
  {
    key: 'cost',
    label: t('近 24h 成本'),
    value: `¥${formatCost(metrics.value.cost24h)}`,
    note: t('按当前估算价计算'),
    icon: icons.cost,
  },
  {
    key: 'speed',
    label: t('平均耗时'),
    value: formatDuration(metrics.value.avgDurationMs24h),
    note: t('仅统计有起止时间的调用'),
    icon: icons.speed,
  },
]);

const assetCards = computed(() => {
  const current = assets.value;
  return [
    {
      key: 'models',
      title: t('模型中心'),
      value: current ? formatNumber(current.models.total) : '0',
      lines: current
        ? [t('企业模型') + ' ' + current.models.total, t('启用') + ' ' + current.models.active, t('异常') + ' ' + current.models.failedHealth]
        : [t('暂无数据')],
      route: '/models',
    },
    {
      key: 'skills',
      title: t('Skill管理'),
      value: current ? formatNumber(current.skills.total) : '0',
      lines: current
        ? [t('启用') + ' ' + current.skills.enabled, t('工作流') + ' ' + current.skills.workflow, t('写作规范') + ' ' + current.skills.writingStyle]
        : [t('暂无数据')],
      route: '/skills',
    },
    {
      key: 'tools',
      title: t('工具与 MCP'),
      value: current ? formatNumber(current.tools.total) : '0',
      lines: current
        ? [t('启用') + ' ' + current.tools.active, 'MCP ' + current.tools.mcp, t('失败') + ' ' + current.tools.failed + ' / ' + t('未设置') + ' ' + current.tools.untested]
        : [t('暂无数据')],
      route: '/tools',
    },
    {
      key: 'users',
      title: t('用户管理'),
      value: current ? formatNumber(current.users.total) : '0',
      lines: current ? [t('部门') + ' ' + current.users.departments, t('停用') + ' ' + current.users.disabled] : [t('暂无数据')],
      route: '/organizations/users',
    },
  ];
});

const quickActions = computed(() => [
  { label: t('新增模型'), route: '/models', icon: icons.plus },
  { label: t('添加 Skill'), route: '/skills', icon: icons.plus },
  { label: t('新增工具连接'), route: '/tools/new', icon: icons.plus },
  { label: t('用户管理'), route: '/organizations/users', icon: icons.users },
  { label: t('Token 统计'), route: '/token-stats', icon: icons.chart },
]);

async function loadOverview() {
  loading.value = true;
  errorText.value = '';
  try {
    const { data } = await apiClient.get<DashboardOverview>('/api/dashboard/overview');
    overview.value = data;
  } catch (err: any) {
    errorText.value = err?.response?.data?.detail || err?.message || t('工作台数据加载失败');
    overview.value = null;
  } finally {
    loading.value = false;
  }
}

async function upgradeToPro() {
  upgradingPro.value = true;
  try {
    const orderResponse = await apiClient.post('/api/organizations/billing/orders', {
      planCode: 'org_pro_monthly',
      paymentMethod: 'wechat_native',
    });
    const orderPayload = orderResponse.data;
    if (orderPayload?.code !== 0) {
      throw new Error(orderPayload?.message || t('创建支付订单失败'));
    }
    const order = orderPayload?.data?.order;
    pendingBillingOrder.value = order;
    message.success(`${t('支付订单已创建')}：${order.orderNo}`);
  } catch (error: any) {
    message.error(error?.message || t('创建支付订单失败'));
  } finally {
    upgradingPro.value = false;
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
  if (amount >= 100000000) return `${(amount / 100000000).toFixed(1)} 亿`;
  if (amount >= 10000) return `${(amount / 10000).toFixed(1)} 万`;
  return formatNumber(amount);
}

function formatCost(value: number) {
  return Number(value || 0).toFixed(2);
}

function formatDuration(value: number) {
  const ms = Number(value || 0);
  if (!ms) return '—';
  if (ms < 1000) return `${ms}ms`;
  return `${(ms / 1000).toFixed(2)}s`;
}

function formatTime(value: string | null) {
  return formatAdminShortDateTime(value, t('暂无'));
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
.deployment-facts,
.deployment-upgrade {
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

.deployment-upgrade {
  justify-content: space-between;
  gap: 10px;
  margin-top: 10px;
  color: #2563eb;
  font-size: 12px;
  font-weight: 600;
}

.billing-order-note {
  display: flex;
  flex-direction: column;
  gap: 4px;
  max-width: 560px;
  margin-top: 12px;
  padding: 10px 12px;
  border: 1px solid #bfdbfe;
  border-radius: 8px;
  background: #eff6ff;
  color: #1f3f73;
  font-size: 12px;
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
