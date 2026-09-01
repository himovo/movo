<script setup lang="ts">
import type { ExecutionItemV3 } from '../domain/model'
import AssistantMarkdown from '../../../components/chat/AssistantMarkdown.vue'

defineProps<{ item: ExecutionItemV3 }>()
</script>

<template>
  <AssistantMarkdown
    v-if="String(item.payload?.text || '').trim()"
    class="provisional-assistant-copy"
    :content="String(item.payload?.text || '')"
    compact
  />
</template>

<style scoped>
.provisional-assistant-copy {
  margin: 5px 0 8px;
  color: #27364a;
}
</style>
