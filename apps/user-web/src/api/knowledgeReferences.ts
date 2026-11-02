import { createApiClient } from './client'
export type KnowledgeScope = 'personal' | 'organization'
export type KnowledgeReference = { scope: KnowledgeScope; kind: 'directory' | 'document'; source_id: string; name: string; path?: string; document_id?: string; checksum?: string }
const api = createApiClient({ baseURL: '/askai-api/api', timeout: 30000 })
export async function searchKnowledgeReferences(params: { scope: KnowledgeScope; keyword?: string; directory_id?: string; cursor?: number }, signal?: AbortSignal): Promise<{ items: KnowledgeReference[]; next_cursor: number | null }> {
  return (await api.get('/knowledge/references', { params, signal })).data
}
