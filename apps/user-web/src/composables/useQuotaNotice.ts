import { computed, ref, watch, type Ref } from 'vue'
import { fetchOrgBilling } from '../api/auth'
import type { ChatMessage } from '../components/chat/chatMessage'
import { isExecutionEventV3 } from '../features/execution-v3/domain/protocol'

export type QuotaNotice = 'enterprise' | 'personal' | null

export function useQuotaNotice(
  messages: Ref<ChatMessage[]>,
  authToken: () => string | undefined,
  initialNotice: () => QuotaNotice,
  running: () => boolean,
) {
  const verifiedNotice = ref<QuotaNotice>(null)
  let requestId = 0
  const failureId = computed(() => {
    for (const message of [...messages.value].reverse()) {
      const events = (message._execV3?.state.rawEvents || message.execution_events || []).filter(isExecutionEventV3)
      const failed = [...events].reverse().find(event => event.type === 'run.failed')
      if (failed?.payload?.code === 'MODEL_GATEWAY_UNAUTHORIZED'
        && /token has expired/i.test(String(failed.payload?.message || ''))) {
        return String(failed.event_id || failed.id || message._id || '')
      }
    }
    return ''
  })

  watch([failureId, () => authToken()], async ([id, token]) => {
    const current = ++requestId
    verifiedNotice.value = null
    if (!id || !token) return
    const result = await fetchOrgBilling(token)
    if (current !== requestId || !result.ok) return
    if (Number(result.data?.remainingPoints || 0) <= 0) {
      verifiedNotice.value = result.data?.spaceType === 'enterprise' ? 'enterprise' : 'personal'
    }
  }, { immediate: true })

  watch([() => running(), () => authToken()], ([active, token], _old, onCleanup) => {
    if (!active || !token) return
    let cancelled = false
    verifiedNotice.value = null
    const check = async () => {
      const result = await fetchOrgBilling(token)
      if (cancelled || !result.ok) return
      verifiedNotice.value = Number(result.data?.remainingPoints || 0) <= 0
        ? (result.data?.spaceType === 'enterprise' ? 'enterprise' : 'personal')
        : null
    }
    const timer = window.setInterval(() => { void check() }, 60_000)
    void check()
    onCleanup(() => { cancelled = true; window.clearInterval(timer) })
  }, { immediate: true })

  return computed(() => initialNotice() || verifiedNotice.value)
}
