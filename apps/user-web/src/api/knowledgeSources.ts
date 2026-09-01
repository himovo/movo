import { notifyAuthExpiredFromResponse } from './authExpiry'

export interface KnowledgeSourceDocument {
  id: string
  name: string
  originalFilename: string
  fileExt: string
  mimeType: string
  previewMimeType: string
  previewStatus: string
  chunkCount: number
}

export interface KnowledgeSourceChunk {
  id: string
  documentId: string
  chunkId: string
  chunkStage: string
  ordinal: number
  text: string
  contextualText: string
  titlePath: string[]
  pageNo: number | string | null
  contentType: string
  sourceChunkIds: string[]
  metadata: Record<string, any>
}

function authHeaders(token?: string | null): Record<string, string> {
  return token ? { Authorization: `Bearer ${token}` } : {}
}

async function readJson<T>(url: string, token?: string | null): Promise<T> {
  const resp = await fetch(url, { headers: authHeaders(token) })
  notifyAuthExpiredFromResponse(resp, Boolean(token))
  if (!resp.ok) throw new Error(`Request failed: ${resp.status}`)
  return resp.json() as Promise<T>
}

export function knowledgeSourcePreviewUrl(documentId: string): string {
  return `/askai-api/api/knowledge/sources/documents/${encodeURIComponent(documentId)}/preview`
}

export async function fetchKnowledgeSourceDocument(documentId: string, token?: string | null) {
  return readJson<KnowledgeSourceDocument>(
    `/askai-api/api/knowledge/sources/documents/${encodeURIComponent(documentId)}`,
    token,
  )
}

export async function fetchKnowledgeSourceChunk(documentId: string, chunkId: string, token?: string | null) {
  return readJson<KnowledgeSourceChunk>(
    `/askai-api/api/knowledge/sources/documents/${encodeURIComponent(documentId)}/chunks/${encodeURIComponent(chunkId)}`,
    token,
  )
}

export async function fetchKnowledgeSourcePreview(documentId: string, token?: string | null) {
  const resp = await fetch(knowledgeSourcePreviewUrl(documentId), { headers: authHeaders(token) })
  notifyAuthExpiredFromResponse(resp, Boolean(token))
  if (!resp.ok) throw new Error(`Request failed: ${resp.status}`)
  return resp.blob()
}
