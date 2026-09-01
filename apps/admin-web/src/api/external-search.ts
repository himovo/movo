import { apiClient } from './client';
import type { SearchProviderId } from '@/components/search-provider/providerGuides';

export type ExternalSearchProvider = SearchProviderId;

export interface ExternalSearchProviderItem {
  id: string;
  provider: ExternalSearchProvider;
  label: string;
  enabled: boolean;
  isDefault: boolean;
  priority: number;
  endpoint: string;
  baseUrl: string;
  model: string;
  apiKeyMasked: string;
  healthStatus: 'healthy' | 'failed' | 'untested' | string;
  lastError: string;
  updatedAt: string;
}

export interface ExternalSearchProviderPayload {
  enabled: boolean;
  apiKey?: string;
  endpoint?: string;
  baseUrl?: string;
  model?: string;
}

export interface ExternalSearchTestPayload {
  query: string;
  apiKey?: string;
  endpoint?: string;
  baseUrl?: string;
  model?: string;
}

export interface ExternalSearchTestResult {
  ok: boolean;
  provider: ExternalSearchProvider;
  resultCount: number;
  sampleResults: Array<{
    title: string;
    url: string;
    snippet: string;
  }>;
  message: string;
}

export async function fetchExternalSearchProviders() {
  const { data } = await apiClient.get<ExternalSearchProviderItem[]>('/api/settings/external-search/providers');
  return data;
}

export async function saveExternalSearchProvider(provider: ExternalSearchProvider, payload: ExternalSearchProviderPayload) {
  const { data } = await apiClient.put<ExternalSearchProviderItem>(`/api/settings/external-search/providers/${provider}`, payload);
  return data;
}

export async function setDefaultExternalSearchProvider(provider: ExternalSearchProvider) {
  const { data } = await apiClient.post<{ success: boolean }>(`/api/settings/external-search/providers/${provider}/default`);
  return data;
}

export async function testExternalSearchProvider(provider: ExternalSearchProvider, payload: ExternalSearchTestPayload) {
  const { data } = await apiClient.post<ExternalSearchTestResult>(`/api/settings/external-search/providers/${provider}/test`, payload);
  return data;
}
