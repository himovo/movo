import { createApiClient } from './client'

const api = createApiClient({
  baseURL: '/askai-api/api',
  timeout: 120000,
})

export type ToolType = 'http' | 'mcp'
export type ToolStatus = 'active' | 'disabled'
export type TestStatus = 'untested' | 'passed' | 'failed'

export interface ExternalToolItem {
  id: string
  mainId: string
  scope?: 'user' | 'organization'
  ownerUserId?: string
  name: string
  type: ToolType
  description: string
  usageHint: string
  tags: string[]
  status: ToolStatus
  config: Record<string, any>
  lastTestStatus: TestStatus
  lastTestAt: string
  lastTestMessage: string
  discoveredTools: Array<{ name: string; description: string; inputSchema?: Record<string, any> }>
  createdAt: string
  updatedAt: string
}

export interface ToolPayload {
  name: string
  type: ToolType
  description: string
  usageHint: string
  tags: string[]
  status: ToolStatus
  config: Record<string, any>
}

function params(userId: string | null | undefined, mainId: string | null | undefined) {
  return {
    userId: userId || '',
    mainId: mainId || 'default',
  }
}

function dataOf<T>(res: { data?: any }): T {
  return res.data?.data ?? res.data
}

export async function fetchTools(userId: string, mainId = 'default'): Promise<ExternalToolItem[]> {
  const res = await api.get('/external-tools/my', { params: params(userId, mainId), timeout: 15000 })
  return dataOf<ExternalToolItem[]>(res) || []
}

export async function fetchTool(id: string, userId: string, mainId = 'default'): Promise<ExternalToolItem> {
  const res = await api.get(`/external-tools/my/${id}`, { params: params(userId, mainId) })
  return dataOf<ExternalToolItem>(res)
}

export async function createTool(userId: string, mainId: string, payload: ToolPayload): Promise<ExternalToolItem> {
  const res = await api.post('/external-tools/my', payload, { params: params(userId, mainId), timeout: 90000 })
  return dataOf<ExternalToolItem>(res)
}

export async function updateTool(id: string, userId: string, mainId: string, payload: ToolPayload): Promise<ExternalToolItem> {
  const res = await api.put(`/external-tools/my/${id}`, payload, { params: params(userId, mainId), timeout: 90000 })
  return dataOf<ExternalToolItem>(res)
}

export async function patchTool(id: string, userId: string, mainId: string, payload: Partial<ToolPayload>): Promise<ExternalToolItem> {
  const res = await api.patch(`/external-tools/my/${id}`, payload, { params: params(userId, mainId), timeout: 30000 })
  return dataOf<ExternalToolItem>(res)
}

export async function deleteTool(id: string, userId: string, mainId: string): Promise<{ id: string }> {
  const res = await api.delete(`/external-tools/my/${id}`, { params: params(userId, mainId) })
  return dataOf<{ id: string }>(res)
}

export async function testTool(id: string, userId: string, mainId: string, input: Record<string, any>): Promise<Record<string, any>> {
  const res = await api.post(`/external-tools/my/${id}/test`, { input }, { params: params(userId, mainId), timeout: 90000 })
  return dataOf<Record<string, any>>(res)
}

export async function testDraftTool(userId: string, mainId: string, payload: ToolPayload, input: Record<string, any>): Promise<Record<string, any>> {
  const res = await api.post('/external-tools/test-draft', { tool: payload, input }, { params: params(userId, mainId), timeout: 90000 })
  return dataOf<Record<string, any>>(res)
}

export async function discoverMcpTools(id: string, userId: string, mainId: string): Promise<{ success: boolean; message: string; tools: ExternalToolItem['discoveredTools'] }> {
  const res = await api.post(`/external-tools/my/${id}/discover`, {}, { params: params(userId, mainId), timeout: 90000 })
  return dataOf<{ success: boolean; message: string; tools: ExternalToolItem['discoveredTools'] }>(res)
}

export async function generateToolDescription(payload: {
  name: string
  type: ToolType
  existingDescription?: string
}): Promise<{ description: string }> {
  const res = await api.post('/external-tools/generate-description', payload, { timeout: 90000 })
  return dataOf<{ description: string }>(res)
}
