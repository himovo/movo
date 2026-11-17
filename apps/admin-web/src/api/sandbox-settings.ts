import { apiClient } from './client'

export interface SandboxStatus {
  enabled: boolean
  healthy: boolean
  running?: number
  pending?: number
  capacity?: number
  task_capacity?: number
  resident_containers?: number
  max_pending?: number
  plugin_runtimes?: number
  plugin_idle_seconds?: number
}

export async function fetchSandboxStatus(): Promise<SandboxStatus> {
  const { data } = await apiClient.get<SandboxStatus>('/api/settings/sandbox/status')
  return data
}

export async function saveSandboxLimits(capacity: number, maxPending: number): Promise<void> {
  await apiClient.put('/api/settings/sandbox/settings', { capacity, max_pending: maxPending })
}
