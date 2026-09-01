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
.approval-panel { display:flex; gap:12px; margin-top:12px; border:1px solid #f0c36a; border-radius:12px; background:#fffbeb; padding:14px; color:#3f3f46; }
.approval-icon { display:flex; width:32px; height:32px; flex:none; align-items:center; justify-content:center; border-radius:9px; background:#fef3c7; color:#a16207; }
.approval-icon svg { width:18px; height:18px; }
.approval-content { min-width:0; flex:1; }
.approval-heading { display:flex; align-items:center; justify-content:space-between; gap:12px; color:#27272a; font-size:14px; }
.approval-risk { flex:none; border-radius:999px; background:#fde68a; padding:2px 8px; color:#854d0e; font-size:11px; font-weight:600; }
.approval-content p { margin:5px 0 0; font-size:13px; line-height:1.6; }
.approval-description { color:#71717a; }
.approval-error { color:#b91c1c; }
.approval-actions { display:flex; justify-content:flex-end; gap:8px; margin-top:12px; }
.approval-button { display:inline-flex; min-width:84px; min-height:44px; cursor:pointer; align-items:center; justify-content:center; gap:7px; border-radius:9px; padding:8px 16px; font-size:13px; font-weight:600; transition:background-color .18s ease,border-color .18s ease,color .18s ease; }
.approval-button:focus-visible { outline:2px solid #2563eb; outline-offset:2px; }
.approval-button:disabled { cursor:not-allowed; opacity:.6; }
.approval-button.secondary { border:1px solid #d4d4d8; background:#fff; color:#52525b; }
.approval-button.secondary:hover:not(:disabled) { background:#f4f4f5; }
.approval-button.primary { border:1px solid #2563eb; background:#2563eb; color:#fff; }
.approval-button.primary:hover:not(:disabled) { border-color:#1d4ed8; background:#1d4ed8; }
.approval-spinner { width:13px; height:13px; border:2px solid rgba(255,255,255,.45); border-top-color:#fff; border-radius:50%; animation:approval-spin .8s linear infinite; }
@keyframes approval-spin { to { transform:rotate(360deg); } }
@media (prefers-reduced-motion: reduce) { .approval-spinner { animation:none; } }
@media (max-width: 480px) { .approval-panel { padding:12px; } .approval-actions { flex-direction:column-reverse; } .approval-button { width:100%; } }
</style>
