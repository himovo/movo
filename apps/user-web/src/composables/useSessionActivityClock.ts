import { onBeforeUnmount, onMounted, ref } from 'vue'

export function useSessionActivityClock() {
  const now = ref(Date.now())
  let timer: ReturnType<typeof setInterval> | undefined
  const refresh = () => { now.value = Date.now() }
  onMounted(() => {
    timer = setInterval(refresh, 60_000)
    document.addEventListener('visibilitychange', refresh)
    window.addEventListener('focus', refresh)
  })
  onBeforeUnmount(() => {
    if (timer) clearInterval(timer)
    document.removeEventListener('visibilitychange', refresh)
    window.removeEventListener('focus', refresh)
  })
  return now
}
