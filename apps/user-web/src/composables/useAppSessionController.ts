import { watch, type Ref } from 'vue'
import type { SessionSummary } from '../api/sessions'
import type { SessionLiveAccessRevokedReason } from './useSessionLiveStream'
import type { useChatRuntimeStore } from './useChatRuntimeStore'
import type { useDshCodeRuntime } from './code/useDshCodeRuntime'
import { t } from './i18n'

type ChatRuntime = ReturnType<typeof useChatRuntimeStore>
type CodeRuntime = ReturnType<typeof useDshCodeRuntime>

export function useAppSessionController(options: {
  chatRuntime: ChatRuntime
  codeRuntime: CodeRuntime
  sharedSessions: Ref<SessionSummary[]>
  canUseCode: () => boolean
  authToken: () => string
  userId: () => string | null
  mainId: () => string
  syncDesktopIdentity: (token: string, userId: string) => Promise<boolean>
  navigateToChat: () => void
  closeSessionSearch: () => void
  refreshSessionSummaries: () => Promise<unknown>
  refreshSharedSummaries: () => Promise<unknown>
  loadSessions: () => Promise<unknown>
  loadSharedSessions: () => Promise<unknown>
  showRefreshError: (message: string) => void
  showAccessLostNotice: (message: string) => void
}) {
  const { chatRuntime, codeRuntime, sharedSessions } = options

  function startLocalSession(settings: { shouldNavigate?: boolean; inheritCurrentProject?: boolean } = {}): void {
    const sourceKey = settings.inheritCurrentProject ? chatRuntime.activeChatKey.value : ''
    const pane = chatRuntime.startLocalSession()
    if (options.canUseCode() && sourceKey) codeRuntime.inheritDraftProject(sourceKey, pane.key)
    if (settings.shouldNavigate !== false) options.navigateToChat()
    options.closeSessionSearch()
  }

  async function selectSession(sessionId: string): Promise<void> {
    const userId = options.userId()
    if (!userId) return
    if (chatRuntime.currentSessionId.value === sessionId) {
      options.navigateToChat()
      return
    }
    // Clear a shared row's unread marker immediately; the server read cursor
    // catches up when selectSession fetches the conversation.
    if (sharedSessions.value.some(session => session.id === sessionId && session.shared_unread)) {
      sharedSessions.value = sharedSessions.value.map(session => (
        session.id === sessionId ? { ...session, shared_unread: false } : session
      ))
    }
    const pane = await chatRuntime.selectSession(sessionId, userId, options.mainId(), options.authToken() || null)
    options.navigateToChat()
    if (options.canUseCode() && pane.codeProject?.workspace_id && !codeRuntime.stateFor(pane.key).session) {
      codeRuntime.beginRestore(pane.key)
      try {
        const identityReady = await options.syncDesktopIdentity(options.authToken(), userId)
        if (identityReady) await codeRuntime.attach(pane.key, sessionId)
      } finally {
        codeRuntime.finishRestore(pane.key)
      }
    }
    options.closeSessionSearch()
  }

  async function refreshOpenSession(sessionId: string): Promise<void> {
    const userId = options.userId()
    if (!userId) return
    try {
      await chatRuntime.refreshSession(sessionId, userId, options.mainId(), options.authToken() || null)
      await Promise.all([options.refreshSessionSummaries(), options.refreshSharedSummaries()])
    } catch {
      options.showRefreshError(t('session.run.refresh_failed'))
    }
  }

  function handleSessionLeft(sessionId: string): void {
    chatRuntime.removeSession(sessionId)
    void options.loadSessions().catch(() => {})
    void options.loadSharedSessions().catch(() => {})
  }

  function accessLostNoticeMessage(reason: SessionLiveAccessRevokedReason | null): string {
    const generic = t('app.accessRevoked')
    switch (reason) {
      case 'participant_left':
        return t('session.share.left')
      case 'participant_removed':
      case null:
        return generic
      default: {
        const exhaustive: never = reason
        void exhaustive
        return generic
      }
    }
  }

  function handlePaneAccessLost(paneKey: string): void {
    const pane = chatRuntime.panes.value.find(item => item.key === paneKey)
    if (!pane?.sessionId) return
    const { sessionId, accessLostReason } = pane
    chatRuntime.removeSession(sessionId)
    sharedSessions.value = sharedSessions.value.filter(session => session.id !== sessionId)
    options.showAccessLostNotice(accessLostNoticeMessage(accessLostReason))
  }

  const accessLostHandledPanes = new Set<string>()
  watch(
    () => chatRuntime.panes.value.filter(pane => pane.accessLost).map(pane => pane.key),
    lostPaneKeys => {
      const livePaneKeys = new Set(chatRuntime.panes.value.map(pane => pane.key))
      for (const handledKey of accessLostHandledPanes) {
        if (!livePaneKeys.has(handledKey)) accessLostHandledPanes.delete(handledKey)
      }
      for (const paneKey of lostPaneKeys) {
        if (accessLostHandledPanes.has(paneKey)) continue
        accessLostHandledPanes.add(paneKey)
        handlePaneAccessLost(paneKey)
      }
    },
  )

  return { startLocalSession, selectSession, refreshOpenSession, handleSessionLeft }
}
