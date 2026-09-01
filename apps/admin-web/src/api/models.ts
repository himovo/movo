import { apiClient } from './client';
import { useAuthStore } from '@/stores/auth';

export type ModelStatus = 'active' | 'disabled';
export type HealthStatus = 'unknown' | 'healthy' | 'failed';

export interface ModelProviderItem {
  id: string;
  name: string;
  code: string;
  providerType: 'openai_compatible' | 'azure_openai';
  defaultBaseUrl: string;
  authType: string;
  status: ModelStatus;
  updatedAt: string;
}

export interface ModelInstanceItem {
  id: string;
  mainId: string;
  providerId: string;
  providerName: string;
  providerCode: string;
  providerType: string;
  orgId: string;
  displayName: string;
  modelName: string;
  baseUrl: string;
  apiVersion: string;
  apiKeyMasked: string;
  apiSecretMasked: string;
  capabilities: string[];
  maxContextTokens: number;
  status: ModelStatus;
  healthStatus: HealthStatus;
  lastError: string;
  isDefault: boolean;
  priority: number;
  updatedAt: string;
}

export interface ModelInstancePayload {
  providerId: string;
  orgId: string;
  displayName: string;
  modelName: string;
  baseUrl: string;
  apiVersion: string;
  apiKey: string;
  apiSecret?: string;
  capabilities: string[];
  maxContextTokens?: number;
  status: ModelStatus;
  isDefault: boolean;
  priority?: number;
}

export async function fetchModelProviders() {
  const { data } = await apiClient.get<ModelProviderItem[]>('/api/models/providers');
  return data;
}

export async function fetchModelInstances() {
  const { data } = await apiClient.get<ModelInstanceItem[]>('/api/models/instances');
  return data;
}

export async function createModelInstance(payload: ModelInstancePayload) {
  const { data } = await apiClient.post<ModelInstanceItem>('/api/models/instances', payload);
  return data;
}

export async function updateModelInstance(id: string, payload: ModelInstancePayload) {
  const { data } = await apiClient.put<ModelInstanceItem>(`/api/models/instances/${id}`, payload);
  return data;
}

export async function deleteModelInstance(id: string) {
  const { data } = await apiClient.delete<{ success: boolean }>(`/api/models/instances/${id}`);
  return data;
}

export async function setDefaultModelInstance(id: string) {
  const { data } = await apiClient.post<{ success: boolean }>(`/api/models/instances/${id}/default`);
  return data;
}

export async function testModelInstance(id: string) {
  const { data } = await apiClient.post<{ success: boolean; status: string; message: string }>(
    `/api/models/instances/${id}/test`,
  );
  return data;
}

export async function streamModelInstanceTest(
  id: string,
  prompt: string,
  onEvent: (event: { type: string; content?: string; message?: string }) => void,
) {
  const authStore = useAuthStore();
  const baseURL = import.meta.env.VITE_ADMIN_API_BASE_URL || '/admin-api';
  const response = await fetch(`${baseURL}/api/models/instances/${id}/test/stream`, {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${authStore.token}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ prompt }),
  });
  if (response.status === 401 || response.status === 403) {
    authStore.clearSession();
    if (typeof window !== 'undefined' && window.location.pathname !== '/login') {
      window.location.replace('/login');
    }
    throw new Error('认证已过期，请重新登录');
  }
  if (!response.ok || !response.body) {
    const text = await response.text();
    throw new Error(text || `HTTP ${response.status}`);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder('utf-8');
  let buffer = '';
  while (true) {
    const { value, done } = await reader.read();
    if (done) {
      break;
    }
    buffer += decoder.decode(value, { stream: true });
    const parts = buffer.split('\n\n');
    buffer = parts.pop() || '';
    for (const part of parts) {
      const line = part
        .split('\n')
        .find((item) => item.startsWith('data:'));
      if (!line) {
        continue;
      }
      onEvent(JSON.parse(line.slice(5).trim()));
    }
  }
}
