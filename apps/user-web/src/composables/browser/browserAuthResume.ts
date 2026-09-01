import { consumeBrowserAgentReturn } from './browserAgentReturn'

export type BrowserAuthResumeRecord = {
  suspension_id: string
  run_id: string
  node_id: string
  chat_session_id: string
  browser_session_id: string
  tab_id?: string
  status: 'waiting_human' | 'ready' | 'resuming' | string
  ready_url?: string
}

export async function waitForBrowserAuthReady(input: {
  userId: string
  sessionId: string
  authToken: string
  signal: AbortSignal
}): Promise<BrowserAuthResumeRecord | null> {
  while (!input.signal.aborted) {
    if (consumeBrowserAgentReturn(input.sessionId)) {
      await post('/tasks/browser-auth/manual-ready', {
        user_id: input.userId,
        session_id: input.sessionId,
      }, input.authToken).catch(() => null)
    }
    const query = new URLSearchParams({ user_id: input.userId, session_id: input.sessionId })
    const response = await fetch(`/askai-api/api/tasks/browser-auth/status?${query}`, {
      headers: { Authorization: `Bearer ${input.authToken}` },
      signal: input.signal,
    }).catch(() => null)
    if (response?.ok) {
      const payload = await response.json().catch(() => null)
      const record = payload?.data as BrowserAuthResumeRecord | null
      if (record?.status === 'ready') return record
    }
    await delay(1_500, input.signal)
  }
  return null
}

async function post(path: string, body: Record<string, unknown>, authToken: string): Promise<Response> {
  return await fetch(`/askai-api/api${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${authToken}` },
    body: JSON.stringify(body),
  })
}

async function delay(ms: number, signal: AbortSignal): Promise<void> {
  await new Promise<void>((resolve) => {
    const timer = setTimeout(resolve, ms)
    signal.addEventListener('abort', () => { clearTimeout(timer); resolve() }, { once: true })
  })
}
