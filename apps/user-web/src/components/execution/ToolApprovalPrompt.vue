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
const isLocal = computed(() => props.item.payload?.source === 'dsh-local')
const description = computed(() => {
  const reason = String(props.item.payload?.description || props.item.payload?.reason || '').trim()
  const prefix = 'escalate sandbox to danger-full-access: '
  return isLocal.value && reason.startsWith(prefix) ? reason.slice(prefix.length) : reason
})
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
        <span class="approval-tool">{{ toolName }}</span>
        <span v-if="!isLocal" class="approval-risk">{{ riskLabel }}</span>
      </div>
      <p class="approval-request">{{ isLocal ? t('approval.local_request') : t('approval.request', { name: toolName }) }}</p>
      <p v-if="description" class="approval-description" :title="description">{{ description }}</p>
      <p v-if="error" class="approval-error" role="alert">{{ error }}</p>
      <div class="approval-actions">
        <button type="button" class="approval-button secondary" :disabled="busy" @click="emit('decide', 'rejected', 'once')">
          {{ t('ui.deny') }}
        </button>
        <button type="button" class="approval-button session" :title="t(isLocal ? 'approval.local_session_hint' : 'approval.session_hint')" :disabled="busy" @click="emit('decide', 'approved', 'session')">
          {{ t('approval.allow_matching_session') }}
        </button>
        <button type="button" class="approval-button primary" :disabled="busy" @click="emit('decide', 'approved', 'once')">
          <span v-if="busy" class="approval-spinner" aria-hidden="true"></span>
          {{ busy ? t('approval.processing') : t('approval.allow_once') }}
        </button>
      </div>
    </div>
  </section>
</template>

<style scoped src="./ToolApprovalPrompt.css"></style>
