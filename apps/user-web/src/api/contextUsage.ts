import { createApiClient } from './client'

const api = createApiClient({ baseURL: '/askai-api/api', timeout: 30000 })

export interface ContextUsage {
  available: boolean
  usedTokens?: number
  capacityTokens?: number | null
  estimated?: boolean
  compacting?: boolean
  modelInstanceId?: string
  modelName?: string
  reason?: 'no_runtime_session' | 'runtime_unavailable' | 'binding_changed'
}

export async function fetchContextUsage(sessionId: string, signal: AbortSignal): Promise<ContextUsage> {
  const response = await api.get(`/sessions/${encodeURIComponent(sessionId)}/context`, { signal })
  return response.data
}
