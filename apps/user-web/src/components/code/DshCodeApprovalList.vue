<script setup lang="ts">
import { computed } from 'vue'
import type { DshPendingApproval } from '../../platform/types'
import type { ExecutionItemV3 } from '../../features/execution-v3/domain/model'
import ToolApprovalPrompt from '../execution/ToolApprovalPrompt.vue'

const props = defineProps<{
  approvals: DshPendingApproval[]
  busy?: Record<string, boolean>
  error?: string
}>()

const emit = defineEmits<{
  (event: 'decide', approvalId: string, decision: 'approved' | 'rejected', scope: 'once' | 'session'): void
}>()

const items = computed(() => props.approvals.map((approval): ExecutionItemV3 => ({
  id: approval.approval_id,
  kind: 'approval',
  revision: 1,
  startedAt: approval.created_at,
  updatedAt: approval.created_at,
  status: 'running',
  payload: {
    source: 'dsh-local', approval_id: approval.approval_id,
    tool_name: approval.tool_name, display_name: approval.tool_name,
    call_id: approval.call_id, description: approval.reason, risk_level: 'write',
  },
})))
</script>

<template>
  <div v-if="items.length" class="dsh-code-approvals">
    <ToolApprovalPrompt
      v-for="item in items"
      :key="item.id"
      :item="item"
      :busy="Boolean(busy?.[item.id])"
      :error="error || ''"
      @decide="(decision, scope) => emit('decide', item.id, decision, scope)"
    />
  </div>
</template>

<style scoped>
.dsh-code-approvals { width:100%; }
</style>
