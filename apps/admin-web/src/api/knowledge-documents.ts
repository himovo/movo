import { apiClient } from './client';

export type KnowledgeDocumentStatus = 'uploaded' | 'pending_parse' | 'parsed' | 'indexed' | 'failed';
export type KnowledgeProcessStatus = 'not_started' | 'queued' | 'running' | 'succeeded' | 'failed';

export interface KnowledgeDocumentItem {
  id: string;
  mainId: string;
  directoryId?: string;
  knowledgeBaseId: string;
  name: string;
  description: string;
  originalFilename: string;
  fileExt: string;
  mimeType: string;
  fileSize: number;
  storageType: 'local' | 'oss';
  storageBucket: string;
  storageKey: string;
  checksum: string;
  status: KnowledgeDocumentStatus;
  parseStatus: KnowledgeProcessStatus;
  parseJobId: string;
  parseError: string;
  parseUpdatedAt: string;
  parsedMarkdownKey: string;
  parsedJsonKey: string;
  rawChunksKey: string;
  rawChunkCount: number;
  ragChunksKey: string;
  ragChunkCount: number;
  chunksKey: string;
  chunkCount: number;
  chunkStatus: KnowledgeProcessStatus;
  indexStatus: KnowledgeProcessStatus;
  previewKey: string;
  previewMimeType: string;
  previewStatus: 'not_required' | 'pending' | 'queued' | 'running' | 'succeeded' | 'failed';
  previewJobId: string;
  previewError: string;
  previewUpdatedAt: string;
  tags: string[];
  createdBy: string;
  createdByName: string;
  updatedBy: string;
  updatedByName: string;
  createdAt: string;
  updatedAt: string;
  deletedAt: string;
  metadata: Record<string, any>;
  downloadUrl: string;
  previewUrl: string;
}

export interface KnowledgeDocumentListResponse {
  items: KnowledgeDocumentItem[];
  total: number;
  page: number;
  pageSize: number;
}

export interface KnowledgeDocumentStats {
  total: number;
  indexed: number;
  failed: number;
  local: number;
  oss: number;
  totalSize: number;
}

export interface KnowledgeDocumentChunkItem {
  id: string;
  documentId: string;
  chunkId: string;
  chunkStage: 'raw' | 'rag';
  ordinal: number;
  text: string;
  contextualText: string;
  titlePath: string[];
  pageNo: number | string | null;
  contentType: string;
  sourceChunkIds: string[];
  metadata: Record<string, any>;
  status: string;
  createdAt: string;
  updatedAt: string;
}

export interface KnowledgeDocumentChunkListResponse {
  items: KnowledgeDocumentChunkItem[];
  total: number;
  page: number;
  pageSize: number;
}

export interface KnowledgeDocumentQuery {
  page: number;
  pageSize: number;
  keyword?: string;
  fileType?: string | null;
  statusValue?: string | null;
  storageType?: string | null;
  directoryId?: string | null;
  directoryScopeId?: string | null;
  sortField?: string;
  sortOrder?: 'ascend' | 'descend';
  includeDeleted?: boolean;
}

export interface KnowledgeDocumentChunkQuery {
  page: number;
  pageSize: number;
  keyword?: string;
  contentType?: string | null;
  chunkStage?: 'raw' | 'rag' | 'all';
}

export interface KnowledgeDocumentUpdatePayload {
  name: string;
  description: string;
  directoryId?: string | null;
  knowledgeBaseId: string;
  tags: string[];
  status: KnowledgeDocumentStatus;
}

export async function fetchKnowledgeDocumentStats() {
  const { data } = await apiClient.get<KnowledgeDocumentStats>('/api/knowledge/documents/stats');
  return data;
}

export async function fetchKnowledgeDocuments(query: KnowledgeDocumentQuery) {
  const { data } = await apiClient.get<KnowledgeDocumentListResponse>('/api/knowledge/documents', {
    params: query,
  });
  return data;
}

export async function fetchKnowledgeDocument(id: string) {
  const { data } = await apiClient.get<KnowledgeDocumentItem>(`/api/knowledge/documents/${id}`);
  return data;
}

export async function fetchKnowledgeDocumentChunks(id: string, query: KnowledgeDocumentChunkQuery) {
  const { data } = await apiClient.get<KnowledgeDocumentChunkListResponse>(`/api/knowledge/documents/${id}/chunks`, {
    params: query,
  });
  return data;
}

export async function fetchKnowledgeDocumentChunk(id: string, chunkId: string, chunkStage: 'raw' | 'rag' | 'all' = 'rag') {
  const { data } = await apiClient.get<KnowledgeDocumentChunkItem>(
    `/api/knowledge/documents/${id}/chunks/${encodeURIComponent(chunkId)}`,
    { params: { chunkStage } },
  );
  return data;
}

export async function uploadKnowledgeDocument(formData: FormData, onUploadProgress?: (progress: number) => void) {
  const { data } = await apiClient.post<KnowledgeDocumentItem>('/api/knowledge/documents', formData, {
    timeout: 120000,
    headers: { 'Content-Type': 'multipart/form-data' },
    onUploadProgress: (event) => {
      if (!onUploadProgress || !event.total) {
        return;
      }
      onUploadProgress(Math.round((event.loaded / event.total) * 100));
    },
  });
  return data;
}

export async function updateKnowledgeDocument(id: string, payload: KnowledgeDocumentUpdatePayload) {
  const { data } = await apiClient.put<KnowledgeDocumentItem>(`/api/knowledge/documents/${id}`, payload);
  return data;
}

export async function deleteKnowledgeDocument(id: string) {
  const { data } = await apiClient.delete<{ success: boolean }>(`/api/knowledge/documents/${id}`);
  return data;
}

export async function retryKnowledgeDocumentParse(id: string) {
  const { data } = await apiClient.post<KnowledgeDocumentItem>(`/api/knowledge/documents/${id}/retry-parse`);
  return data;
}

export function knowledgeDocumentContentUrl(id: string) {
  const baseURL = import.meta.env.VITE_ADMIN_API_BASE_URL || '/admin-api';
  return `${baseURL}/api/knowledge/documents/${id}/content`;
}
