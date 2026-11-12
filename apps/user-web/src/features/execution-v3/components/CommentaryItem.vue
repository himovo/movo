<script setup lang="ts">
import type { ExecutionItemV3 } from '../domain/model'
import AssistantMarkdown from '../../../components/chat/AssistantMarkdown.vue'

defineProps<{ item: ExecutionItemV3 }>()
</script>

<template>
  <AssistantMarkdown
    v-if="String(item.payload?.text || '').trim()"
    class="commentary-copy"
    :content="String(item.payload?.text || '')"
    compact
  />
</template>

<style scoped>
.commentary-copy { margin:3px 0 2px; color:#27364a; font-size:14px; line-height:1.72; overflow-wrap:anywhere; }
</style>
