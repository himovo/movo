<script setup lang="ts">
import type { KnowledgeReference, KnowledgeScope } from '../../../api/knowledgeReferences'
import { t } from '../../../composables/i18n'
defineProps<{ items: KnowledgeReference[]; scope: KnowledgeScope; loading: boolean; failed: boolean; active: number; hasMore: boolean; trail: Array<{ id: string; name: string }> }>()
defineEmits<{ scope: [value: KnowledgeScope]; select: [item: KnowledgeReference]; browse: [item: KnowledgeReference]; back: []; more: []; retry: []; close: [] }>()
</script>
<template>
  <section class="knowledge-picker" :aria-label="t('knowledgeMention.title')">
    <header><div><button v-for="value in (['personal', 'organization'] as const)" :key="value" type="button" :class="{ active: scope === value }" @click="$emit('scope', value)">{{ t(`knowledgeMention.${value}`) }}</button></div><button type="button" :aria-label="t('ui.close')" @click="$emit('close')">×</button></header>
    <div v-if="trail.length" class="breadcrumb"><button type="button" @click="$emit('back')">← {{ t('knowledgeMention.back') }}</button><span>{{ trail.map(item => item.name).join(' / ') }}</span></div>
    <div class="results" role="listbox" :aria-label="t('knowledgeMention.title')">
      <div v-for="(item, index) in items" :key="`${item.scope}:${item.kind}:${item.source_id}`" class="result" :class="{ focused: index === active }">
        <button type="button" role="option" :aria-selected="index === active" @click="$emit('select', item)"><span class="kind">{{ t(`knowledgeMention.${item.kind}`) }}</span><span class="name"><strong>{{ item.name }}</strong><small>{{ item.path }}</small></span></button>
        <button v-if="item.kind === 'directory'" type="button" class="browse" @click="$emit('browse', item)">{{ t('knowledgeMention.browse') }} →</button>
      </div>
      <p v-if="loading" role="status">{{ t('knowledgeMention.loading') }}</p><p v-else-if="failed" role="alert">{{ t('knowledgeMention.failed') }} <button type="button" @click="$emit('retry')">{{ t('knowledgeMention.retry') }}</button></p><p v-else-if="!items.length">{{ t('knowledgeMention.empty') }}</p>
      <button v-if="hasMore && !loading" type="button" class="more" @click="$emit('more')">{{ t('knowledgeMention.more') }}</button>
    </div>
    <footer>{{ t('knowledgeMention.hint') }}</footer>
  </section>
</template>
<style scoped>
.knowledge-picker{position:absolute;bottom:100%;left:0;right:0;z-index:30;margin-bottom:8px;border:1px solid #dce4ef;border-radius:14px;background:#fff;box-shadow:0 12px 32px #172a4d20;overflow:hidden;color:#1e293b}header{display:flex;justify-content:space-between;align-items:center;padding:8px 12px;border-bottom:1px solid #e8edf4}button{font:inherit;cursor:pointer;background:transparent;border:0;color:inherit}header button{padding:6px 10px;border-radius:7px}header .active{background:#eaf1ff;color:#2563eb}.results{max-height:280px;overflow:auto}.result{display:flex;align-items:center;padding:4px 10px}.result.focused,.result:hover{background:#f1f5fc}.result>button:first-child{display:flex;align-items:center;gap:10px;text-align:left;min-width:0;flex:1;padding:8px}.kind{font-size:11px;color:#64748b;flex:none}.name{display:grid;gap:3px;min-width:0}.name strong,.name small{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.name strong{font-size:13px}.name small{font-size:11px;color:#64748b}.browse{font-size:12px;color:#2563eb;flex:none}p,footer{padding:10px 14px;font-size:12px;color:#64748b;margin:0}footer{border-top:1px solid #e8edf4}.breadcrumb{display:flex;gap:12px;padding:8px 14px;font-size:12px}.breadcrumb span{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.more{width:100%;padding:10px;color:#2563eb}
:global(html.theme-dark .knowledge-picker){background:#162033;color:#e2e8f0;border-color:#334155}:global(html.theme-dark .knowledge-picker .result.focused),:global(html.theme-dark .knowledge-picker .result:hover){background:#243249}
</style>
