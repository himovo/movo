export class ChatStreamConnectionLostError extends Error {
  constructor() {
    super('Chat stream connection lost')
    this.name = 'ChatStreamConnectionLostError'
  }
}

export function heartbeatDeadline(response: Response, controller: AbortController) {
  const interval = Number(response.headers.get('X-Chat-Heartbeat-Seconds'))
  if (!Number.isFinite(interval) || interval <= 0 || interval > 60) return null
  const deadlineMs = interval * 3000
  let timer: ReturnType<typeof setTimeout> | null = null
  let expired = false
  const arm = () => {
    if (timer) clearTimeout(timer)
    timer = setTimeout(() => {
      expired = true
      controller.abort()
    }, deadlineMs)
  }
  arm()
  return {
    received: arm,
    expired: () => expired,
    close: () => { if (timer) clearTimeout(timer) },
  }
}
