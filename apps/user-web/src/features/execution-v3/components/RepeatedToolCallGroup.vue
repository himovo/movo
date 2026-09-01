<script setup lang="ts">
import { computed, ref } from 'vue'
import type { ExecutionItemV3 } from '../domain/model'
import { toolCallSummary, toolCapabilityKeys, toolName } from '../domain/repeatedToolCalls'
import { t } from '../../../composables/i18n'
import ActivityIcon from './ActivityIcon.vue'

const props = defineProps<{ items: ExecutionItemV3[]; statusItems: ExecutionItemV3[] }>()
const expanded = ref(false)
const hasFailure = computed(() => props.statusItems.some(item => item.status === 'failed'))
const isRunning = computed(() => props.statusItems.some(item => item.status === 'running'))
const label = computed(() => toolCapabilityKeys(props.items).map(key => t(key)).join(t('execution.v3.activity_separator')))

function syncExpanded(event: Event) {
  expanded.value = Boolean((event.currentTarget as HTMLDetailsElement).open)
}
</script>

<template>
  <details class="repeated-tool-group" :open="expanded" @toggle="syncExpanded">
    <summary :class="{ failed: hasFailure, running: isRunning }">
      <ActivityIcon category="tool" kind="tool" />
      <span class="repeated-tool-label" :role="isRunning ? 'status' : undefined" :aria-label="isRunning ? `${label}${t('execution.v3.activity_separator')}${t('execution.v3.processing')}` : undefined">{{ label }}</span>
      <svg class="repeated-tool-chevron" viewBox="0 0 16 16" aria-hidden="true"><path d="m5 3 5 5-5 5" /></svg>
      <span v-if="hasFailure" class="repeated-tool-status">{{ t('execution.v3.repeated_failed') }}</span>
    </summary>
    <ol>
      <li v-for="item in items" :key="item.id" :class="`status-${item.status}`">
        <ActivityIcon category="tool" kind="tool" />
        <span class="tool-call-name">{{ toolName(item) }}</span>
        <span class="tool-call-summary">{{ toolCallSummary(item) || t('execution.v3.tool_call_without_arguments') }}</span>
        <span v-if="item.status === 'failed'" class="repeated-tool-error">{{ String(item.payload?.error || t('ui.failed')) }}</span>
      </li>
    </ol>
  </details>
</template>

<style scoped>
.repeated-tool-group { margin:1px 0; color:#64748b; font-size:13px; }
.repeated-tool-group summary { display:flex; min-height:32px; align-items:center; gap:8px; cursor:pointer; list-style:none; border-radius:6px; }
.repeated-tool-group summary::-webkit-details-marker { display:none; }
.repeated-tool-group summary:focus-visible { outline:2px solid #2563eb; outline-offset:2px; }
.repeated-tool-chevron { width:13px; height:13px; flex:none; fill:none; stroke:#94a3b8; stroke-width:1.8; stroke-linecap:round; stroke-linejoin:round; transition:transform .16s ease; }
.repeated-tool-group[open] .repeated-tool-chevron { transform:rotate(90deg); }
.repeated-tool-group summary.running { color:#2563eb; }
.repeated-tool-group summary.failed { color:#b45309; }
.repeated-tool-group summary.running .repeated-tool-label {
  color:transparent;
  background:linear-gradient(100deg,#2563eb 16%,#93c5fd 38%,#2563eb 60%);
  background-size:240% 100%;
  background-clip:text;
  -webkit-background-clip:text;
  animation:repeated-tool-sheen 1.7s linear infinite;
}
.repeated-tool-status { margin-left:auto; color:inherit; font-size:12px; }
.repeated-tool-group ol { display:flex; flex-direction:column; gap:2px; margin:3px 0 6px 28px; padding:2px 0 2px 12px; border-left:1px solid #e2e8f0; color:#64748b; font-size:12px; line-height:18px; }
.repeated-tool-group li { display:grid; grid-template-columns:18px minmax(96px,220px) minmax(0,1fr); align-items:center; column-gap:7px; min-height:26px; }
.repeated-tool-label { min-width:0; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.tool-call-name { min-width:0; overflow:hidden; color:#475569; font-weight:500; text-overflow:ellipsis; white-space:nowrap; }
.tool-call-summary { min-width:0; overflow:hidden; color:#94a3b8; text-overflow:ellipsis; white-space:nowrap; }
.repeated-tool-group li.status-failed { color:#b45309; }
.repeated-tool-error { grid-column:2 / -1; display:block; margin-top:1px; color:#b45309; }
@keyframes repeated-tool-sheen { from { background-position:100% 0; } to { background-position:-140% 0; } }
@media (max-width:640px) {
  .repeated-tool-group li { grid-template-columns:18px minmax(0,1fr); row-gap:1px; }
  .tool-call-summary { grid-column:2; }
  .repeated-tool-error { grid-column:2; }
}
@media (prefers-reduced-motion: reduce) { .repeated-tool-chevron { transition:none; } .repeated-tool-group summary.running .repeated-tool-label { color:#2563eb; background:none; animation:none; } }
</style>
