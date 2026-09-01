<template>
  <n-page-header>
    <template #title>{{ title }}</template>
    <template #subtitle>{{ description }}</template>
    <template #extra>
      <n-space>
        <n-tag v-for="tag in tags" :key="tag" round>{{ tag }}</n-tag>
      </n-space>
    </template>
  </n-page-header>
</template>

<script setup lang="ts">
withDefaults(
  defineProps<{
    title: string;
    description: string;
    tags?: string[];
  }>(),
  {
    tags: () => [],
  },
);
</script>
