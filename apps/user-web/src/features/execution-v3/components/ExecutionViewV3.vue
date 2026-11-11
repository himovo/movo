<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import type { ExecutionStoreV3 } from '../stores/executionStore'
import { t, useLocale } from '../../../composables/i18n'
import CommentaryItem from './CommentaryItem.vue'
import ProvisionalAssistantItem from './ProvisionalAssistantItem.vue'
import ActivityItem from './ActivityItem.vue'
import RepeatedToolCallGroup from './RepeatedToolCallGroup.vue'
import { hasVisibleActiveRunningLeaf, runningContainerIds } from '../domain/activityPresentation'
import { collapseRepeatedToolCalls } from '../domain/repeatedToolCalls'
import { elapsedRunMs, formatRunDuration } from '../domain/runTiming'
import { failureMessageKey } from '../domain/failureMessage'

const props = defineProps<{ store: ExecutionStoreV3; live?: boolean; connectionLostAt?: number }>()
const emit = defineEmits<{
  (event: 'resolve-permission', requestId: string, decision: 'allow' | 'deny' | 'always_allow'): void
}>()
const collapsed = ref(false)
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
  () => Boolean(props.live && !props.connectionLostAt)
    && !hasVisibleActiveRunningLeaf(rows.value, passiveRunningIds.value),
)
const terminalWithoutAnswer = computed(
  () => Boolean(props.connectionLostAt) || (!props.live && ['failed', 'cancelled', 'blocked'].includes(props.store.state.runStatus)),
)
const terminalText = computed(() => {
  if (props.connectionLostAt) return t('execution.v3.connection_lost')
  if (props.store.state.runStatus === 'blocked') return t('execution.v3.blocked')
  if (props.store.state.runStatus === 'cancelled') return t('execution.v3.cancelled')
  return t('execution.v3.failed')
})
const terminalDetail = computed(() => {
  if (props.connectionLostAt) return ''
  if (props.store.state.runStatus !== 'failed') return ''
  const failedEvent = [...props.store.state.rawEvents].reverse().find(event => event.type === 'run.failed')
  const message = String(failedEvent?.payload?.message || '').trim()
  if (!message) return ''
  const key = failureMessageKey(message)
  return key ? t(key) : message
})
const activityCount = computed(() => rows.value.filter(
  (item) => !['commentary', 'final_answer'].includes(item.kind),
).length)
const elapsedText = computed(() => formatRunDuration(
  elapsedRunMs(props.store.state.runStartedAt, props.store.state.runEndedAt, props.connectionLostAt || clock.value),
  locale.value,
))
const toggleText = computed(() => {
  if (!collapsed.value) return t('execution.v3.process')
  return activityCount.value
    ? t('execution.v3.processed_count', { count: activityCount.value })
    : t('execution.v3.processed')
})

watch(() => props.store.state.finalAnswerComplete, (done) => {
  if (done) collapsed.value = true
}, { immediate: true, flush: 'sync' })

watch(
  () => Boolean(props.live && !props.connectionLostAt) && props.store.state.runStatus === 'running' && props.store.state.runStartedAt !== null,
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
          :run-status="store.state.runStatus"
        />
        <CommentaryItem v-else-if="entry.item.kind === 'commentary'" :item="entry.item" />
        <ProvisionalAssistantItem v-else-if="entry.item.kind === 'final_answer'" :item="entry.item" />
        <ActivityItem
          v-else
          :item="entry.item"
          :active="!props.connectionLostAt && !passiveRunningIds.has(entry.item.id)"
          :run-status="store.state.runStatus"
          @resolve-permission="(requestId, decision) => emit('resolve-permission', requestId, decision)"
        />
      </template>
      <div v-if="showIdlePlaceholder" class="execution-v3-placeholder" role="status" :aria-label="t('execution.v3.processing')">
        <span class="execution-v3-thinking">{{ t('execution.v3.thinking') }}</span>
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
.execution-v3-placeholder { display:flex; align-items:center; min-height:28px; }
.execution-v3-thinking {
  color:transparent;
  background:linear-gradient(100deg,#64748b 12%,#2563eb 42%,#93c5fd 52%,#2563eb 62%,#64748b 88%);
  background-size:240% 100%;
  background-clip:text;
  -webkit-background-clip:text;
  font-size:12px;
  font-weight:600;
  animation:thinking-sheen 1.7s linear infinite;
}
.execution-v3-terminal { display:flex; flex-direction:column; gap:3px; color:#b45309; font-size:13px; padding-bottom:5px; }
.execution-v3-terminal small { color:#7c5b27; font-size:12px; font-weight:400; }
@keyframes thinking-sheen { from { background-position:100% 0; } to { background-position:-140% 0; } }
@media (prefers-reduced-motion: reduce) {
  .execution-v3-toggle svg { transition:none; }
  .execution-v3-thinking { color:#2563eb; background:none; animation:none; }
}
</style>
