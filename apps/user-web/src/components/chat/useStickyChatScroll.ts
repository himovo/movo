import { nextTick, ref, watch, type ComputedRef, type Ref } from 'vue'

type StickyMessage = {
  role: 'user' | 'assistant'
  content: string
  _id?: string
  documents?: unknown[]
  progress?: unknown[]
}

export function useStickyChatScroll<T extends StickyMessage>(options: {
  messages: ComputedRef<T[]>
  displayMessages: ComputedRef<T[]>
  isLoading: Ref<boolean>
  messagesContainer: Ref<HTMLElement | null>
  composerContainer: Ref<HTMLElement | null>
}) {
  const { messages, displayMessages, isLoading, messagesContainer, composerContainer } = options
  const msgElements = ref<Record<string, HTMLElement>>({})
  const showScrollButton = ref(false)
  const isProgrammaticScroll = ref(false)

  const stickyDebugEnabled = typeof window !== 'undefined' && window.location.search.includes('sticky_debug=1')

  // Sticky-top state management
  const stickyState = ref<'UNLOCKED' | 'LOCKED' | 'MANUAL_SCROLL'>('UNLOCKED')
  const stickyUserMsgId = ref<string | null>(null)
  const stickyAssistantMsgId = ref<string | null>(null)
  const stickySpacerHeight = ref(0)
  const scrollLockUntil = ref(0)
  const stickyNeedsInitialAlign = ref(false)
  const stickyHoldUntil = ref(0)
  const userScrollIntentUntil = ref(0)
  let scrollTimeout: ReturnType<typeof setTimeout> | null = null
  let stickyFollowRaf: number | null = null
  let layoutRaf: number | null = null
  let layoutObserver: ResizeObserver | null = null
  const stickyTurnMinHeightPx = ref(0)

  function stickyLog(...args: any[]) {
    if (!stickyDebugEnabled) return
    console.log('[Sticky]', ...args)
  }

  function markUserScrollIntent() {
    userScrollIntentUntil.value = Date.now() + 1200
  }

  function recomputeStickyTurnMinHeight() {
    if (layoutRaf !== null) cancelAnimationFrame(layoutRaf)
    layoutRaf = requestAnimationFrame(() => {
      layoutRaf = null
      if (!messagesContainer.value) return
      const containerTop = messagesContainer.value.getBoundingClientRect().top
      const composerHeight = composerContainer.value?.getBoundingClientRect().height || 0
      const viewportHeight = window.innerHeight || document.documentElement.clientHeight || 0
      const bottomGap = 12
      const available = Math.max(0, Math.floor(viewportHeight - containerTop - composerHeight - bottomGap))
      stickyTurnMinHeightPx.value = available
    })
  }

  function stopStickyFollow() {
    if (stickyFollowRaf !== null) {
      cancelAnimationFrame(stickyFollowRaf)
      stickyFollowRaf = null
    }
  }

  function startStickyFollow() {
    // no-op: keep for compatibility during refactor
    stopStickyFollow()
  }

  function findLatestUserAssistantPair(): { userId: string; assistantId: string | null } | null {
    for (let i = messages.value.length - 1; i >= 0; i -= 1) {
      const m = messages.value[i]
      if (m.role !== 'user' || !m._id) continue
      const next = messages.value[i + 1]
      const assistantId = next && next.role === 'assistant' ? (next._id || null) : null
      return { userId: m._id, assistantId }
    }
    return null
  }

  function activateStickyForLatestRunningTurn() {
    if (!isLoading.value) return
    const pair = findLatestUserAssistantPair()
    if (!pair?.assistantId) return
    if (stickyState.value === 'LOCKED' && stickyUserMsgId.value === pair.userId && stickyAssistantMsgId.value === pair.assistantId) {
      return
    }
    stickyState.value = 'LOCKED'
    scrollLockUntil.value = Date.now() + 1500
    stickyHoldUntil.value = Date.now() + 1200
    stickyUserMsgId.value = pair.userId
    stickyAssistantMsgId.value = pair.assistantId
    stickyNeedsInitialAlign.value = true
    nextTick(() => {
      void alignStickyAnchorWithRetry(10)
    })
  }

  function ensureStickyAnchorBound(): boolean {
    if (stickyState.value !== 'LOCKED') return false
    const currentUserId = stickyUserMsgId.value
    if (currentUserId && msgElements.value[currentUserId]) return true
    const pair = findLatestUserAssistantPair()
    if (!pair) return false
    stickyUserMsgId.value = pair.userId
    stickyAssistantMsgId.value = pair.assistantId
    stickyNeedsInitialAlign.value = true
    stickyLog('rebind sticky anchor', pair)
    return !!msgElements.value[pair.userId]
  }


  // Watch AI content changes to update spacer height
  watch(
    () => {
      if (stickyState.value !== 'LOCKED' || !stickyAssistantMsgId.value) return null
      const aiMsg = messages.value.find((m) => m._id === stickyAssistantMsgId.value)
      return aiMsg?.content || ''
    },
    () => {
      if (stickyState.value === 'LOCKED') {
        nextTick(() => updateSpacerHeight())
      }
    }
  )


  // Ensure refs are stored in order
  function setMsgRef(el: any, msgId: string) {
    if (!msgId) return
    if (el) {
      msgElements.value[msgId] = el as HTMLElement
    } else {
      delete msgElements.value[msgId]
    }
  }

  // Scroll handling
  function handleScroll() {
    if (!messagesContainer.value) return
    if (isProgrammaticScroll.value) return
    const container = messagesContainer.value
    const remainingScroll = container.scrollHeight - (container.scrollTop + container.clientHeight)

    const stickyAssistantMsg =
      stickyAssistantMsgId.value
        ? displayMessages.value.find((m) => m._id === stickyAssistantMsgId.value)
        : null
    const stickyAssistantHasRenderableContent = !!(
      stickyAssistantMsg &&
      (
        (stickyAssistantMsg.content && stickyAssistantMsg.content.trim().length > 0) ||
        (stickyAssistantMsg.documents && stickyAssistantMsg.documents.length > 0) ||
        (stickyAssistantMsg.progress && stickyAssistantMsg.progress.length > 0)
      )
    )

    if (stickyState.value === 'LOCKED') {
      // In LOCKED mode, arrow visibility must be based ONLY on current assistant real content,
      // not on scrollHeight (which includes min-height shell).
      if (!stickyAssistantHasRenderableContent) {
        showScrollButton.value = false
      } else if (stickyAssistantMsgId.value) {
        const stickyAssistantEl = msgElements.value[stickyAssistantMsgId.value]
        if (stickyAssistantEl) {
          const containerRect = container.getBoundingClientRect()
          const contentProbe =
            (stickyAssistantEl.querySelector('.assistant-content') as HTMLElement | null)
            || (stickyAssistantEl.firstElementChild as HTMLElement | null)
            || stickyAssistantEl
          const probeRect = contentProbe.getBoundingClientRect()
          showScrollButton.value = probeRect.bottom > (containerRect.bottom + 16)
        } else {
          showScrollButton.value = false
        }
      } else {
        showScrollButton.value = false
      }
    } else {
      // Normal mode.
      showScrollButton.value = remainingScroll > 16
      const lastMsgId = displayMessages.value[displayMessages.value.length - 1]?._id
      const lastMsg = lastMsgId ? msgElements.value[lastMsgId] : null
      if (lastMsg && remainingScroll <= 1) {
        const rect = lastMsg.getBoundingClientRect()
        const containerRect = container.getBoundingClientRect()
        const isLastMsgVisible = rect.top < containerRect.bottom && rect.bottom > containerRect.top
        showScrollButton.value = !isLastMsgVisible
      }
    }

    // Detect user manual scrolling in LOCKED state
    if (stickyState.value === 'LOCKED') {
      if (scrollTimeout) clearTimeout(scrollTimeout)
      scrollTimeout = setTimeout(() => {
        // Sticky state may have changed while timer was waiting.
        if (stickyState.value !== 'LOCKED') return
        // If within lock period, ignore this scroll event
        if (Date.now() < scrollLockUntil.value) {
          stickyLog('Scroll ignored due to lock')
          return
        }
        // Only user-driven scroll should unlock sticky mode.
        if (Date.now() > userScrollIntentUntil.value) {
          stickyLog('Scroll ignored (no user intent)')
          return
        }

        stickyLog('Detected manual scroll, unlock to MANUAL_SCROLL')
        stickyState.value = 'MANUAL_SCROLL'
      }, 100)
    }
  }

  // Sticky-top helper functions
  function unlockSticky() {
    stopStickyFollow()
    if (scrollTimeout) {
      clearTimeout(scrollTimeout)
      scrollTimeout = null
    }
    stickyLog('unlockSticky', {
      state: stickyState.value,
      userId: stickyUserMsgId.value,
      assistantId: stickyAssistantMsgId.value,
    })
    stickyState.value = 'UNLOCKED'
    stickySpacerHeight.value = 0
    stickyUserMsgId.value = null
    stickyAssistantMsgId.value = null
    userScrollIntentUntil.value = 0
  }

  function updateSpacerHeight() {
    if (stickyState.value !== 'LOCKED' || !stickyUserMsgId.value) return
    ensureStickyAnchorBound()

    const userMsgEl = msgElements.value[stickyUserMsgId.value]
    const aiMsgEl = stickyAssistantMsgId.value ? msgElements.value[stickyAssistantMsgId.value] : undefined

    if (!userMsgEl || !messagesContainer.value) {
      stickyLog('updateSpacerHeight skipped', {
        hasUserEl: !!userMsgEl,
        hasContainer: !!messagesContainer.value,
        userId: stickyUserMsgId.value,
        assistantId: stickyAssistantMsgId.value,
      })
      return
    }

    const viewportHeight = messagesContainer.value.clientHeight
    const userMsgHeight = userMsgEl.offsetHeight
    const aiMsgHeight = aiMsgEl?.offsetHeight || 0

    // If the AI reply exceeds the viewport, unlock scrolling and move to the bottom.
    if (aiMsgHeight >= viewportHeight - userMsgHeight - 100) {
      // Content has reached the lower viewport bound.
      // Keep sticky state, but collapse spacer to zero instead of unlocking immediately.
      // This avoids "flash unlock" before users can perceive sticky-top behavior.
      stickySpacerHeight.value = 0
      stickyLog('ai exceeds viewport, collapse spacer', {
        aiMsgHeight,
        viewportHeight,
        userMsgHeight,
      })
      return
    }

    // Otherwise, adjust the placeholder height.
    const newHeight = Math.max(0, viewportHeight - userMsgHeight - aiMsgHeight - 60)
    stickySpacerHeight.value = newHeight
  }

  function scrollToUserMessage(): boolean {
    if (!stickyUserMsgId.value) {
      stickyLog('scrollToUserMessage failed: missing stickyUserMsgId')
      return false
    }
    ensureStickyAnchorBound()
    const userMsgEl = msgElements.value[stickyUserMsgId.value]
    if (!userMsgEl || !messagesContainer.value) {
      stickyLog('scrollToUserMessage failed: missing el/container', {
        hasUserEl: !!userMsgEl,
        hasContainer: !!messagesContainer.value,
        userId: stickyUserMsgId.value,
      })
      return false
    }

    // Set lock for 1 second
    scrollLockUntil.value = Date.now() + 1000

    const targetTop = Math.max(0, userMsgEl.offsetTop - 8)
    isProgrammaticScroll.value = true
    messagesContainer.value.scrollTop = targetTop
    requestAnimationFrame(() => {
      isProgrammaticScroll.value = false
    })
    return true
  }

  async function alignStickyAnchorWithRetry(maxTries = 8) {
    stickyLog('alignStickyAnchorWithRetry start', {
      maxTries,
      state: stickyState.value,
      userId: stickyUserMsgId.value,
      assistantId: stickyAssistantMsgId.value,
    })
    for (let i = 0; i < maxTries; i += 1) {
      await nextTick()
      const ok = scrollToUserMessage()
      if (ok) {
        updateSpacerHeight()
        stickyNeedsInitialAlign.value = false
        stickyLog('alignStickyAnchorWithRetry success', { attempt: i + 1 })
        return true
      }
      stickyLog('alignStickyAnchorWithRetry retry', { attempt: i + 1 })
      await new Promise((resolve) => requestAnimationFrame(() => resolve(true)))
    }
    stickyLog('alignStickyAnchorWithRetry failed', {
      state: stickyState.value,
      userId: stickyUserMsgId.value,
      assistantId: stickyAssistantMsgId.value,
    })
    return false
  }



  function assistantTurnStyle(msg: T) {
    if (stickyState.value !== 'LOCKED') return undefined
    if (!stickyAssistantMsgId.value || msg._id !== stickyAssistantMsgId.value) return undefined
    const minH = stickyTurnMinHeightPx.value
    if (!minH) return undefined
    // Auto-computed from viewport/header/composer layout.
    return { minHeight: `${minH}px` }
  }

  async function scrollToBottom(behavior: ScrollBehavior = 'smooth') {
    // Arrow click is an explicit user action to leave sticky mode.
    if (stickyState.value === 'LOCKED') {
      unlockSticky()
      await nextTick()
    }
    if (messagesContainer.value) {
      isProgrammaticScroll.value = true
      messagesContainer.value.scrollTo({
        top: messagesContainer.value.scrollHeight,
        behavior,
      })
      setTimeout(() => {
        isProgrammaticScroll.value = false
      }, 500)
    }
  }

  async function scrollToTurn(index: number) {
    if (stickyState.value === 'LOCKED') {
      unlockSticky()
      await nextTick()
    }
    const container = messagesContainer.value
    const target = container?.querySelector(`[data-chat-turn-index="${index}"]`)
    if (!container || !target) return
    const offset = target.getBoundingClientRect().top - container.getBoundingClientRect().top
    container.scrollTo({ top: container.scrollTop + offset - 16 })
  }


  function startLayoutObserver(): void {
    if (typeof ResizeObserver === 'undefined') return
    layoutObserver = new ResizeObserver(() => recomputeStickyTurnMinHeight())
    if (messagesContainer.value) layoutObserver.observe(messagesContainer.value)
    if (composerContainer.value) layoutObserver.observe(composerContainer.value)
  }

  function stopLayoutObserver(): void {
    if (layoutObserver) {
      layoutObserver.disconnect()
      layoutObserver = null
    }
    if (layoutRaf !== null) {
      cancelAnimationFrame(layoutRaf)
      layoutRaf = null
    }
  }

  function resetMessageRefs(): void {
    msgElements.value = {}
    showScrollButton.value = false
  }

  return {
    msgElements, showScrollButton, stickyState, stickyAssistantMsgId,
    stickyNeedsInitialAlign, markUserScrollIntent, recomputeStickyTurnMinHeight,
    stickyLog, activateStickyForLatestRunningTurn, setMsgRef, handleScroll,
    alignStickyAnchorWithRetry, assistantTurnStyle, scrollToBottom, scrollToTurn,
    startLayoutObserver, stopLayoutObserver, resetMessageRefs,
  }
}
