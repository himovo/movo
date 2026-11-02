<script setup lang="ts">
import type { KnowledgeReference } from '../../../api/knowledgeReferences'
import { t } from '../../../composables/i18n'
defineProps<{ items: KnowledgeReference[]; removable?: boolean }>()
defineEmits<{ remove: [item: KnowledgeReference] }>()
</script>
<template><div v-if="items.length" class="knowledge-references"><span v-for="item in items" :key="`${item.scope}:${item.kind}:${item.source_id}`" :title="item.path || item.name"><small>{{ t(`knowledgeMention.${item.scope}`) }} · {{ t(`knowledgeMention.${item.kind}`) }}</small><strong>{{ item.name }}</strong><button v-if="removable" type="button" :aria-label="t('knowledgeMention.remove')" @click="$emit('remove', item)">×</button></span></div></template>
<style scoped>
.knowledge-references{display:flex;flex-wrap:wrap;gap:6px;margin:8px 0}.knowledge-references>span{display:inline-flex;align-items:center;gap:7px;max-width:100%;padding:6px 9px;border:1px solid #cbdcf5;background:#eff6ff;border-radius:8px;font-size:12px;color:#1e40af}small{font-size:10px;color:#64748b;white-space:nowrap}strong{font-weight:500;min-width:0;overflow:hidden;white-space:nowrap;text-overflow:ellipsis}button{border:0;background:transparent;font:inherit;cursor:pointer;color:inherit}
:global(html.theme-dark .knowledge-references>span){background:#1b2b47;border-color:#334a70;color:#bfdbfe}
</style>
