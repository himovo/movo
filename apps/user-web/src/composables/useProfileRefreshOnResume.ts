import { onBeforeUnmount, onMounted, type Ref } from 'vue'

interface ProfileRefreshOptions {
  token: Ref<string>
  refresh: (token: string) => Promise<void>
  minimumIntervalMs?: number
}

/** Refresh mutable enterprise policy when an employee returns to the app. */
export function useProfileRefreshOnResume(options: ProfileRefreshOptions): void {
  let lastStartedAt = 0
  let inFlight: Promise<void> | null = null
  const minimumIntervalMs = options.minimumIntervalMs ?? 3_000

  const refresh = () => {
    const token = options.token.value
    const now = Date.now()
    if (!token || inFlight || now - lastStartedAt < minimumIntervalMs) return
    lastStartedAt = now
    inFlight = options.refresh(token).finally(() => { inFlight = null })
  }
  const onVisibilityChange = () => {
    if (document.visibilityState === 'visible') refresh()
  }

  onMounted(() => {
    window.addEventListener('focus', refresh)
    document.addEventListener('visibilitychange', onVisibilityChange)
  })
  onBeforeUnmount(() => {
    window.removeEventListener('focus', refresh)
    document.removeEventListener('visibilitychange', onVisibilityChange)
  })
}
