import { computed, ref } from 'vue'
import {
  desktopDiffTabId,
  desktopFileTabId,
  desktopResourceName,
  type DesktopToolLauncherKind,
  type DesktopToolTab,
} from '../../components/desktop/desktopToolTabs'
import type { DshTaskChangeSet } from '../../platform/types'
import type { DocumentInfo } from '../../components/chat/types'
import { desktopChromeMessages, desktopTerminalTabTitle } from '../../locales/desktopChromeMessages'

interface DesktopToolTabsOptions {
  getScopeKey: () => string
  getLocale?: () => 'zh' | 'en'
  isAvailable: (kind: DesktopToolLauncherKind) => boolean
  onActivate?: (tab: DesktopToolTab) => void
}

interface DesktopToolTabsState { tabs: DesktopToolTab[]; activeId: string | null; nextTerminal: number }

export function useDesktopToolTabs(options: DesktopToolTabsOptions) {
  const states = ref<Record<string, DesktopToolTabsState>>({})
  const scopeKey = () => options.getScopeKey() || '__default__'
  function state(): DesktopToolTabsState {
    const key = scopeKey()
    if (!states.value[key]) states.value = { ...states.value, [key]: { tabs: [], activeId: null, nextTerminal: 1 } }
    return states.value[key]
  }
  function tabsFor(key: string): DesktopToolTab[] { return states.value[key || '__default__']?.tabs || [] }
  function activeFor(key: string): string | null { return states.value[key || '__default__']?.activeId || null }
  function update(next: DesktopToolTabsState): void {
    states.value = { ...states.value, [scopeKey()]: next }
  }
  const tabs = computed(() => state().tabs)
  const active = computed<string | null>({ get: () => state().activeId, set: value => update({ ...state(), activeId: value }) })
  const activeTab = computed(() => tabs.value.find(tab => tab.id === active.value) || null)
  const activeKind = computed(() => activeTab.value?.kind || null)
  const language = () => options.getLocale?.() === 'en' ? 'en' : 'zh'

  function activate(tab: DesktopToolTab): void {
    update({ ...state(), activeId: tab.id })
    options.onActivate?.(tab)
  }

  function addOrActivate(tab: DesktopToolTab): void {
    const existing = state().tabs.find(item => item.id === tab.id)
    if (existing) return activate(existing)
    update({ ...state(), tabs: [...state().tabs, tab], activeId: tab.id })
    options.onActivate?.(tab)
  }

  function open(kind: DesktopToolLauncherKind): void {
    if (!options.isAvailable(kind)) return
    if (kind === 'terminal') {
      const number = state().nextTerminal
      const tab = { id: `terminal:${number}`, kind, title: desktopTerminalTabTitle[language()](number) } satisfies DesktopToolTab
      update({ tabs: [...state().tabs, tab], activeId: tab.id, nextTerminal: number + 1 })
      options.onActivate?.(tab)
      return
    }
    addOrActivate({ id: kind, kind, title: desktopChromeMessages[kind][language()] })
  }

  function reveal(kind: DesktopToolLauncherKind): void {
    const existing = [...state().tabs].reverse().find(tab => tab.kind === kind)
    if (existing) activate(existing)
    else open(kind)
  }

  function openFile(path: string): void {
    if (!path || !options.isAvailable('files')) return
    addOrActivate({ id: desktopFileTabId(path), kind: 'file', title: desktopResourceName(path), resource: { path } })
  }

  function openDiff(path: string, taskChanges?: DshTaskChangeSet): void {
    if (!path || !options.isAvailable('changes')) return
    addOrActivate({ id: desktopDiffTabId(path, taskChanges?.task_id), kind: 'diff', title: `${desktopResourceName(path)} (Diff)`, resource: { path, taskChanges } })
  }

  function openPreview(document: DocumentInfo): void {
    const key = document.object_path || (document.local_session_id && document.local_artifact_id ? `${document.local_session_id}:${document.local_artifact_id}` : '') || document.url
    if (!key) return
    addOrActivate({ id: `preview:${encodeURIComponent(key)}`, kind: 'preview', title: document.filename || document.title || key, resource: { document } })
  }

  function select(id: string): void {
    const tab = state().tabs.find(item => item.id === id)
    if (tab) activate(tab)
  }

  function close(id: string): void {
    const index = state().tabs.findIndex(tab => tab.id === id)
    if (index < 0) return
    const remaining = state().tabs.filter(tab => tab.id !== id)
    const wasActive = state().activeId === id
    const next = wasActive ? remaining[Math.min(index, remaining.length - 1)] || null : null
    update({ ...state(), tabs: remaining, activeId: wasActive ? next?.id || null : state().activeId })
    if (next) options.onActivate?.(next)
  }

  function hide(): void { update({ ...state(), activeId: null }) }
  function reset(key = scopeKey()): void {
    const next = { ...states.value }
    delete next[key]
    states.value = next
  }
  function pruneUnavailable(): void {
    const remaining = state().tabs.filter(tab => {
      if (tab.kind === 'preview') return true
      const launcher = tab.kind === 'file' ? 'files' : tab.kind === 'diff' ? 'changes' : tab.kind
      return options.isAvailable(launcher)
    })
    if (remaining.length !== state().tabs.length) {
      const activeId = remaining.some(tab => tab.id === state().activeId) ? state().activeId : null
      update({ ...state(), tabs: remaining, activeId })
    }
  }

  return { tabs, active, activeTab, activeKind, tabsFor, activeFor, open, reveal, openFile, openDiff, openPreview, select, close, hide, reset, pruneUnavailable }
}
