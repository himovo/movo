import { nextTick, onBeforeUnmount, onMounted, onUpdated, watch, type ComputedRef, type Ref } from 'vue'
import { normalizeAssistantContent } from '../../utils/assistantMarkdown'
import { ensureScript, renderMermaidBlocks } from './mermaidRendering'
import { renderChartBlocks } from './chartRendering'
import type { ChatMessage } from './chatMessage'
import type { Locale } from '../../locales/messages'

interface Options {
  messages: ComputedRef<ChatMessage[]>
  displayMessages: ComputedRef<ChatMessage[]>
  locale: Ref<Locale>
  mainId: () => string | undefined
  authToken: () => string | undefined
  sessionId: () => string | undefined
  initialMessages: () => ChatMessage[] | undefined
  isLoading: Ref<boolean>
  stickyState: Ref<string>
  stickyNeedsInitialAlign: Ref<boolean>
  handleScroll: () => void
  recomputeStickyTurnMinHeight: () => void
  loadChatModels: () => unknown
  loadPromptGuideShortcuts: () => Promise<unknown>
  handleShortcutPreferencesUpdated: () => void
  startLayoutObserver: () => void
  stopLayoutObserver: () => void
  cancelPromptGuideClose: () => void
  stickyLog: (...args: any[]) => void
  alignStickyAnchorWithRetry: (attempts: number) => Promise<unknown>
  resetBrowserWorkspace: () => void
  resetMessageRefs: () => void
  activateStickyForLatestRunningTurn: () => void
  active: () => boolean
  scrollToLatest: () => Promise<void>
}

export function useChatWindowLifecycle(options: Options): void {
  const debugEnabled = typeof window !== 'undefined' && window.location.search.includes('debug=1')
  const renderContent = () => {
    renderMermaidBlocks()
    renderChartBlocks(options.locale.value, ensureScript)
  }

  watch(options.displayMessages, () => {
    if (!debugEnabled) return
    console.log('[chat-debug]', {
      messagesCount: options.messages.value.length,
      displayCount: options.displayMessages.value.length,
      lastMessageContent: options.messages.value.at(-1)?.content || '',
      lastDisplayContent: options.displayMessages.value.at(-1)?.content || '',
    })
  }, { deep: true })
  watch(() => [...options.messages.value].reverse().find(m => m.role === 'assistant')?.content || '', content => {
    if (!debugEnabled || !content) return
    console.log('[chat-debug] assistant-raw', JSON.stringify(content))
    console.log('[chat-debug] assistant-normalized', JSON.stringify(normalizeAssistantContent(content)))
  })

  onMounted(() => {
    options.handleScroll()
    options.recomputeStickyTurnMinHeight()
    options.loadChatModels()
    void options.loadPromptGuideShortcuts()
    window.addEventListener('shortcut-preferences-updated', options.handleShortcutPreferencesUpdated)
    window.addEventListener('resize', options.recomputeStickyTurnMinHeight)
    options.startLayoutObserver()
    nextTick().then(renderContent)
  })
  let openedSession: string | undefined
  watch(
    [options.sessionId, options.active, () => options.displayMessages.value.length > 0, options.isLoading],
    ([sessionId, active, hasMessages, loading]) => {
      if (!active || sessionId !== openedSession) openedSession = undefined
      if (!active || !sessionId || !hasMessages || loading || openedSession === sessionId) return
      nextTick(() => {
        if (options.active() && options.sessionId() === sessionId && !options.isLoading.value) {
          openedSession = sessionId
          void options.scrollToLatest()
        }
      })
    },
    { immediate: true, flush: 'post' },
  )
  watch(options.mainId, () => {
    options.loadChatModels()
    void options.loadPromptGuideShortcuts()
  })
  watch(options.authToken, () => void options.loadPromptGuideShortcuts())
  onBeforeUnmount(() => {
    options.cancelPromptGuideClose()
    window.removeEventListener('resize', options.recomputeStickyTurnMinHeight)
    window.removeEventListener('shortcut-preferences-updated', options.handleShortcutPreferencesUpdated)
    options.stopLayoutObserver()
  })

  // Coalesce streaming updates into one DOM pass per frame in desktop WebViews.
  let updateScheduled = false
  onUpdated(() => {
    if (updateScheduled) return
    updateScheduled = true
    requestAnimationFrame(() => {
      updateScheduled = false
      options.handleScroll()
      options.recomputeStickyTurnMinHeight()
      nextTick().then(() => {
        if (options.stickyState.value === 'LOCKED' && options.stickyNeedsInitialAlign.value) {
          options.stickyLog('onUpdated triggers alignStickyAnchorWithRetry')
          void options.alignStickyAnchorWithRetry(6)
        }
        renderContent()
        if (!debugEnabled) return
        const nodes = Array.from(document.querySelectorAll('.assistant-content')) as HTMLElement[]
        console.log('[chat-debug] assistant-nodes', {
          count: nodes.length,
          texts: nodes.map(n => n.innerText.trim()).filter(Boolean),
          htmls: nodes.map(n => n.innerHTML.trim()).filter(Boolean),
        })
        nodes.forEach((n, idx) => {
          console.log(`[chat-debug] assistant-node-${idx}-text`, JSON.stringify(n.innerText))
          console.log(`[chat-debug] assistant-node-${idx}-html`, JSON.stringify(n.innerHTML))
          console.log(`[chat-debug] assistant-node-${idx}-children`, n.childNodes.length)
        })
      })
    })
  })

  watch(options.sessionId, (nextId, prevId) => {
    if (nextId === prevId) return
    options.resetBrowserWorkspace()
    options.resetMessageRefs()
  })
  watch(options.initialMessages, nextMessages => {
    if (!nextMessages) return
    options.resetMessageRefs()
    if (options.isLoading.value) options.activateStickyForLatestRunningTurn()
    else if (options.stickyState.value === 'LOCKED') {
      options.stickyNeedsInitialAlign.value = true
      nextTick(() => { void options.alignStickyAnchorWithRetry(6) })
    }
  }, { deep: true })
}
