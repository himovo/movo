export type BrowserAgentReturnSignal = {
  media_completed_candidate_ids?: string[]
  human_outcome?: 'completed' | 'unable' | 'succeeded' | 'failed' | 'uncertain' | 'task_completed' | 'continue_agent'
  assistance_contract?: Record<string, unknown>
}

const pendingReturns = new Map<string, { at: number; signal: BrowserAgentReturnSignal }>()
const MAX_PENDING_AGE_MS = 60_000

export function notifyBrowserAgentReturned(
  sessionId: string,
  signal: BrowserAgentReturnSignal = {},
): void {
  const key = String(sessionId || '').trim()
  if (key) pendingReturns.set(key, { at: Date.now(), signal })
}

export function consumeBrowserAgentReturn(sessionId: string): boolean {
  return consumeBrowserAgentReturnSignal(sessionId) !== null
}

export function consumeBrowserAgentReturnSignal(
  sessionId: string,
): BrowserAgentReturnSignal | null {
  const key = String(sessionId || '').trim()
  const pending = pendingReturns.get(key)
  if (!pending) return null
  pendingReturns.delete(key)
  return Date.now() - pending.at <= MAX_PENDING_AGE_MS ? pending.signal : null
}
