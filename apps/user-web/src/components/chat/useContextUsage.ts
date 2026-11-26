import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { fetchContextUsage, type ContextUsage } from '../../api/contextUsage'

export function useContextUsage(options: {
  sessionId: () => string | undefined
  modelId: () => string
  active: () => boolean
  running: () => boolean
}, fetchUsage: typeof fetchContextUsage = fetchContextUsage) {
  const usage = ref<ContextUsage | null>(null)
  const loading = ref(false)
  let timer: ReturnType<typeof setTimeout> | undefined
  let controller: AbortController | undefined
  let requestKey = ''
  let generation = 0
  let settled = false

  async function refresh() {
    const sessionId = options.sessionId()
    const key = `${sessionId}:${options.modelId()}`
    const enabled = Boolean(sessionId && options.active() && !document.hidden)
    if (enabled && controller && requestKey === key && !controller.signal.aborted) return
    clearTimeout(timer)
    controller?.abort()
    controller = undefined
    const requestGeneration = ++generation
    loading.value = false
    if (!enabled || !sessionId) return
    requestKey = key
    controller = new AbortController()
    loading.value = !settled
    try {
      const result = await fetchUsage(sessionId, controller.signal)
      if (requestGeneration === generation) {
        usage.value = result
      }
    } catch {
      if (requestGeneration === generation && !usage.value?.available) usage.value = null
    } finally {
      if (requestGeneration === generation) {
        settled = true
        loading.value = false
        controller = undefined
        timer = setTimeout(refresh, options.running() ? 5000 : 15000)
      }
    }
  }

  watch([options.sessionId, options.modelId, options.active], () => {
    settled = false
    usage.value = null
    void refresh()
  }, { flush: 'sync' })
  watch(options.running, () => { void refresh() })
  onMounted(() => {
    document.addEventListener('visibilitychange', refresh)
    void refresh()
  })
  onBeforeUnmount(() => {
    generation++
    clearTimeout(timer)
    controller?.abort()
    document.removeEventListener('visibilitychange', refresh)
  })
  return { usage, loading, refresh }
}
