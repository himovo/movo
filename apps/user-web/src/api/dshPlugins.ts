import { createApiClient } from './client'

export interface DshPlugin {
  id: string
  name: string
  version: string
  spec: string
  description: string
  enabled: boolean
  execution_allowed?: boolean
  scope: 'organization' | 'personal'
  engine: 'dsh'
  source: string
  updatedAt?: string
  archive_id?: string
  availability?: PluginAvailability
}

export interface PluginAvailability {
  status: 'verified' | 'session_exposed' | 'runtime_active' | 'not_exposed' | 'unsupported' | 'unverified' | 'failed' | 'version_incompatible'
  reason: string
  error_code?: string
  dsh_version?: string
  plugin_version?: string
  offline_source_dsh_version?: string
  offline_source_dsh_mismatch?: boolean
  checks: Record<string, boolean>
  discovered_tools?: string[]
  session_tools?: string[]
  capabilities?: { skills?: Array<{ name: string; description: string; modelInvocable: boolean; userInvocable: boolean }>; commands?: Array<{ name: string; description: string; definitionId?: string }>; modelProviders?: Array<{ id: string; name: string }>; clientModules?: Array<{ id: string; rev: string; conversationView?: boolean }>; webRoutes?: Array<{ kind: 'exact' | 'prefix'; path: string }>; remoteEndpoints?: string[]; mcpServers?: Array<{ name: string; tools: string[] }>; rows?: Array<{ rowId: string; moduleName: string }>; overrides?: string[] }
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
const api = createApiClient({ baseURL: '/askai-api/api', timeout: 330000 })
const path = '/dsh-plugins/personal'

export async function getPluginExecutionAccess(): Promise<boolean> {
  const { data } = await api.get<Response<{ allowed: boolean }>>(`${path}/execution-access`)
  return data.data.allowed === true
}

export async function listDshPlugins(): Promise<DshPlugin[]> {
  const { data } = await api.get<Response<DshPlugin[]>>(path)
  return data.data
}

export async function installDshPlugin(spec: string): Promise<DshPlugin> {
  const { data } = await api.post<Response<DshPlugin>>(`${path}/install`, { spec })
  return data.data
}

export async function preflightDshPlugin(spec: string): Promise<PluginPreflight> {
  const { data } = await api.post<Response<PluginPreflight>>(`${path}/preflight`, { spec }, { timeout: 120000 })
  return data.data
}

export async function uploadDshPlugin(file: File): Promise<DshPlugin> {
  const form = new FormData()
  form.append('file', file)
  const { data } = await api.post<Response<DshPlugin>>(`${path}/upload`, form)
  return data.data
}

export async function verifyDshPlugin(id: string): Promise<DshPlugin> {
  const { data } = await api.post<Response<DshPlugin>>(`${path}/${encodeURIComponent(id)}/verify`, {})
  return data.data
}

export async function launchDshPluginUi(id: string, conversationId?: string): Promise<{ url: string; kernelSessionId?: string }> {
  const { data } = await api.post<Response<{ url: string; kernelSessionId?: string }>>(
    `${path}/${encodeURIComponent(id)}/ui-launch`, conversationId ? { conversationId } : {},
  )
  return data.data
}

export async function resolveDshPluginUiSession(kernelSessionId: string): Promise<string> {
  const { data } = await api.get<Response<{ conversationId: string }>>(
    `${path}/ui-sessions/${encodeURIComponent(kernelSessionId)}`,
  )
  return data.data.conversationId
}

export async function setDshPluginEnabled(id: string, enabled: boolean): Promise<DshPlugin> {
  const { data } = await api.patch<Response<DshPlugin>>(`${path}/${encodeURIComponent(id)}/enabled`, { enabled })
  return data.data
}

export async function removeDshPlugin(id: string): Promise<void> {
  await api.delete(`${path}/${encodeURIComponent(id)}`)
}
