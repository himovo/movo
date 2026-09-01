import { apiClient } from './client';
import type { SearchProviderId } from '@/components/search-provider/providerGuides';

export interface SetupStatus {
  completed: boolean;
  orgName: string;
  mainId: string;
  initializedAt: string;
  ready: boolean;
  services: SetupServiceStatus[];
  urls: SetupUrls;
}

export interface SetupServiceStatus {
  key: string;
  label: string;
  ok: boolean;
  message: string;
}

export interface SetupUrls {
  userWeb: string;
  adminWeb: string;
  desktopService: string;
  agentWebSocket: string;
}

export interface SetupInitPayload {
  orgName: string;
  adminUsername: string;
  adminPassword: string;
  adminDisplayName: string;
  employeeUsername: string;
  employeePassword: string;
  employeeName: string;
  orgTotalTokens: number;
  defaultUserTokens: number;
  quotaPeriod: 'monthly' | 'daily' | 'hourly';
  quotaTimezone: string;
  model: SetupModelPayload;
  additionalModels: SetupModelPayload[];
  externalSearch: SetupSearchPayload | null;
}

export interface SetupModelProvider {
  id: string;
  name: string;
  code: string;
  providerType: 'openai_compatible' | 'azure_openai';
  defaultBaseUrl: string;
}

export interface SetupModelPayload {
  providerId: string;
  displayName: string;
  modelName: string;
  baseUrl: string;
  apiVersion: string;
  apiKey: string;
  capability: 'chat' | 'embedding' | 'rerank' | 'vision' | 'image';
}

export type SetupSearchProviderId = SearchProviderId;

export interface SetupSearchProvider {
  id: SetupSearchProviderId;
  name: string;
  description: string;
  defaultEndpoint: string;
  defaultBaseUrl: string;
}

export interface SetupSearchPayload {
  provider: SetupSearchProviderId;
  apiKey: string;
  endpoint: string;
  baseUrl: string;
  model: string;
  query: string;
}

export async function fetchSetupStatus() {
  const { data } = await apiClient.get<SetupStatus>('/api/setup/status');
  return data;
}

export async function initializeSetup(payload: SetupInitPayload) {
  const { data } = await apiClient.post<{ completed: boolean; mainId: string; orgName: string; modelInstanceId: string }>(
    '/api/setup/initialize',
    payload,
    { timeout: 150000 },
  );
  return data;
}

export async function fetchSetupModelProviders() {
  const { data } = await apiClient.get<SetupModelProvider[]>('/api/setup/model-providers');
  return data;
}

export async function testSetupModel(payload: SetupModelPayload) {
  const { data } = await apiClient.post<{ success: boolean; message: string }>('/api/setup/model/test', payload, {
    timeout: 150000,
  });
  return data;
}

export async function fetchSetupSearchProviders() {
  const { data } = await apiClient.get<SetupSearchProvider[]>('/api/setup/search-providers');
  return data;
}

export async function testSetupSearch(payload: SetupSearchPayload) {
  const { data } = await apiClient.post<{ success: boolean; message: string; resultCount: number }>(
    '/api/setup/search/test',
    payload,
    { timeout: 60000 },
  );
  return data;
}
