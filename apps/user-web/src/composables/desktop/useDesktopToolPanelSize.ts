import { computed, ref } from 'vue'

const WIDTH_KEY = 'movo.desktop-tool-panel-width'
const LEGACY_BROWSER_RATIO_KEY = 'askai.browser-pane-ratio'
const DEFAULT_WIDTH = 720
const MIN_WIDTH = 520

function maximumWidth(): number {
  return typeof window === 'undefined' ? 1180 : Math.max(MIN_WIDTH, window.innerWidth * 0.82)
}

function clamp(value: number): number {
  return Math.min(maximumWidth(), Math.max(MIN_WIDTH, value))
}

function initialWidth(): number {
  if (typeof localStorage === 'undefined') return DEFAULT_WIDTH
  const stored = Number(localStorage.getItem(WIDTH_KEY))
  if (Number.isFinite(stored) && stored > 0) return clamp(stored)
  const legacyRatio = Number(localStorage.getItem(LEGACY_BROWSER_RATIO_KEY))
  if (Number.isFinite(legacyRatio) && legacyRatio > 0 && typeof window !== 'undefined') {
    return clamp(window.innerWidth * legacyRatio)
  }
  return clamp(DEFAULT_WIDTH)
}

// One shared size keeps Browser, Changes, Files and Terminal visually stable
// while switching between tool tabs.
const sharedWidth = ref(initialWidth())
const sharedDragging = ref(false)

export function useDesktopToolPanelSize() {
  const width = computed(() => `${clamp(sharedWidth.value)}px`)

  function setWidth(value: number): void {
    sharedWidth.value = clamp(value)
    localStorage.setItem(WIDTH_KEY, String(sharedWidth.value))
  }

  function beginDrag(event: PointerEvent): void {
    const dragStart = event.clientX
    const widthStart = clamp(sharedWidth.value)
    sharedDragging.value = true
    const move = (next: PointerEvent) => setWidth(widthStart + dragStart - next.clientX)
    const stop = () => {
      sharedDragging.value = false
      window.removeEventListener('pointermove', move)
      window.removeEventListener('pointerup', stop)
    }
    window.addEventListener('pointermove', move)
    window.addEventListener('pointerup', stop, { once: true })
    event.preventDefault()
  }

  function adjustByKeyboard(event: KeyboardEvent): void {
    if (event.key === 'ArrowLeft') setWidth(sharedWidth.value + 24)
    else if (event.key === 'ArrowRight') setWidth(sharedWidth.value - 24)
    else return
    event.preventDefault()
  }

  return { width, dragging: sharedDragging, beginDrag, adjustByKeyboard }
}

