import { createApiClient } from './client'

const client = createApiClient({
  baseURL: '/askai-api',
  timeout: 15000,
})

export interface ChatModelOption {
  id: string
  displayName: string
  modelName: string
  providerName: string
  providerType: string
  runtimeKind?: string
  capabilities?: string[]
  isDefault: boolean
  healthStatus: string
}

export async function fetchChatModels(mainId = 'default'): Promise<ChatModelOption[]> {
  const response = await client.get('/api/models/available', { params: { main_id: mainId, capability: 'chat' } })
  return Array.isArray(response.data) ? response.data : response.data?.data || []
}

export async function fetchImageModels(mainId = 'default'): Promise<ChatModelOption[]> {
  const response = await client.get('/api/models/images/available', { params: { main_id: mainId } })
  return Array.isArray(response.data) ? response.data : response.data?.data || []
}
