import { nextTick, onBeforeUnmount, onMounted, watch, type Ref } from 'vue'
import { shouldAutofocusComposer } from './composerFocusPolicy'

const BLOCKING_OVERLAY_SELECTOR = [
  '[aria-modal="true"]',
  '.n-modal-container',
  '.n-dialog-container',
  '[role="dialog"]',
].join(',')

function isMobileDevice(): boolean {
  const userAgentData = navigator as Navigator & { userAgentData?: { mobile?: boolean } }
  if (userAgentData.userAgentData?.mobile === true) return true
  if (/Android|iPhone|iPad|iPod|Mobile/i.test(navigator.userAgent)) return true
  return window.matchMedia?.('(pointer: coarse) and (max-width: 767px)').matches === true
}

function hasTextSelection(): boolean {
  const selection = window.getSelection?.()
  return Boolean(selection && selection.type === 'Range' && !selection.isCollapsed)
}

export function useComposerAutofocus(
  input: Ref<HTMLTextAreaElement | null>,
  enabled: Ref<boolean>,
): { requestComposerFocus: () => void } {
  let frame = 0
  let replaceCurrentFocus = false

  function cancelScheduledFocus() {
    if (frame) window.cancelAnimationFrame(frame)
    frame = 0
  }

  function focusIfAppropriate() {
    frame = 0
    const shouldReplaceCurrentFocus = replaceCurrentFocus
    replaceCurrentFocus = false
    const target = input.value
    if (!target || !target.isConnected) return
    const allowed = shouldAutofocusComposer(target, enabled.value, {
      activeElement: document.activeElement,
      documentVisible: document.visibilityState !== 'hidden',
      hasBlockingOverlay: Boolean(document.querySelector(BLOCKING_OVERLAY_SELECTOR)),
      hasTextSelection: hasTextSelection(),
      mobileDevice: isMobileDevice(),
    }, shouldReplaceCurrentFocus)
    if (!allowed) return
    target.focus({ preventScroll: true })
  }

  function scheduleComposerFocus(replaceFocus = false) {
    cancelScheduledFocus()
    replaceCurrentFocus = replaceFocus
    void nextTick(() => {
      frame = window.requestAnimationFrame(focusIfAppropriate)
    })
  }

  function requestComposerFocus() {
    scheduleComposerFocus(false)
  }

  function onVisibilityChange() {
    if (document.visibilityState === 'visible') requestComposerFocus()
  }

  onMounted(() => {
    window.addEventListener('focus', requestComposerFocus)
    document.addEventListener('visibilitychange', onVisibilityChange)
    scheduleComposerFocus(true)
  })

  watch(enabled, (active) => {
    if (active) scheduleComposerFocus(true)
    else cancelScheduledFocus()
  })

  onBeforeUnmount(() => {
    cancelScheduledFocus()
    window.removeEventListener('focus', requestComposerFocus)
    document.removeEventListener('visibilitychange', onVisibilityChange)
  })

  return { requestComposerFocus }
}
