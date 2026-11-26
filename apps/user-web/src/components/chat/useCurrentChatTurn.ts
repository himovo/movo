import { ref, watch } from 'vue'

export function useCurrentChatTurn(container: () => HTMLElement | null, messageCount: () => number) {
  const current = ref<number>()
  watch([container, messageCount], ([element], _, onCleanup) => {
    if (!element) {
      current.value = undefined
      return
    }
    let frame = 0
    function update() {
      frame = 0
      if (!element || !element.clientHeight) return
      const anchors = element.querySelectorAll<HTMLElement>('[data-chat-turn-index]')
      if (!anchors.length) {
        current.value = undefined
        return
      }
      const remaining = element.scrollHeight - element.clientHeight - element.scrollTop
      let low = 0
      let high = anchors.length
      const readingLine = element.getBoundingClientRect().top + 24
      while (low < high) {
        const middle = Math.floor((low + high) / 2)
        if (anchors[middle].getBoundingClientRect().top <= readingLine) low = middle + 1
        else high = middle
      }
      const atBottom = element.scrollTop > 0 && remaining <= 2
      current.value = Number(anchors[atBottom ? anchors.length - 1 : Math.max(0, low - 1)].dataset.chatTurnIndex)
    }
    function schedule() {
      if (!frame) frame = requestAnimationFrame(update)
    }
    element.addEventListener('scroll', schedule, { passive: true })
    const observer = new ResizeObserver(schedule)
    observer.observe(element)
    if (element.firstElementChild) observer.observe(element.firstElementChild)
    schedule()
    onCleanup(() => {
      element.removeEventListener('scroll', schedule)
      observer.disconnect()
      if (frame) cancelAnimationFrame(frame)
    })
  }, { immediate: true, flush: 'post' })
  return current
}
