<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { NButton, NInput, NSelect } from 'naive-ui'

import { fetchOrgBilling } from '../api/auth'
import { listTokenUsage, type TokenUsageItem, type TokenUsageSummary } from '../api/tokenUsage'
import { t, useLocale } from '../composables/i18n'
import { formatAppShortDateTime } from '../composables/appTimezone'
import { formatQuotaUsagePercent, formatTokenAmount, quotaUsagePercent } from '../utils/tokenNumberFormat'

const props = defineProps<{
  userId?: string | null
  mainId?: string | null
  token?: string
}>()

const emit = defineEmits<{
  (e: 'back'): void
}>()

const { locale } = useLocale()

const loading = ref(false)
const query = ref('')
const status = ref('')
const items = ref<TokenUsageItem[]>([])
const total = ref(0)
const offset = ref(0)
const limit = 10
const billing = ref<any>(null)
const summary = ref<TokenUsageSummary>({
  total_calls: 0,
  internal_calls: 0,
  total_tokens: 0,
  prompt_tokens: 0,
  completion_tokens: 0,
  avg_tokens: 0,
  last_called_at: null,
  last_24h_calls: 0,
  last_24h_internal_calls: 0,
  last_24h_tokens: 0,
  top_models: [],
})

const statusOptions = computed(() => [
  { label: t('usage.filters.all_status'), value: '' },
  { label: t('usage.status.completed'), value: 'completed' },
  { label: t('usage.status.user_cancelled'), value: 'user_cancelled' },
  { label: t('usage.status.runtime_error'), value: 'runtime_error' },
  { label: t('usage.status.network_error'), value: 'network_error' },
])

const pageStart = computed(() => (items.value.length ? offset.value + 1 : 0))
const pageEnd = computed(() => offset.value + items.value.length)
const remainingTokens = computed(() => Number(billing.value?.remainingPoints || 0))
const totalQuota = computed(() => Number(billing.value?.totalPoints || 0))
const usedPercent = computed(() => {
  return quotaUsagePercent(Number(billing.value?.usedPoints || 0), totalQuota.value)
})
const usedPercentLabel = computed(() => formatQuotaUsagePercent(Number(billing.value?.usedPoints || 0), totalQuota.value))
const primaryModel = computed(() => summary.value.top_models[0]?.model_name || t('usage.default_model'))
const internalRequestTitles = new Set(['意图路由', 'LLM 调用', 'LLM_Call', '任务规划', '内容生成', '任务执行'])

async function loadBilling() {
  if (!props.token) return
  const result = await fetchOrgBilling(props.token)
  if (result.ok) billing.value = result.data
}

async function loadPage(nextOffset = 0) {
  if (!props.userId || !props.token) return
  loading.value = true
  try {
    const page = await listTokenUsage(props.userId, {
      mainId: props.mainId || undefined,
      limit,
      offset: nextOffset,
      q: query.value.trim(),
      status: status.value,
      token: props.token,
    })
    items.value = page.items
    total.value = page.total
    offset.value = page.offset
    summary.value = page.summary
  } finally {
    loading.value = false
  }
}

function goPrev() {
  if (offset.value <= 0) return
  loadPage(Math.max(offset.value - limit, 0))
}

function goNext() {
  if (offset.value + items.value.length >= total.value) return
  loadPage(offset.value + limit)
}

function formatNumber(value: number) {
  return new Intl.NumberFormat('zh-CN').format(Number(value || 0))
}

function formatCompact(value: number) {
  return formatTokenAmount(value, locale.value)
}

function formatDate(value?: string | null) {
  return formatAppShortDateTime(value, '—')
}

function formatPrompt(prompt: string) {
  const text = String(prompt || '').replace(/\s+/g, ' ').trim()
  if (!text) return t('usage.empty_prompt')
  return text
}

function requestTitle(item: TokenUsageItem) {
  const title = String(item.request_title_zh || item.request_title_en || '').trim()
  if (title && !internalRequestTitles.has(title)) return title
  return formatPrompt(item.prompt)
}

function modelText(item: TokenUsageItem) {
  const models = Array.isArray(item.model_names) ? item.model_names.filter(Boolean) : []
  if (models.length > 1) return t('usage.model_others_format', { first: models[0], count: models.length })
  return item.model_name || models[0] || t('usage.default_model')
}

function rowKey(item: TokenUsageItem) {
  return item.user_request_id || item.trace_id || item.request_id
}

