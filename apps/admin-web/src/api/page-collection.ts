import { apiClient } from './client';

export interface PageCollectionSettings {
  id: string;
  provider: 'firecrawl';
  label: string;
  enabled: boolean;
  apiKeyMasked: string;
  updatedAt: string;
}

export interface PageCollectionPayload {
  enabled: boolean;
  apiKey?: string;
}

export async function fetchPageCollectionSettings() {
  const { data } = await apiClient.get<PageCollectionSettings>('/api/settings/page-collection');
  return data;
}

export async function savePageCollectionSettings(payload: PageCollectionPayload) {
  const { data } = await apiClient.put<PageCollectionSettings>('/api/settings/page-collection', payload);
  return data;
}
