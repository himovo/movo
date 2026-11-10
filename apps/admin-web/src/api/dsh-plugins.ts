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
  status: 'verified' | 'session_exposed' | 'runtime_active' | 'not_exposed' | 'unsupported' | 'unverified' | 'failed' | 'version_incompatible'
  reason: string
  dsh_version?: string
  plugin_version?: string
  offline_source_dsh_version?: string
  offline_source_dsh_mismatch?: boolean
  checks: Record<string, boolean>
  discovered_tools?: string[]
  session_tools?: string[]
  workspace_required_tools?: string[]
  capabilities?: { skills?: Array<{ name: string; description: string; modelInvocable: boolean; userInvocable: boolean }>; commands?: Array<{ name: string; description: string; definitionId?: string }>; modelProviders?: Array<{ id: string; name: string }>; clientModules?: Array<{ id: string; rev: string }>; mcpServers?: Array<{ name: string; tools: string[] }>; rows?: Array<{ rowId: string; moduleName: string }>; overrides?: string[] }
}

export interface PluginPreflight {
  spec: string
  dshVersion: string
  lockedVersion: string
  offlineSourceDshVersion?: string | null
  status: 'pending_runtime_validation' | 'unverified' | 'refused'
  name?: string
  version?: string
  description?: string
  kind?: string
  registry?: string
  problem?: string
  diagnostic?: string
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

export async function preflightDshPlugin(spec: string): Promise<PluginPreflight> {
  const { data } = await apiClient.post<Response<PluginPreflight>>(`${path}/preflight`, { spec }, { timeout: 120000 })
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
