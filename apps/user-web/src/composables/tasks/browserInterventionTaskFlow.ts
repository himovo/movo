import { waitForBrowserAuthReady } from '../browser/browserAuthResume'
import { waitForBrowserInterventionReady } from '../browser/browserInterventionResume'
import type { ExecutionEventV3 } from '../../features/execution-v3/domain/protocol'
import type { ChatStreamHandle } from '../useChatStream'
import { startTaskResumeStream } from './taskResume'

type ResumableIntervention = {
  category?: string
  resumable?: boolean
  suspension_id?: string
  run_id?: string
  node_id?: string
  browser_session_id?: string
} | null

export async function resumeBrowserInterventionTaskUntilSettled(input: {
  userId: string
  sessionId: string
  authToken: string
  modelId?: string
  locale: string
  signal: AbortSignal
  getIntervention: () => ResumableIntervention
  getMessages: () => any[]
  setWaitController: (controller: AbortController | null) => void
  setRunning: (running: boolean) => void
  setActiveHandle: (handle: ChatStreamHandle) => void
  clearIntervention: () => void
  onEvent: (event: ExecutionEventV3) => void
  onMessageId: (messageId: string) => void
}): Promise<void> {
  while (!input.signal.aborted) {
    const intervention = input.getIntervention()
    if (!isResumableBrowserIntervention(intervention)) return

    input.setRunning(false)
    const waitController = linkedAbortController(input.signal)
    input.setWaitController(waitController)
    const auth = isAuthCategory(intervention.category)
    const ready = auth
      ? await waitForBrowserAuthReady({
          userId: input.userId,
          sessionId: input.sessionId,
          authToken: input.authToken,
          signal: waitController.signal,
        })
      : await waitForBrowserInterventionReady({
          sessionId: input.sessionId,
          suspensionId: intervention.suspension_id,
          authToken: input.authToken,
          signal: waitController.signal,
        })
    input.setWaitController(null)
    if (!ready?.suspension_id || input.signal.aborted) return

    let accepted = false
    const resumed = startTaskResumeStream({
      runId: ready.run_id,
      suspensionId: ready.suspension_id,
      nodeId: ready.node_id,
      messages: input.getMessages(),
      modelId: input.modelId,
      signal: {
        type: auth ? 'browser_auth_completed' : 'human_intervention_completed',
        ...(!auth && 'ready_signal' in ready && ready.ready_signal ? ready.ready_signal : {}),
        ...('ready_url' in ready && ready.ready_url ? { ready_url: ready.ready_url } : {}),
      },
    }, input.onEvent, {
      authToken: input.authToken,
      onAccepted: () => {
        accepted = true
        input.clearIntervention()
        input.setRunning(true)
        input.onEvent(resumeProgressEvent(ready.run_id, ready.node_id, input.locale, auth))
      },
      onMessageId: input.onMessageId,
    })
    input.setActiveHandle(resumed)
    const abortResume = () => resumed.abort()
    if (input.signal.aborted) abortResume()
    else input.signal.addEventListener('abort', abortResume, { once: true })
    try {
      await resumed.done
    } catch (error) {
      if (!accepted) input.setRunning(false)
      throw error
    } finally {
      input.signal.removeEventListener('abort', abortResume)
    }
  }
}

function isResumableBrowserIntervention(value: ResumableIntervention): value is NonNullable<ResumableIntervention> & {
  suspension_id: string
  run_id: string
  node_id: string
  browser_session_id: string
} {
  return Boolean(
    value?.resumable
    && value.suspension_id
    && value.run_id
    && value.node_id
    && value.browser_session_id,
  )
}

function isAuthCategory(category?: string): boolean {
  return ['login', 'registration', 'authentication'].includes(String(category || '').toLowerCase())
}

function linkedAbortController(parent: AbortSignal): AbortController {
  const controller = new AbortController()
  if (parent.aborted) controller.abort()
  else parent.addEventListener('abort', () => controller.abort(), { once: true })
  return controller
}

function resumeProgressEvent(runId: string, nodeId: string, locale: string, auth: boolean): ExecutionEventV3 {
  const eventId = `browser_resumed_${runId}_${nodeId}_${Date.now()}`
  const message = locale === 'zh'
    ? (auth ? '登录成功，继续执行任务' : '人工操作已完成，继续执行任务')
    : (auth ? 'Login succeeded, resuming task' : 'Human intervention completed, resuming task')
  return {
    v: 3,
    event_id: eventId,
    id: eventId,
    ts: Date.now(),
    type: 'item.completed',
    item_kind: 'commentary',
    item_id: eventId,
    revision: 1,
    payload: { message },
  }
}
