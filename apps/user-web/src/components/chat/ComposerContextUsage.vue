<script setup lang="ts">
import { computed } from 'vue'
import { NPopover } from 'naive-ui'
import type { ContextUsage } from '../../api/contextUsage'
import { t, useLocale } from '../../composables/i18n'

const props = defineProps<{ usage: ContextUsage | null; loading?: boolean; selectedModelId?: string }>()
const emit = defineEmits<{ refresh: [] }>()
const { locale } = useLocale()
const capacity = computed(() => props.usage?.capacityTokens || null)
const used = computed(() => props.usage?.available ? props.usage.usedTokens ?? null : null)
const ratio = computed(() => capacity.value && used.value !== null ? used.value / capacity.value : null)
const percent = computed(() => ratio.value === null ? null : Math.round(ratio.value * 100))
const remaining = computed(() => percent.value === null ? null : Math.max(0, 100 - percent.value))
const formatter = computed(() => new Intl.NumberFormat(locale.value === 'zh' ? 'zh-CN' : 'en-US', {
  notation: 'compact', maximumFractionDigits: 1,
}))
const tokens = (value: number) => formatter.value.format(value)
const differentModel = computed(() => props.usage?.modelName && props.selectedModelId
  && props.usage.modelInstanceId !== props.selectedModelId)
const unavailable = computed(() => t(props.usage?.reason === 'no_runtime_session'
  ? 'context.noRuntimeHistory' : 'context.usageUnavailable'))
</script>

<template>
  <span v-if="loading" class="context-usage-loading flex h-8 w-8 items-center justify-center" role="status" :aria-label="t('context.loading')" aria-busy="true">
    <span class="h-2 w-6 animate-pulse rounded-full bg-slate-200 dark:bg-slate-700" aria-hidden="true" />
  </span>
  <n-popover v-else-if="usage?.available" trigger="hover" placement="top" :show-arrow="false" :style="{ padding: '12px 18px', borderRadius: '14px', background: '#202324', color: '#f8fafc' }" @update:show="show => show && emit('refresh')">
    <template #trigger>
      <span role="img"
        :aria-label="percent === null ? t('context.window') : t('context.usedPercent', { used: percent, remaining: remaining ?? 0 })"
        class="flex h-8 w-8 cursor-help items-center justify-center text-slate-500">
        <svg class="h-[18px] w-[18px]" :class="{ 'animate-spin': usage?.compacting }" viewBox="0 0 24 24" fill="none" aria-hidden="true">
          <circle cx="12" cy="12" r="9" stroke="currentColor" stroke-width="3" opacity=".2" />
          <circle v-if="ratio !== null" cx="12" cy="12" r="9" stroke="currentColor" stroke-width="3" stroke-linecap="round"
            :stroke-dasharray="`${Math.min(1, Math.max(0, ratio)) * 56.55} 56.55`" transform="rotate(-90 12 12)" />
        </svg>
      </span>
    </template>
    <div class="context-usage-details">
      <div class="context-usage-title">{{ t('context.window') }}</div>
      <div v-if="percent !== null">{{ t('context.usedPercent', { used: percent, remaining: remaining ?? 0 }) }}</div>
      <div v-if="used !== null">
        {{ t(usage?.estimated ? 'context.estimatedUsedTokens' : 'context.usedTokens', { used: tokens(used) }) }}<template v-if="capacity"> · {{ t('context.totalTokens', { capacity: tokens(capacity) }) }}</template>
      </div>
      <div v-if="used !== null && !capacity" class="context-usage-note">{{ t('context.capacityMissing') }}</div>
      <div v-if="used === null" class="context-usage-note">{{ unavailable }}</div>
      <div v-if="differentModel" class="context-usage-note">{{ t('context.measuredModel', { model: usage?.modelName || '' }) }}</div>
      <div v-if="usage?.compacting" class="context-usage-note">{{ t('context.compacting') }}</div>
    </div>
  </n-popover>
</template>

<style scoped>
.context-usage-details {
  max-width: 300px;
  text-align: center;
  font-size: 13px;
  line-height: 1.7;
  font-variant-numeric: tabular-nums;
}
.context-usage-title,
.context-usage-note {
  color: #b8babb;
  font-size: 12px;
}
</style>
