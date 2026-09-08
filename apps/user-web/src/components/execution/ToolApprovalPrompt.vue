<script setup lang="ts">
import { computed } from 'vue'
import { t } from '../../composables/i18n'
import type { ExecutionItemV3 } from '../../features/execution-v3/domain/model'

const props = defineProps<{
  item: ExecutionItemV3
  busy?: boolean
  error?: string
}>()

const emit = defineEmits<{
  (event: 'decide', decision: 'approved' | 'rejected', grantScope: 'once' | 'session'): void
}>()

const toolName = computed(() => String(
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
      <p>{{ t('approval.request', { name: toolName }) }}</p>
      <p v-if="description" class="approval-description">{{ description }}</p>
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
.approval-panel { display:flex; box-sizing:border-box; width:min(100%, 620px); gap:10px; margin-top:10px; border:1px solid #f0c36a; border-radius:11px; background:#fffbeb; padding:11px 12px; color:#3f3f46; }
.approval-icon { display:flex; width:28px; height:28px; flex:none; align-items:center; justify-content:center; border-radius:8px; background:#fef3c7; color:#a16207; }
.approval-icon svg { width:16px; height:16px; }
.approval-content { min-width:0; flex:1; }
.approval-heading { display:flex; align-items:center; justify-content:flex-start; flex-wrap:wrap; gap:6px; min-height:28px; color:#27272a; font-size:13px; }
.approval-risk { flex:none; border-radius:999px; background:#fde68a; padding:1px 7px; color:#854d0e; font-size:10px; font-weight:600; line-height:18px; }
.approval-content p { margin:2px 0 0; font-size:12px; line-height:1.5; }
.approval-description { color:#71717a; }
.approval-error { color:#b91c1c; }
.approval-actions { display:flex; justify-content:flex-start; flex-wrap:wrap; gap:6px; margin-top:8px; }
.approval-button { display:inline-flex; min-width:72px; min-height:40px; cursor:pointer; align-items:center; justify-content:center; gap:6px; border-radius:8px; padding:6px 12px; font-size:12px; font-weight:600; transition:background-color .18s ease,border-color .18s ease,color .18s ease; }
.approval-button:focus-visible { outline:2px solid #2563eb; outline-offset:2px; }
.approval-button:disabled { cursor:not-allowed; opacity:.6; }
.approval-button.secondary { border:1px solid #d4d4d8; background:#fff; color:#52525b; }
.approval-button.secondary:hover:not(:disabled) { background:#f4f4f5; }
.approval-button.primary { border:1px solid #2563eb; background:#2563eb; color:#fff; }
.approval-button.primary:hover:not(:disabled) { border-color:#1d4ed8; background:#1d4ed8; }
.approval-spinner { width:13px; height:13px; border:2px solid rgba(255,255,255,.45); border-top-color:#fff; border-radius:50%; animation:approval-spin .8s linear infinite; }
@keyframes approval-spin { to { transform:rotate(360deg); } }
@media (prefers-reduced-motion: reduce) { .approval-spinner { animation:none; } }
@media (max-width: 480px) { .approval-panel { padding:10px; } .approval-actions { display:grid; grid-template-columns:1fr 1fr; } .approval-button { width:100%; } .approval-button.primary { grid-column:1 / -1; } }
</style>