function statusText(value: string) {
  if (value === 'completed') return t('usage.status.completed')
  if (value === 'user_cancelled') return t('usage.status.user_cancelled')
  if (value === 'runtime_error' || value === 'failed') return t('usage.status.runtime_error')
  if (value === 'network_error') return t('usage.status.network_error')
  return value || t('usage.status.completed')
}

function statusClass(value: string) {
  if (value === 'completed') return 'bg-emerald-50 text-emerald-600'
  if (value === 'user_cancelled') return 'bg-amber-50 text-amber-600'
  return 'bg-rose-50 text-rose-600'
}

watch([query, status], () => {
  loadPage(0).catch(() => {})
})

watch(
  () => [props.userId, props.mainId, props.token],
  () => {
    if (props.userId && props.token) {
      loadPage(0).catch(() => {})
      loadBilling().catch(() => {})
    }
  },
)

onMounted(() => {
  if (props.userId && props.token) {
    loadPage(0).catch(() => {})
    loadBilling().catch(() => {})
  }
})
</script>

<template>
  <div class="usage-page">
    <header class="usage-header">
      <div class="min-w-0">
        <h1>{{ t('usage.title') }}</h1>
        <p>{{ t('usage.header_desc') }}</p>
      </div>
      <div class="usage-header-actions">
        <span class="usage-updated">{{ t('usage.last_updated', { time: formatDate(summary.last_called_at) }) }}</span>
        <n-button secondary @click="emit('back')">{{ t('skills.back_to_chat') }}</n-button>
      </div>
    </header>

    <div class="usage-content">
      <div class="shrink-0 overflow-x-auto pb-1">
        <div class="flex gap-3" style="min-width: 980px">
        <div class="flex-1 rounded-2xl border border-slate-200 bg-white p-4 shadow-[0_10px_30px_rgba(15,23,42,0.05)]">
          <div class="flex items-center justify-between gap-3">
            <div class="flex items-center gap-2 text-xs font-semibold text-slate-500">
              <span class="inline-flex h-7 w-7 items-center justify-center rounded-lg bg-blue-50 text-blue-600">
                <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><path d="M4 7.5A2.5 2.5 0 0 1 6.5 5H18a2 2 0 0 1 2 2v10.5a2.5 2.5 0 0 1-2.5 2.5h-11A2.5 2.5 0 0 1 4 17.5v-10Z"/><path d="M16 12h4v4h-4a2 2 0 0 1 0-4Z"/><path d="M7 5V4a2 2 0 0 1 2-2h7"/></svg>
              </span>
              {{ t('ui.quota_remaining') }}
            </div>
            <div class="text-xs text-slate-400">{{ t('usage.used_percent_format', { percent: usedPercentLabel }) }}</div>
          </div>
          <div class="mt-3 text-2xl font-semibold text-slate-900">{{ totalQuota ? formatTokenAmount(remainingTokens, locale) : '—' }}</div>
          <div class="mt-3 h-1.5 overflow-hidden rounded-full bg-slate-100">
            <div class="h-full rounded-full bg-blue-600" :style="{ width: `${usedPercent}%` }"></div>
          </div>
        </div>

        <div class="flex-1 rounded-2xl border border-slate-200 bg-white p-4 shadow-[0_10px_30px_rgba(15,23,42,0.05)]">
          <div class="flex items-center gap-2 text-xs font-semibold text-slate-500">
            <span class="inline-flex h-7 w-7 items-center justify-center rounded-lg bg-indigo-50 text-indigo-600">
              <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><path d="M4 19V5"/><path d="M4 19h16"/><rect x="7" y="11" width="3" height="5" rx="1"/><rect x="12" y="7" width="3" height="9" rx="1"/><rect x="17" y="9" width="3" height="7" rx="1"/></svg>
            </span>
            {{ t('usage.burn_title') }}
          </div>
          <div class="mt-3 text-2xl font-semibold text-slate-900">{{ formatCompact(summary.total_tokens) }}</div>
          <div class="mt-2 text-xs text-slate-500">{{ t('usage.requests_count', { count: formatNumber(summary.total_calls) }) }}</div>
        </div>

        <div class="flex-1 rounded-2xl border border-slate-200 bg-white p-4 shadow-[0_10px_30px_rgba(15,23,42,0.05)]">
          <div class="flex items-center gap-2 text-xs font-semibold text-slate-500">
            <span class="inline-flex h-7 w-7 items-center justify-center rounded-lg bg-cyan-50 text-cyan-600">
              <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><path d="M7 7h11"/><path d="m15 4 3 3-3 3"/><path d="M17 17H6"/><path d="m9 14-3 3 3 3"/></svg>
            </span>
            {{ t('usage.input_output_title') }}
          </div>
          <div class="mt-3 flex items-baseline gap-2">
            <div class="text-2xl font-semibold text-slate-900">{{ formatCompact(summary.prompt_tokens) }}</div>
            <div class="text-xs text-slate-400">/ {{ formatCompact(summary.completion_tokens) }}</div>
          </div>
          <div class="mt-2 text-xs text-slate-500">{{ t('usage.input_output_desc') }}</div>
        </div>

        <div class="flex-1 rounded-2xl border border-slate-200 bg-white p-4 shadow-[0_10px_30px_rgba(15,23,42,0.05)]">
          <div class="flex items-center gap-2 text-xs font-semibold text-slate-500">
            <span class="inline-flex h-7 w-7 items-center justify-center rounded-lg bg-amber-50 text-amber-600">
              <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="8"/><path d="M12 7v5l3 2"/><path d="M5 5.5 3.5 4"/><path d="M19 5.5 20.5 4"/></svg>
            </span>
            {{ t('usage.summary.last_24h') }}
          </div>
          <div class="mt-3 text-2xl font-semibold text-slate-900">{{ formatCompact(summary.last_24h_tokens) }}</div>
          <div class="mt-2 text-xs text-slate-500">{{ t('usage.last_24h_summary_format', { requests: formatNumber(summary.last_24h_calls), calls: formatNumber(summary.last_24h_internal_calls) }) }}</div>
        </div>

        <div class="flex-1 rounded-2xl border border-slate-200 bg-slate-900 p-4 text-white shadow-[0_14px_40px_rgba(15,23,42,0.16)]">
          <div class="flex items-center gap-2 text-xs font-semibold text-slate-400">
            <span class="inline-flex h-7 w-7 items-center justify-center rounded-lg bg-white/10 text-white">
              <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><rect x="7" y="7" width="10" height="10" rx="2"/><path d="M10 3v4"/><path d="M14 3v4"/><path d="M10 17v4"/><path d="M14 17v4"/><path d="M3 10h4"/><path d="M3 14h4"/><path d="M17 10h4"/><path d="M17 14h4"/></svg>
            </span>
            {{ t('usage.primary_model_title') }}
          </div>
          <div class="mt-3 truncate text-lg font-semibold">{{ primaryModel }}</div>
          <div class="mt-2 text-xs text-slate-400">{{ t('usage.total_model_calls_format', { count: formatNumber(summary.internal_calls) }) }}</div>
        </div>
        </div>
      </div>

      <div class="usage-list-card mt-4 flex min-h-0 flex-1 flex-col overflow-hidden bg-white">
        <div class="shrink-0 flex flex-wrap items-center justify-between gap-3 border-b border-slate-100 px-5 py-3">
          <div>
            <div class="flex items-center gap-2 text-base font-semibold text-slate-900">
              <span class="inline-flex h-8 w-8 items-center justify-center rounded-lg bg-slate-100 text-slate-600">
                <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4" viewBox="0 0 512 512" fill="currentColor"><path d="M80 96h352v48H80V96zm0 136h352v48H80v-48zm0 136h224v48H80v-48z"/></svg>
              </span>
              {{ t('usage.table.title') }}
            </div>
            <div class="mt-1 text-xs text-slate-500">{{ t('usage.table.desc') }}</div>
          </div>
          <div class="flex max-w-full flex-nowrap items-center gap-2 overflow-x-auto pb-1">
            <div class="w-[260px] shrink-0">
              <n-input v-model:value="query" clearable :placeholder="t('usage.search_requests_placeholder')" />
            </div>
            <div class="w-[136px] shrink-0">
              <n-select v-model:value="status" :options="statusOptions" />
            </div>
          </div>
        </div>

        <div class="min-h-0 flex-1 overflow-auto custom-scrollbar">
          <table class="min-w-[1040px] w-full table-fixed border-collapse">
            <colgroup>
              <col style="width: 40%" />
              <col style="width: 9%" />
              <col style="width: 14%" />
              <col style="width: 13%" />
              <col style="width: 11%" />
              <col style="width: 13%" />
            </colgroup>
            <thead class="sticky top-0 z-10 bg-slate-50/95 text-xs font-semibold text-slate-500 backdrop-blur">
              <tr class="border-b border-slate-100">
                <th class="px-5 py-3 text-left">{{ t('usage.columns.request') }}</th>
                <th class="px-4 py-3 text-left">{{ t('usage.columns.status') }}</th>
                <th class="px-4 py-3 text-left">{{ t('usage.columns.model') }}</th>
                <th class="px-4 py-3 text-left">{{ t('usage.columns.tokens') }}</th>
                <th class="px-4 py-3 text-left">{{ t('usage.columns.calls_count') }}</th>
                <th class="px-4 py-3 text-left">{{ t('usage.columns.time') }}</th>
              </tr>
            </thead>
            <tbody v-if="!loading && items.length" class="divide-y divide-slate-100 bg-white">
              <tr v-for="item in items" :key="rowKey(item)" class="align-top transition-colors hover:bg-slate-50/80">
                <td class="px-5 py-3.5">
                  <div class="line-clamp-2 break-words text-sm font-medium leading-5 text-slate-900">{{ requestTitle(item) }}</div>
                </td>
                <td class="px-4 py-3.5">
                  <span
                    class="inline-flex rounded-full px-2.5 py-1 text-xs font-semibold"
                    :class="statusClass(item.status)"
                  >
                    {{ statusText(item.status) }}
                  </span>
                </td>
                <td class="px-4 py-3.5">
                  <div class="truncate text-sm text-slate-700">{{ modelText(item) }}</div>
                </td>
                <td class="px-4 py-3.5">
                  <div class="text-sm font-semibold text-slate-900">{{ formatNumber(item.total_tokens) }}</div>
                  <div class="mt-1 text-xs text-slate-400">{{ t('usage.prompt_completion_format', { prompt: formatCompact(item.prompt_tokens), completion: formatCompact(item.completion_tokens) }) }}</div>
                </td>
                <td class="px-4 py-3.5 text-sm font-medium text-slate-700">{{ t('usage.calls_unit', { count: formatNumber(item.calls || 1) }) }}</td>
                <td class="px-4 py-3.5 text-sm text-slate-500">{{ formatDate(item.updated_at || item.created_at) }}</td>
              </tr>
            </tbody>
          </table>
          <div v-if="loading" class="px-5 py-14 text-center text-sm italic text-slate-400">{{ t('ui.loading') }}</div>
          <div v-else-if="!items.length" class="px-5 py-14 text-center text-sm italic text-slate-400">{{ t('usage.empty') }}</div>
        </div>

        <div class="shrink-0 flex flex-wrap items-center justify-between gap-4 border-t border-slate-100 px-5 py-3">
          <div class="text-sm text-slate-500">
            {{ t('usage.pagination.range', { start: String(pageStart), end: String(pageEnd), total: formatNumber(total) }) }}
          </div>
          <div class="flex items-center gap-2">
            <button
              class="rounded-full border border-slate-200 px-4 py-2 text-sm font-medium text-slate-600 transition-colors hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-40"
              :disabled="offset <= 0 || loading"
              @click="goPrev"
            >
              {{ t('usage.pagination.prev') }}
            </button>
            <button
              class="rounded-full border border-slate-200 px-4 py-2 text-sm font-medium text-slate-600 transition-colors hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-40"
              :disabled="pageEnd >= total || loading"
              @click="goNext"
            >
              {{ t('usage.pagination.next') }}
            </button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.usage-page {
  height: 100%;
  min-height: 0;
  display: flex;
  flex-direction: column;
  gap: 16px;
  overflow: hidden;
  padding-top: 12px;
  background: #f6f8fc;
}

