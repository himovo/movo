<template>
  <n-card :bordered="false" size="large">
    <div class="metric-head">
      <span class="shell-card-title">{{ title }}</span>
      <n-tag size="small" :type="tagType">{{ trend }}</n-tag>
    </div>
    <div class="metric-value">{{ value }}</div>
    <div class="stat-footnote">{{ footnote }}</div>
  </n-card>
</template>

<script setup lang="ts">
withDefaults(
  defineProps<{
    title: string;
    value: string;
    footnote: string;
    trend?: string;
    tagType?: 'default' | 'success' | 'warning' | 'error' | 'info';
  }>(),
  {
    trend: '稳定',
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
