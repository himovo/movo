import { computed, onBeforeUnmount, ref, watch, type ComputedRef } from 'vue'
import {
  decideToolApproval,
  listPendingToolApprovals,
  type PendingToolApproval,
  type ToolApprovalDecision,
  type ToolApprovalGrantScope,
} from '../api/toolApprovals'
import type { ExecutionItemV3 } from '../features/execution-v3/domain/model'
import { ensureMessageExecutionV3 } from '../features/execution-v3/stores/messageExecution'

interface ApprovalMessage {
  _execV3?: ReturnType<typeof ensureMessageExecutionV3>
  execution_events?: unknown[]
}

interface ApprovalControlOptions {
  messages: ComputedRef<ApprovalMessage[]>
  sessionId: () => string | undefined
  authToken: () => string | undefined
  running: () => boolean
  onDecided?: () => void
}

const RECOVERY_INTERVAL_MS = 2000

export function useDshToolApprovals(options: ApprovalControlOptions) {
  const recovered = ref<PendingToolApproval[]>([])
  const busy = ref<Record<string, boolean>>({})
  const errors = ref<Record<string, string>>({})
  let timer: ReturnType<typeof setInterval> | null = null

  const eventItems = computed(() => options.messages.value.flatMap((message) => {
    const source = ensureMessageExecutionV3(message).visibleItems as any
    const items = Array.isArray(source) ? source : source?.value
    return (Array.isArray(items) ? items : []).filter(
      (item: ExecutionItemV3) => item.kind === 'approval'
        && item.status === 'running'
        && ['askai-approval', 'dsh'].includes(String(item.payload?.source || '')),
    )
  }))

  const active = computed<ExecutionItemV3[]>(() => {
    const byAction = new Map<string, ExecutionItemV3>()
    for (const item of eventItems.value) byAction.set(actionId(item), item)
    for (const row of recovered.value) {
      if (!byAction.has(row.action_id)) byAction.set(row.action_id, recoveredItem(row))
    }
    return [...byAction.values()]
  })

  async function refresh() {
    const token = options.authToken()
    const conversationId = options.sessionId()
    if (!token || !conversationId) {
      recovered.value = []
      return
    }
    try {
      recovered.value = await listPendingToolApprovals(token, conversationId)
    } catch {
      // The live V3 event remains usable; the next poll retries durable recovery.
    }
  }

  async function decide(
    item: ExecutionItemV3,
    decision: ToolApprovalDecision,
    grantScope: ToolApprovalGrantScope = 'once',
  ) {
    const id = actionId(item)
    const token = options.authToken()
    if (!id || !token || busy.value[id]) return
    busy.value = { ...busy.value, [id]: true }
    errors.value = { ...errors.value, [id]: '' }
    try {
      await decideToolApproval(id, decision, token, grantScope)
      recovered.value = recovered.value.filter((row) => row.action_id !== id)
      options.onDecided?.()
      await refresh()
    } catch (error: any) {
      errors.value = { ...errors.value, [id]: String(error?.message || 'Approval failed') }
    } finally {
      busy.value = { ...busy.value, [id]: false }
    }
  }

  function resetTimer() {
    if (timer !== null) clearInterval(timer)
    timer = null
    void refresh()
    if (options.running() && options.authToken()) {
      timer = setInterval(() => { void refresh() }, RECOVERY_INTERVAL_MS)
    }
  }

  watch(
    () => [options.sessionId(), options.authToken(), options.running()],
    resetTimer,
    { immediate: true },
  )
  onBeforeUnmount(() => { if (timer !== null) clearInterval(timer) })

  return { active, busy, errors, decide, refresh }
}

function actionId(item: ExecutionItemV3): string {
  return String(item.payload?.action_id || item.id)
}

function recoveredItem(row: PendingToolApproval): ExecutionItemV3 {
  const timestamp = row.created_at ? Date.parse(row.created_at) : Date.now()
  return {
    id: row.action_id,
    kind: 'approval',
    revision: 1,
    startedAt: Number.isFinite(timestamp) ? timestamp : Date.now(),
    updatedAt: Number.isFinite(timestamp) ? timestamp : Date.now(),
    status: 'running',
    payload: {
      source: 'askai-approval',
      action_id: row.action_id,
      request_id: row.action_id,
      tool_name: row.tool_name,
      display_name: row.tool_name,
      reason: row.reason || '',
      args: row.arguments || {},
      scope_label: row.scope_label || '',
      status: 'pending',
      recovered: true,
    },
  }
}
