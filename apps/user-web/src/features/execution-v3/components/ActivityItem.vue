<script setup lang="ts">
import { computed } from 'vue'
import type { ExecutionItemV3 } from '../domain/model'
import { t } from '../../../composables/i18n'
import ActivityIcon from './ActivityIcon.vue'
import { activityOutcome, activityStateMessageKey } from '../domain/activityPresentation'
import { toolActionLabelKey, toolCallSummary } from '../domain/repeatedToolCalls'

const props = withDefaults(defineProps<{ item: ExecutionItemV3; active?: boolean }>(), {
  active: true,
})
const emit = defineEmits<{
  (event: 'resolve-permission', requestId: string, decision: 'allow' | 'deny' | 'always_allow'): void
}>()

const category = computed(() => {
  if (['browser_handoff', 'approval', 'error'].includes(props.item.kind)) return props.item.kind
  return String(props.item.payload?.category || props.item.kind || 'tool')
})
const outcome = computed(() => activityOutcome(props.item.payload))
const activelyRunning = computed(() => props.item.status === 'running' && props.active)
const stateText = computed(() => {
  const key = activityStateMessageKey(props.item.status, outcome.value, props.item.payload)
  return key ? t(key) : ''
})
const text = computed(() => {
  const payload = props.item.payload || {}
  if (props.item.kind === 'activity') return String(payload.label || '')
  if (props.item.kind === 'tool') {
    return t(toolActionLabelKey(props.item))
  }
  if (props.item.kind === 'subagent') return String(payload.goal || payload.summary || '')
  if (props.item.kind === 'approval') {
    if (['dsh', 'dsh-local', 'askai-approval'].includes(String(payload.source || ''))) {
      const name = String(payload.display_name || '').trim()
      return name ? t('approval.timeline_pending', { name }) : t('ui.permission_required')
    }
    return String(payload.reason || t('ui.permission_required'))
  }
  if (props.item.kind === 'browser_handoff') return String(payload.reason || t('execution.v3.browser_handoff'))
  if (props.item.kind === 'error') return String(payload.message || t('ui.failed'))
  return ''
})
const detail = computed(() => props.item.kind === 'tool' ? toolCallSummary(props.item) : '')
</script>

<template>
  <div v-if="text" class="activity-row" :class="[`category-${category}`, `status-${item.status}`, `outcome-${outcome || 'none'}`, { 'actively-running': activelyRunning, 'tool-activity-row': item.kind === 'tool' }]">
    <ActivityIcon :category="category" :kind="item.kind" />
    <span class="activity-copy">{{ text }}</span>
    <span v-if="detail" class="activity-detail">{{ detail }}</span>
    <span v-if="stateText" class="activity-state">{{ stateText }}</span>
    <span v-if="item.kind === 'approval' && item.status === 'running' && !['dsh', 'dsh-local', 'askai-approval'].includes(String(item.payload?.source || ''))" class="activity-actions">
      <button type="button" @click="emit('resolve-permission', String(item.payload.request_id || item.id), 'deny')">{{ t('ui.deny') }}</button>
      <button type="button" class="primary" @click="emit('resolve-permission', String(item.payload.request_id || item.id), 'allow')">{{ t('ui.allow') }}</button>
    </span>
  </div>
</template>

<style scoped>
.activity-row {
  --activity-color:#475569;
  display:flex;
  align-items:center;
  gap:10px;
  min-height:32px;
  color:var(--activity-color);
  font-size:13px;
  line-height:20px;
}
.activity-copy { min-width:0; overflow-wrap:anywhere; }
.tool-activity-row .activity-copy {
  flex:0 0 auto;
  max-width:clamp(140px,22vw,260px);
  overflow:hidden;
  text-overflow:ellipsis;
  white-space:nowrap;
}
.activity-detail { min-width:0; flex:1 1 auto; overflow:hidden; color:#94a3b8; font-size:12px; text-overflow:ellipsis; white-space:nowrap; }
.status-running { --activity-color:#64748b; }
.status-running.actively-running { --activity-color:#2563eb; }
.status-running.actively-running .activity-copy {
  color:transparent;
  background:linear-gradient(100deg,#2563eb 16%,#93c5fd 38%,#2563eb 60%);
  background-size:240% 100%;
  background-clip:text;
  -webkit-background-clip:text;
  animation:activity-sheen 1.7s linear infinite;
}
.status-completed { --activity-color:#64748b; }
.status-failed,.category-warning,.category-error,.outcome-inconclusive { --activity-color:#b45309; }
.outcome-needs_repair { --activity-color:#9a3412; }
.status-abandoned { --activity-color:#64748b; }
.activity-state { margin-left:auto; flex:none; color:var(--activity-color); font-size:11px; }
.activity-actions { display:inline-flex; gap:6px; margin-left:auto; }
.activity-actions button { min-height:28px; border:1px solid #cbd5e1; border-radius:7px; background:#fff; padding:3px 10px; color:#475569; cursor:pointer; font-size:12px; }
.activity-actions .primary { border-color:#2563eb; background:#2563eb; color:#fff; }
.activity-actions button:focus-visible { outline:2px solid #2563eb; outline-offset:2px; }
@keyframes activity-sheen { from { background-position:100% 0; } to { background-position:-140% 0; } }
@media (max-width:640px) {
  .tool-activity-row {
    display:grid;
    grid-template-columns:18px minmax(0,1fr) auto;
    column-gap:8px;
    row-gap:1px;
  }
  .tool-activity-row .activity-copy {
    grid-column:2;
    max-width:none;
  }
  .tool-activity-row .activity-detail {
    grid-column:2 / -1;
    min-width:0;
  }
  .tool-activity-row .activity-state,
  .tool-activity-row .activity-actions {
    grid-column:3;
    grid-row:1;
  }
}
@media (prefers-reduced-motion: reduce) {
  .status-running.actively-running .activity-copy { color:#2563eb; background:none; animation:none; }
}
</style>
