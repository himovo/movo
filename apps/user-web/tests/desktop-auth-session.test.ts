import assert from 'node:assert/strict'
import test from 'node:test'
import { clearDesktopAuthSession, restoreDesktopAuthToken } from '../src/composables/desktop/desktopAuthSession'
import type { AgentStatus, Settings } from '../src/platform/types'

const settings = (overrides: Partial<Settings> = {}): Settings => ({
  service_url: 'https://movo.example.com',
  server_configured: true,
  backend_url: 'https://movo.example.com/askai-api',
  agent_ws_url: 'wss://movo.example.com/api/agent/connect',
  user_id: 'user-1',
  auth_token: 'persisted-token',
  auto_start_agent: true,
  language: 'zh',
  timezone: 'Asia/Shanghai',
  ...overrides,
})

const agentStatus = (running: boolean): AgentStatus => ({
  running,
  ws_url: '',
  user_id: running ? 'user-1' : '',
  local_control_url: '',
  local_control_token: '',
})

test('restores the desktop token when a new local UI origin has empty storage', () => {
  const values = new Map<string, string>()
  const storage = {
    getItem: (key: string) => values.get(key) || null,
    setItem: (key: string, value: string) => values.set(key, value),
  }

  assert.equal(restoreDesktopAuthToken(settings(), storage, 'auth_token'), 'persisted-token')
  assert.equal(values.get('auth_token'), 'persisted-token')
})

test('does not overwrite a token already stored by the current UI origin', () => {
  const values = new Map([['auth_token', 'current-origin-token']])
  const storage = {
    getItem: (key: string) => values.get(key) || null,
    setItem: (key: string, value: string) => values.set(key, value),
  }

  assert.equal(restoreDesktopAuthToken(settings(), storage, 'auth_token'), 'current-origin-token')
  assert.equal(values.get('auth_token'), 'current-origin-token')
})

test('stops the desktop agent and clears persisted identity on logout', async () => {
  let current = settings()
  const calls: string[] = []
  const bridge = {
    getSettings: async () => current,
    updateSettings: async (next: Settings) => {
      calls.push('update')
      current = next
      return current
    },
    getAgentStatus: async () => agentStatus(true),
    stopAgent: async () => {
      calls.push('stop')
      return agentStatus(false)
    },
  }

  await clearDesktopAuthSession(bridge)

  assert.deepEqual(calls, ['stop', 'update'])
  assert.equal(current.auth_token, '')
  assert.equal(current.user_id, '')
  assert.equal(current.backend_url, 'https://movo.example.com/askai-api')
})
