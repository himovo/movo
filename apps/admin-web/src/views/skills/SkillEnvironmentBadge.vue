<template>
  <span v-if="status" class="environment-badge" @click.stop>
    <n-tag size="small" :bordered="false" :type="status === 'ready' ? 'success' : status === 'failed' ? 'error' : 'warning'">
      <span v-if="status === 'preparing'" class="environment-spinner" aria-hidden="true" />
      {{ t(`skillDeps.status.${status}`) }}
    </n-tag>
    <n-button v-if="status === 'failed' || status === 'unavailable'" size="tiny" text type="primary" :loading="busy" @click.stop="emit('retry')">
      {{ t('skillDeps.retry') }}
    </n-button>
    <n-button size="tiny" text type="primary" :title="t('skillDeps.records.open')" :aria-label="t('skillDeps.records.open')" @click.stop="emit('records')">
      <svg class="records-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><path d="M8 4h9a2 2 0 0 1 2 2v14H8a3 3 0 0 1-3-3V7a3 3 0 0 1 3-3Z"/><path d="M8 4v13a3 3 0 0 0-3 0M10 9h6M10 13h6"/></svg>
    </n-button>
  </span>
</template>

<script setup lang="ts">
import { NButton, NTag } from 'naive-ui'
import { t } from '@/composables/i18n'

defineProps<{ status?: string | null; busy?: boolean }>()
const emit = defineEmits<{ retry: []; records: [] }>()
</script>

<style scoped>
.environment-badge { display: flex; align-items: center; gap: 6px; min-height: 22px; margin: 0 0 8px; }
.environment-spinner { display: inline-block; width: 11px; height: 11px; margin-right: 4px; border: 2px solid currentColor; border-right-color: transparent; border-radius: 50%; vertical-align: -1px; animation: environment-spin .8s linear infinite; }
.records-icon { width: 16px; height: 16px; }
@keyframes environment-spin { to { transform: rotate(360deg); } }
@media (prefers-reduced-motion: reduce) { .environment-spinner { animation: none; } }
</style>
