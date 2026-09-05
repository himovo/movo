import { cancelChat, type ChatStreamHandle } from './useChatStream'

interface CancellationMessage {
  _id?: string
  role: string
  _backendSid?: string
}

export interface StoppableChatPane {
  sessionId: string | null
  messages: CancellationMessage[]
  stopping: boolean
  operationId: number
  activeStream: ChatStreamHandle | null
  abortController: AbortController | null
  authResumeController: AbortController | null
  activeAssistantMessageId: string | null
  activeAuthToken: string | null
}

function releaseStoppedPane(
  pane: StoppableChatPane,
  setRunning: (running: boolean) => void,
  invalidateOperation = false,
) {
  if (invalidateOperation) pane.operationId += 1
  pane.activeStream?.abort()
  pane.abortController?.abort()
  pane.activeStream = null
  pane.abortController = null
  pane.activeAssistantMessageId = null
  pane.activeAuthToken = null
  pane.stopping = false
  setRunning(false)
}

export async function stopChatGeneration(
  pane: StoppableChatPane,
  setRunning: (running: boolean) => void,
): Promise<boolean> {
  if (pane.stopping) return false
  pane.authResumeController?.abort()
  pane.authResumeController = null
  pane.stopping = true
  const handle = pane.activeStream
  if (!handle) {
    // Billing and attachment preflight have not created a server turn yet.
    releaseStoppedPane(pane, setRunning, true)
    return true
  }

  await handle.ready
  const activeAssistant =
    (pane.activeAssistantMessageId
      ? pane.messages.find((message) => message._id === pane.activeAssistantMessageId)
      : null) || [...pane.messages].reverse().find((message) => message.role === 'assistant')
  const conversationId = handle.sessionId || activeAssistant?._backendSid || pane.sessionId || ''
  if (!conversationId) {
    handle.abort()
    await handle.done.catch(() => undefined)
    releaseStoppedPane(pane, setRunning, true)
    return true
  }

  const cancelled = await cancelChat(conversationId, pane.activeAuthToken)
  if (!cancelled) {
    pane.stopping = false
    return false
  }

  await Promise.race([
    handle.done.catch(() => undefined),
    new Promise<void>((resolve) => setTimeout(resolve, 2000)),
  ])
  releaseStoppedPane(pane, setRunning)
  return true
}
