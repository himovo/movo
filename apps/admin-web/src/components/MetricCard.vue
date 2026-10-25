<template>
  <n-card :bordered="false" size="large">
    <div class="metric-head">
      <span class="shell-card-title">{{ title }}</span>
      <n-tag size="small" :type="tagType">{{ trend || t('legacy.stable') }}</n-tag>
    </div>
    <div class="metric-value">{{ value }}</div>
    <div class="stat-footnote">{{ footnote }}</div>
  </n-card>
</template>

<script setup lang="ts">
import { t } from '@/composables/i18n';

withDefaults(
  defineProps<{
    title: string;
    value: string;
    footnote: string;
    trend?: string;
    tagType?: 'default' | 'success' | 'warning' | 'error' | 'info';
  }>(),
  {
    trend: '',
    tagType: 'info',
  },
);
</script>

<style scoped>
.metric-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 14px;
}

.metric-value {
  font-size: 30px;
  font-weight: 800;
  line-height: 1.1;
  margin-bottom: 8px;
}
</style>
