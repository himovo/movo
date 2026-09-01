import { notifyAuthExpiredFromResponse } from '../../api/authExpiry'
import type { ChatStreamHandle } from '../useChatStream'
import type { ExecutionEventV3 } from '../../features/execution-v3/domain/protocol'

export function startTaskResumeStream(input: {
  runId: string
  suspensionId: string
  nodeId: string
  messages: any[]
  modelId?: string
  signal?: Record<string, any>
}, onEvent: (event: ExecutionEventV3) => void, options: {
  authToken: string
  onAccepted?: () => void
  onMessageId?: (messageId: string) => void
}): ChatStreamHandle {
  const controller = new AbortController()
  const handle: ChatStreamHandle = {
    sessionId: null,
    messageId: null,
    done: Promise.resolve(),
    abort: () => controller.abort(),
  }
  handle.done = (async () => {
    const response = await fetch(`/askai-api/api/tasks/${encodeURIComponent(input.runId)}/resume`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${options.authToken}`,
      },
      body: JSON.stringify({
        suspension_id: input.suspensionId,
        node_id: input.nodeId,
        messages: input.messages,
        model_id: input.modelId || '',
        signal: input.signal || {},
      }),
      signal: controller.signal,
    })
    notifyAuthExpiredFromResponse(response, true)
    if (!response.ok) throw new Error(await responseError(response))
    options.onAccepted?.()
    handle.sessionId = response.headers.get('X-Session-Id')
    handle.messageId = response.headers.get('X-Message-Id')
    if (handle.messageId) options.onMessageId?.(handle.messageId)
    if (!response.body) throw new Error('No response body')
    const reader = response.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n')
      buffer = lines.pop() || ''
      for (const line of lines) emitLine(line, onEvent)
    }
    emitLine(buffer, onEvent)
  })()
  return handle
}

function emitLine(line: string, onEvent: (event: ExecutionEventV3) => void): void {
  const value = line.trim()
  if (!value) return
  try { onEvent(JSON.parse(value) as ExecutionEventV3) } catch { /* ignore malformed transport lines */ }
}

async function responseError(response: Response): Promise<string> {
  try {
    const payload = await response.json()
    return String(payload?.detail?.message || payload?.detail || payload?.message || `Request failed: ${response.status}`)
  } catch {
    return `Request failed: ${response.status}`
  }
}
