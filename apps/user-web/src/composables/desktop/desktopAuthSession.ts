import type { AgentStatus, Settings } from '../../platform/types'

interface TokenStorage {
  getItem(key: string): string | null
  setItem(key: string, value: string): void
}

interface DesktopAuthBridge {
  getSettings(): Promise<Settings>
  updateSettings(settings: Settings): Promise<Settings>
  getAgentStatus(): Promise<AgentStatus>
  stopAgent(): Promise<AgentStatus>
}

export function restoreDesktopAuthToken(
  settings: Settings,
  storage: TokenStorage,
  tokenKey: string,
): string {
  const cachedToken = String(storage.getItem(tokenKey) || '').trim()
  if (cachedToken) return cachedToken

  const persistedToken = String(settings.auth_token || '').trim()
  if (persistedToken) storage.setItem(tokenKey, persistedToken)
  return persistedToken
}

export async function clearDesktopAuthSession(bridge: DesktopAuthBridge): Promise<void> {
  const status = await bridge.getAgentStatus()
  if (status.running) await bridge.stopAgent()

  const settings = await bridge.getSettings()
  if (!settings.auth_token && !settings.user_id) return
  await bridge.updateSettings({
    ...settings,
    auth_token: '',
    user_id: '',
  })
}
