import { onBeforeUnmount, onMounted, ref } from 'vue'
import { getDesktopCompatibilityState, onDesktopCompatibilityState, type DesktopCompatibilityState } from '../../platform'

export function useDesktopCompatibility() {
  const state = ref<DesktopCompatibilityState>({ current: { level: 'unconfigured', desktop_version: '', checked_at: 0 } })
  let dispose: (() => void) | undefined
  onMounted(async () => {
    dispose = onDesktopCompatibilityState(next => { state.value = next })
    state.value = await getDesktopCompatibilityState().catch(() => state.value)
  })
  onBeforeUnmount(() => dispose?.())
  return state
}
