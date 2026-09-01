<script setup lang="ts">
import type { ExecutionItemV3 } from '../domain/model'

defineProps<{ item: ExecutionItemV3 }>()
</script>

<template>
  <p v-if="String(item.payload?.text || '').trim()" class="commentary-copy">{{ item.payload.text }}</p>
</template>

<style scoped>
.commentary-copy { margin:5px 0 8px; color:#27364a; font-size:14px; line-height:1.72; white-space:pre-wrap; overflow-wrap:anywhere; }
</style>
