import { apiClient } from './client'

export type SandboxRuntimeMode = 'on_demand' | 'forced'

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
  runtime_mode?: SandboxRuntimeMode
}

export async function fetchSandboxStatus(): Promise<SandboxStatus> {
  const { data } = await apiClient.get<SandboxStatus>('/api/settings/sandbox/status')
  return data
}

export async function saveSandboxSettings(settings: {
  capacity: number
  max_pending: number
  plugin_idle_seconds: number
  runtime_mode: SandboxRuntimeMode
}): Promise<void> {
  await apiClient.put('/api/settings/sandbox/settings', settings)
}
