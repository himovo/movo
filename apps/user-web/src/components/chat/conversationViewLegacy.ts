const PREFIX = 'movo:conversation-view:'
const EVENT = 'movo:conversation-view-probe'

export function cachedConversationView(key: string): boolean | undefined {
  try {
    const raw = sessionStorage.getItem(PREFIX + key)
    if (!raw) return undefined
    const value = JSON.parse(raw) as { available: boolean; checkedAt: number }
    if (typeof value.available === 'boolean' && Date.now() - value.checkedAt < 30 * 60 * 1000) return value.available
  } catch { /* Unavailable cache entries are checked again. */ }
  return undefined
}

export function rememberConversationView(key: string, available: boolean): void {
  try { sessionStorage.setItem(PREFIX + key, JSON.stringify({ available, checkedAt: Date.now() })) }
  catch { /* Storage is optional. */ }
}

export function probeLegacyConversationView(launchUrl: string): Promise<boolean | undefined> {
  return new Promise(resolve => {
    const url = new URL(launchUrl)
    url.searchParams.set('probe', 'conversation-view')
    const frame = document.createElement('iframe')
    frame.setAttribute('aria-hidden', 'true')
    frame.tabIndex = -1
    frame.style.cssText = 'position:absolute;width:0;height:0;border:0;opacity:0;pointer-events:none'
    let finished = false
    const finish = (value: boolean | undefined) => {
      if (finished) return
      finished = true
      window.removeEventListener('message', onMessage)
      clearTimeout(timer)
      frame.remove()
      resolve(value)
    }
    const onMessage = (event: MessageEvent) => {
      if (event.source !== frame.contentWindow || event.origin !== url.origin) return
      if (event.data?.type === EVENT && Number.isInteger(event.data.count)) finish(event.data.count > 0)
    }
    const timer = window.setTimeout(() => finish(undefined), 12000)
    window.addEventListener('message', onMessage)
    frame.onerror = () => finish(undefined)
    frame.src = url.toString()
    document.body.appendChild(frame)
  })
}
