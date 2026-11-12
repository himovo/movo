import { computed, ref, watch, type Ref } from 'vue'
import { activateEmbeddedBrowserSession, capabilities, selectEmbeddedBrowserSession } from '../../platform'
import type { AppView } from '../useAppNavigation'
import type { useDshCodeRuntime } from '../code/useDshCodeRuntime'
import { useDesktopWorkspaceSummary } from './useDesktopWorkspaceSummary'
import { useDesktopToolTabs } from './useDesktopToolTabs'
import { useDesktopCodePanel } from './useDesktopCodePanel'
import type { DesktopToolLauncherKind } from '../../components/desktop/desktopToolTabs'

type Options = {
  codeRuntime: ReturnType<typeof useDshCodeRuntime>
  activeChatKey: Ref<string>
  currentView: Ref<AppView>
  currentSessionId: Ref<string | null>
  locale: Ref<string>
  canUseBrowser: Ref<boolean>
}

/** Coordinates desktop Code inspection and tool tabs for the active chat pane. */
export function useAppDesktopTools(options: Options) {
  const { codeRuntime, activeChatKey, currentView, currentSessionId, locale, canUseBrowser } = options
  watch(currentSessionId, sessionId => {
    if (capabilities.embeddedBrowser && sessionId) void selectEmbeddedBrowserSession(sessionId)
  }, { immediate: true })
  const desktopBrowserRequest = ref(0)
  const activeCodeState = computed(() => codeRuntime.stateFor(activeChatKey.value))
  const {
    reviewPath: desktopCodeReviewPath, reviewChanges: desktopCodeReviewChanges,
    filePath: desktopCodeFilePath, summary: desktopWorkspaceSummary,
    refresh: refreshDesktopWorkspaceSummary,
  } = useDesktopWorkspaceSummary({
    codeInspector: capabilities.codeInspector,
    sessionId: () => activeCodeState.value.session?.kernel_session_id,
    eventCount: () => activeCodeState.value.events.length,
    latestEvent: () => activeCodeState.value.events.at(-1),
  })

  const desktopAvailableTools = computed<DesktopToolLauncherKind[]>(() => {
    const tools: DesktopToolLauncherKind[] = []
    if (canUseBrowser.value && activeChatKey.value) tools.push('browser')
    if (activeCodeState.value.session && capabilities.codeInspector) {
      if (desktopWorkspaceSummary.value?.git_available === true) tools.push('changes')
      if (capabilities.workspaceFiles) tools.push('files')
      if (capabilities.projectTerminal) tools.push('terminal')
    }
    return tools
  })

  const {
    tabs: desktopToolTabs,
    active: desktopActiveTool,
    activeKind: desktopActiveToolKind,
    tabsFor: desktopToolTabsFor,
    activeFor: desktopActiveToolFor,
    open: openDesktopTool,
    reveal: revealDesktopTool,
    openFile: openDesktopFileTab,
    openDiff: openDesktopDiffTab,
    openPreview: openDesktopPreviewTab,
    select: selectDesktopTool,
    close: closeDesktopTool,
    hide: hideDesktopTools,
  } = useDesktopToolTabs({
    getScopeKey: () => activeChatKey.value,
    getLocale: () => locale.value === 'en' ? 'en' : 'zh',
    isAvailable: kind => currentView.value === 'chat' && desktopAvailableTools.value.includes(kind),
    onActivate: tab => {
      if (tab.kind === 'browser') {
        desktopBrowserRequest.value += 1
        const sessionId = currentSessionId.value || activeChatKey.value
        if (sessionId && capabilities.embeddedBrowser) {
          void selectEmbeddedBrowserSession(sessionId)
            .then(() => activateEmbeddedBrowserSession(sessionId))
            .catch(() => { /* Browser surface reports its own unavailable state. */ })
        }
      }
    },
  })

  const {
    toggle: toggleDesktopCodePanel,
    reviewChanges: reviewCodeChanges,
    openFile: openCodeFile,
  } = useDesktopCodePanel({
    activeKind: () => desktopActiveToolKind.value,
    hasSession: () => Boolean(activeCodeState.value.session),
    reviewPath: desktopCodeReviewPath,
    reviewChanges: desktopCodeReviewChanges,
    filePath: desktopCodeFilePath,
    hide: hideDesktopTools,
    reveal: revealDesktopTool,
    openFile: openDesktopFileTab,
    openDiff: openDesktopDiffTab,
  })

  function requestDesktopBrowser() {
    if (canUseBrowser.value && currentView.value === 'chat') openDesktopTool('browser')
  }

  return {
    desktopBrowserRequest, activeCodeState,
    desktopCodeReviewPath, desktopCodeReviewChanges, desktopCodeFilePath,
    desktopWorkspaceSummary, refreshDesktopWorkspaceSummary,
    desktopAvailableTools, desktopToolTabs, desktopActiveTool,
    desktopActiveToolKind, desktopToolTabsFor, desktopActiveToolFor,
    openDesktopTool, revealDesktopTool, openDesktopFileTab, openDesktopDiffTab, openDesktopPreviewTab,
    selectDesktopTool, closeDesktopTool, hideDesktopTools,
    toggleDesktopCodePanel, reviewCodeChanges, openCodeFile, requestDesktopBrowser,
  }
}
