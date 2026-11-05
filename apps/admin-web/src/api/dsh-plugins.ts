import { apiClient } from './client'

export interface DshPlugin {
  id: string
  name: string
  version: string
  spec: string
  description: string
  tool_names: string[]
  updatedAt?: string | null
  enabled: boolean
  scope: 'organization' | 'personal'
  engine: 'dsh'
  source: string
  archive_id?: string
  availability?: PluginAvailability
}

export interface PluginAvailability {
  status: 'verified' | 'session_exposed' | 'not_exposed' | 'unsupported' | 'unverified' | 'failed'
  reason: string
  checks: Record<string, boolean>
  discovered_tools?: string[]
  session_tools?: string[]
  workspace_required_tools?: string[]
}

type Response<T> = { code: number; data: T }
const path = '/api/dsh-plugins'

export async function listDshPlugins(): Promise<DshPlugin[]> {
  const { data } = await apiClient.get<Response<DshPlugin[]>>(path)
  return data.data
}

export async function installDshPlugin(spec: string): Promise<DshPlugin> {
  const { data } = await apiClient.post<Response<DshPlugin>>(`${path}/install`, { spec }, { timeout: 330000 })
  return data.data
}

export async function uploadDshPlugin(file: File): Promise<DshPlugin> {
  const form = new FormData()
  form.append('file', file)
  const { data } = await apiClient.post<Response<DshPlugin>>(`${path}/upload`, form, { timeout: 330000 })
  return data.data
}

export async function verifyDshPlugin(id: string): Promise<DshPlugin> {
  const { data } = await apiClient.post<Response<DshPlugin>>(`${path}/${encodeURIComponent(id)}/verify`, {}, { timeout: 330000 })
  return data.data
}

export async function setDshPluginEnabled(id: string, enabled: boolean): Promise<DshPlugin> {
  const { data } = await apiClient.patch<Response<DshPlugin>>(`${path}/${encodeURIComponent(id)}/enabled`, { enabled })
  return data.data
}

export async function removeDshPlugin(id: string): Promise<void> {
  await apiClient.delete(`${path}/${encodeURIComponent(id)}`)
}
