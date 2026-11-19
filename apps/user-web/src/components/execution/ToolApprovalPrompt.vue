<script setup lang="ts">
import { computed } from 'vue'
import { t } from '../../composables/i18n'
import type { ExecutionItemV3 } from '../../features/execution-v3/domain/model'
import { localizedInternalToolLabel } from '../../features/execution-v3/domain/internalToolLabels'

const props = defineProps<{
  item: ExecutionItemV3
  busy?: boolean
  error?: string
}>()

const emit = defineEmits<{
  (event: 'decide', decision: 'approved' | 'rejected', grantScope: 'once' | 'session'): void
}>()

const toolName = computed(() => localizedInternalToolLabel(
  props.item.payload?.tool_name,
  props.item.payload?.display_name || props.item.payload?.tool_name || t('approval.unknown_tool'),
))
const description = computed(() => String(props.item.payload?.description || '').trim())
const riskLabel = computed(() => {
  const risk = String(props.item.payload?.risk_level || '')
  if (risk === 'dangerous') return t('approval.risk_dangerous')
  return t('approval.risk_write')
})
</script>

<template>
  <section class="approval-panel" role="region" :aria-label="t('approval.title')">
    <div class="approval-icon" aria-hidden="true">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <rect x="5" y="10" width="14" height="10" rx="2" />
        <path d="M8 10V7a4 4 0 0 1 8 0v3" />
      </svg>
    </div>
    <div class="approval-content">
      <div class="approval-heading">
        <strong>{{ t('approval.title') }}</strong>
        <span class="approval-risk">{{ riskLabel }}</span>
      </div>
      <p class="approval-request">{{ t('approval.request', { name: toolName }) }}</p>
      <p v-if="description" class="approval-description" :title="description">{{ description }}</p>
      <p v-if="error" class="approval-error" role="alert">{{ error }}</p>
      <div class="approval-actions">
        <button type="button" class="approval-button secondary" :disabled="busy" @click="emit('decide', 'rejected', 'once')">
          {{ t('ui.deny') }}
        </button>
        <button type="button" class="approval-button secondary" :disabled="busy" @click="emit('decide', 'approved', 'once')">
          <span v-if="busy" class="approval-spinner" aria-hidden="true"></span>
          {{ busy ? t('approval.processing') : t('ui.allow') }}
        </button>
        <button type="button" class="approval-button primary" :disabled="busy" @click="emit('decide', 'approved', 'session')">
          <span v-if="busy" class="approval-spinner" aria-hidden="true"></span>
          {{ busy ? t('approval.processing') : t('approval.allow_session') }}
        </button>
      </div>
    </div>
  </section>
</template>

<style scoped>
.approval-panel { display:flex; box-sizing:border-box; width:100%; gap:11px; margin-top:8px; border:1px solid #e4c993; border-left:3px solid #cf8c19; border-radius:12px; background:#fffdf8; padding:12px 14px; color:#334155; box-shadow:0 5px 20px rgba(30,41,59,.06); }
.approval-icon { display:flex; width:30px; height:30px; flex:none; align-items:center; justify-content:center; border-radius:9px; background:#fff0cf; color:#94600b; }
.approval-icon svg { width:16px; height:16px; }
.approval-content { min-width:0; flex:1; }
.approval-heading { display:flex; align-items:center; flex-wrap:wrap; gap:8px; min-height:28px; color:#1e293b; font-size:14px; }
.approval-risk { flex:none; border-radius:6px; background:#fff0cf; padding:1px 7px; color:#805008; font-size:11px; font-weight:600; line-height:18px; }
.approval-content p { margin:3px 0 0; font-size:12px; line-height:1.45; }
.approval-request { font-weight:600; }
.approval-description { color:#64748b; max-height:4.4em; overflow:auto; overflow-wrap:anywhere; }
.approval-error { color:#b42318; overflow-wrap:anywhere; }
.approval-actions { display:flex; justify-content:flex-end; flex-wrap:wrap; gap:7px; margin-top:9px; }
.approval-button { display:inline-flex; min-width:72px; min-height:40px; cursor:pointer; align-items:center; justify-content:center; gap:6px; border-radius:8px; padding:6px 12px; font-size:12px; font-weight:600; transition:background-color .18s ease,border-color .18s ease,color .18s ease; }
.approval-button:focus-visible { outline:2px solid #2563eb; outline-offset:2px; }
.approval-button:disabled { cursor:not-allowed; opacity:.6; }
.approval-button.secondary { border:1px solid #cbd5e1; background:#fff; color:#334155; }
.approval-button.secondary:hover:not(:disabled) { background:#f1f5f9; }
.approval-button.primary { border:1px solid #2563eb; background:#2563eb; color:#fff; }
.approval-button.primary:hover:not(:disabled) { border-color:#1d4ed8; background:#1d4ed8; }
.approval-spinner { width:13px; height:13px; border:2px solid rgba(255,255,255,.45); border-top-color:#fff; border-radius:50%; animation:approval-spin .8s linear infinite; }
@keyframes approval-spin { to { transform:rotate(360deg); } }
@media (prefers-reduced-motion: reduce) { .approval-spinner { animation:none; } }
html.theme-dark .approval-panel { border-color:#675735; border-left-color:#d6a24a; background:#1c2635; color:#e2e8f0; box-shadow:0 5px 20px rgba(0,0,0,.16); }
html.theme-dark .approval-heading { color:#f1f5f9; }
html.theme-dark .approval-icon, html.theme-dark .approval-risk { background:#3b3426; color:#f6d790; }
html.theme-dark .approval-description { color:#aebed1; }
html.theme-dark .approval-error { color:#ffb4b4; }
html.theme-dark .approval-button.secondary { border-color:#536176; background:#263449; color:#e2e8f0; }
html.theme-dark .approval-button.secondary:hover:not(:disabled) { background:#344761; }
@media (max-width: 480px) { .approval-panel { padding:10px; } .approval-actions { display:grid; grid-template-columns:1fr 1fr; } .approval-button { width:100%; } .approval-button.primary { grid-column:1 / -1; } }
</style>
