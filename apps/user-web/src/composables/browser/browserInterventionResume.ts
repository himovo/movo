import { consumeBrowserAgentReturnSignal, type BrowserAgentReturnSignal } from './browserAgentReturn'

export type BrowserInterventionResumeRecord = {
  suspension_id: string
  run_id: string
  node_id: string
  status: string
  ready_signal?: Record<string, unknown>
}

export async function waitForBrowserInterventionReady(input: {
  sessionId: string
  suspensionId: string
  authToken: string
  signal: AbortSignal
}): Promise<BrowserInterventionResumeRecord | null> {
  let manualSignal: BrowserAgentReturnSignal | null = null
  while (!input.signal.aborted) {
    manualSignal = consumeBrowserAgentReturnSignal(input.sessionId) || manualSignal
    if (manualSignal) {
      const response = await fetch(
        `/askai-api/api/tasks/suspensions/${encodeURIComponent(input.suspensionId)}/manual-ready`,
        {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            Authorization: `Bearer ${input.authToken}`,
          },
          body: JSON.stringify({
            signal: {
              type: 'human_intervention_completed',
              ...manualSignal,
            },
          }),
          signal: input.signal,
        },
      ).catch(() => null)
      if (response?.ok) {
        const payload = await response.json().catch(() => null)
        const record = payload?.data as BrowserInterventionResumeRecord | null
        if (record?.status === 'ready') return record
      }
    }
    await delay(250, input.signal)
  }
  return null
}

async function delay(ms: number, signal: AbortSignal): Promise<void> {
  await new Promise<void>((resolve) => {
    const timer = setTimeout(resolve, ms)
    signal.addEventListener('abort', () => { clearTimeout(timer); resolve() }, { once: true })
  })
}
