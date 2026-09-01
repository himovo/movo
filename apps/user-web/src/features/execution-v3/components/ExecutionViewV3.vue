<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import type { ExecutionStoreV3 } from '../stores/executionStore'
import { t, useLocale } from '../../../composables/i18n'
import CommentaryItem from './CommentaryItem.vue'
import ProvisionalAssistantItem from './ProvisionalAssistantItem.vue'
import ActivityItem from './ActivityItem.vue'
import RepeatedToolCallGroup from './RepeatedToolCallGroup.vue'
import { hasActiveRunningLeaf, runningContainerIds } from '../domain/activityPresentation'
import { collapseRepeatedToolCalls } from '../domain/repeatedToolCalls'
import { elapsedRunMs, formatRunDuration } from '../domain/runTiming'

const props = defineProps<{ store: ExecutionStoreV3; live?: boolean }>()
const emit = defineEmits<{
  (event: 'resolve-permission', requestId: string, decision: 'allow' | 'deny' | 'always_allow'): void
}>()
const collapsed = ref(false)
const userOverrode = ref(false)
const { locale } = useLocale()
const clock = ref(Date.now())
let clockHandle: ReturnType<typeof setInterval> | null = null
const rows = computed(() => {
  // Tolerate stores created before this deployment/HMR cycle, where Vue may
  // already have auto-unwrapped the computed ref through a reactive message.
  const source = props.store.visibleItems as any
  const items = Array.isArray(source) ? source : source?.value
  return (Array.isArray(items) ? items : []).filter(
    (item) => !['artifact', 'evidence', 'browser_preview'].includes(item.kind)
      && (item.kind !== 'commentary' || String(item.payload?.text || '').trim()),
  )
})
const passiveRunningIds = computed(() => runningContainerIds(rows.value))
const timeline = computed(() => collapseRepeatedToolCalls(rows.value))
const showIdlePlaceholder = computed(
  () => Boolean(props.live) && !hasActiveRunningLeaf(rows.value, passiveRunningIds.value),
)
const terminalWithoutAnswer = computed(
  () => !props.live && ['failed', 'cancelled', 'blocked'].includes(props.store.state.runStatus),
)
const terminalText = computed(() => {
  if (props.store.state.runStatus === 'blocked') return t('execution.v3.blocked')
  if (props.store.state.runStatus === 'cancelled') return t('execution.v3.cancelled')
  return t('execution.v3.failed')
})
const terminalDetail = computed(() => {
  if (props.store.state.runStatus !== 'failed') return ''
  const failedEvent = [...props.store.state.rawEvents].reverse().find(event => event.type === 'run.failed')
  const message = String(failedEvent?.payload?.message || '').trim()
  if (!message) return ''
  return /fetch failed|failed to fetch/i.test(message)
    ? t('execution.v3.failed_network')
    : message
})
const activityCount = computed(() => rows.value.filter(
  (item) => !['commentary', 'final_answer'].includes(item.kind),
).length)
const elapsedText = computed(() => formatRunDuration(
  elapsedRunMs(props.store.state.runStartedAt, props.store.state.runEndedAt, clock.value),
  locale.value,
))
const toggleText = computed(() => {
  if (!collapsed.value) return t('execution.v3.process')
  return activityCount.value
    ? t('execution.v3.processed_count', { count: activityCount.value })
    : t('execution.v3.processed')
})

watch(() => props.store.state.finalAnswerComplete, (done) => {
  if (done && !userOverrode.value) collapsed.value = true
}, { immediate: true })

watch(
  () => Boolean(props.live) && props.store.state.runStatus === 'running' && props.store.state.runStartedAt !== null,
  (running) => {
    if (clockHandle !== null) clearInterval(clockHandle)
    clockHandle = null
    clock.value = Date.now()
    if (running) clockHandle = setInterval(() => { clock.value = Date.now() }, 1000)
  },
  { immediate: true },
)

onBeforeUnmount(() => {
  if (clockHandle !== null) clearInterval(clockHandle)
})

function toggle() {
  collapsed.value = !collapsed.value
  userOverrode.value = true
}
</script>

<template>
  <section v-if="rows.length || live || terminalWithoutAnswer" class="execution-v3" :class="{ collapsed }">
    <button class="execution-v3-toggle" type="button" :aria-expanded="!collapsed" @click="toggle">
      <svg viewBox="0 0 24 24"><path d="m9 18 6-6-6-6" /></svg>
      <span>{{ toggleText }}</span>
      <time v-if="elapsedText" class="execution-v3-elapsed" aria-live="off">· {{ elapsedText }}</time>
    </button>
    <div v-show="!collapsed" class="execution-v3-list">
      <template v-for="entry in timeline" :key="entry.key">
        <RepeatedToolCallGroup
          v-if="entry.type === 'tool-group'"
          :items="entry.items"
          :status-items="entry.statusItems"
        />
        <CommentaryItem v-else-if="entry.item.kind === 'commentary'" :item="entry.item" />
        <ProvisionalAssistantItem v-else-if="entry.item.kind === 'final_answer'" :item="entry.item" />
        <ActivityItem
          v-else
          :item="entry.item"
          :active="!passiveRunningIds.has(entry.item.id)"
          @resolve-permission="(requestId, decision) => emit('resolve-permission', requestId, decision)"
        />
      </template>
      <div v-if="showIdlePlaceholder" class="execution-v3-placeholder" role="status" :aria-label="t('execution.v3.processing')">
        <span></span><span></span><span></span>
      </div>
      <div v-if="terminalWithoutAnswer" class="execution-v3-terminal" role="status">
        <span>{{ terminalText }}</span>
        <small v-if="terminalDetail">{{ terminalDetail }}</small>
      </div>
    </div>
  </section>
</template>

<style scoped>
.execution-v3 { display:flex; flex-direction:column; gap:6px; }
.execution-v3-toggle { display:inline-flex; width:fit-content; min-height:32px; align-items:center; gap:5px; padding:2px 4px; border:0; background:transparent; color:#64748b; cursor:pointer; font-size:13px; font-weight:600; }
.execution-v3-toggle:focus-visible { outline:2px solid #2563eb; outline-offset:2px; border-radius:6px; }
.execution-v3-toggle svg { width:15px; height:15px; fill:none; stroke:currentColor; stroke-width:2; stroke-linecap:round; stroke-linejoin:round; transform:rotate(90deg); transition:transform .18s ease; }
.execution-v3-elapsed { min-width:4.5em; color:#7c8798; font-variant-numeric:tabular-nums; font-weight:500; }
.collapsed .execution-v3-toggle svg { transform:rotate(0deg); }
.execution-v3-list { display:flex; flex-direction:column; gap:4px; padding:3px 4px 7px; }
.execution-v3-placeholder { display:flex; gap:4px; align-items:center; min-height:28px; }
.execution-v3-placeholder span { width:5px; height:5px; border-radius:50%; background:#2563eb; animation:placeholder-pulse 1.2s ease-in-out infinite; }
.execution-v3-placeholder span:nth-child(2) { animation-delay:.15s; }
.execution-v3-placeholder span:nth-child(3) { animation-delay:.3s; }
.execution-v3-terminal { display:flex; flex-direction:column; gap:3px; color:#b45309; font-size:13px; padding-bottom:5px; }
.execution-v3-terminal small { color:#7c5b27; font-size:12px; font-weight:400; }
@keyframes placeholder-pulse { 50% { opacity:.3; transform:translateY(-2px); } }
@media (prefers-reduced-motion: reduce) {
  .execution-v3-toggle svg { transition:none; }
  .execution-v3-placeholder span { animation:none; }
}
</style>