.usage-header {
  width: calc(100% - 24px);
  margin: 0 12px;
  padding: 14px 18px;
  border: 1px solid #e6ebf5;
  border-radius: 8px;
  background: #fff;
  box-shadow: 0 4px 12px rgba(29, 54, 110, 0.04);
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}

.usage-header h1 {
  margin: 0;
  color: #101c3d;
  font-size: 20px;
  line-height: 1.2;
  font-weight: 800;
}

.usage-header p {
  margin: 4px 0 0;
  color: #65748c;
  font-size: 13px;
}

.usage-header-actions {
  display: flex;
  align-items: center;
  gap: 14px;
  flex-shrink: 0;
}

.usage-updated {
  color: #7a8797;
  font-size: 12px;
  white-space: nowrap;
}

.usage-content {
  min-height: 0;
  flex: 1;
  display: flex;
  flex-direction: column;
  padding: 0 12px 12px;
}

.usage-list-card {
  border: 1px solid #e6ebf5;
  border-radius: 8px;
  box-shadow: 0 6px 20px rgba(16, 38, 84, 0.05);
}

@media (max-width: 768px) {
  .usage-header {
    align-items: flex-start;
  }

  .usage-header-actions {
    gap: 8px;
  }

  .usage-updated {
    display: none;
  }
}
</style>
