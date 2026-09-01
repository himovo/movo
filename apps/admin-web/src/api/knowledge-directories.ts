import { apiClient } from './client';

export interface KnowledgeDirectoryNode {
  id: string;
  name: string;
  parentId: string | null;
  documentCount: number;
  totalDocumentCount: number;
  children: KnowledgeDirectoryNode[];
}

export interface KnowledgeDirectoryCreatePayload {
  name: string;
  parentId: string | null;
}

export interface KnowledgeDirectoryUpdatePayload {
  name: string;
}

export interface KnowledgeDirectoryMovePayload {
  parentId: string | null;
}

export async function fetchDirectoryTree() {
  const { data } = await apiClient.get<KnowledgeDirectoryNode[]>('/api/knowledge/directories/tree');
  return data;
}

export async function createDirectory(payload: KnowledgeDirectoryCreatePayload) {
  const { data } = await apiClient.post<{ id: string; name: string; parentId: string | null }>(
    '/api/knowledge/directories',
    payload
  );
  return data;
}

export async function updateDirectory(id: string, payload: KnowledgeDirectoryUpdatePayload) {
  const { data } = await apiClient.put<{ id: string; name: string; parentId: string | null }>(
    `/api/knowledge/directories/${id}`,
    payload
  );
  return data;
}

export async function moveDirectory(id: string, payload: KnowledgeDirectoryMovePayload) {
  const { data } = await apiClient.post<{ success: boolean }>(
    `/api/knowledge/directories/${id}/move`,
    payload
  );
  return data;
}

export async function deleteDirectory(id: string) {
  const { data } = await apiClient.delete<{ success: boolean }>(
    `/api/knowledge/directories/${id}`
  );
  return data;
}
