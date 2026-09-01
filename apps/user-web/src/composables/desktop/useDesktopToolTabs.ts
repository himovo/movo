import { ref } from 'vue'
import type { DesktopToolTab, DesktopToolTabKind } from '../../components/desktop/desktopToolTabs'

interface DesktopToolTabsOptions {
  isAvailable: (kind: DesktopToolTabKind) => boolean
  onActivate?: (kind: DesktopToolTabKind) => void
}

export function useDesktopToolTabs(options: DesktopToolTabsOptions) {
  const tabs = ref<DesktopToolTab[]>([])
  const active = ref<DesktopToolTabKind | null>(null)

  function activate(kind: DesktopToolTabKind): void {
    active.value = kind
    options.onActivate?.(kind)
  }

  function open(kind: DesktopToolTabKind): void {
    if (!options.isAvailable(kind)) return
    if (!tabs.value.some(tab => tab.kind === kind)) tabs.value = [...tabs.value, { id: kind, kind }]
    activate(kind)
  }

  function select(kind: DesktopToolTabKind): void {
    if (tabs.value.some(tab => tab.kind === kind)) activate(kind)
  }

  function close(kind: DesktopToolTabKind): void {
    const index = tabs.value.findIndex(tab => tab.kind === kind)
    if (index < 0) return
    const remaining = tabs.value.filter(tab => tab.kind !== kind)
    tabs.value = remaining
    if (active.value === kind) {
      const next = remaining[Math.min(index, remaining.length - 1)]?.kind || null
      active.value = next
      if (next) options.onActivate?.(next)
    }
  }

  function hide(): void { active.value = null }
  function reset(): void { tabs.value = []; active.value = null }

  return { tabs, active, open, select, close, hide, reset }
}

