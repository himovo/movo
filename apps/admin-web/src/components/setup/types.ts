import type { SetupSearchProviderId } from '@/api/setup';

export interface SetupAccountForm {
  orgName: string;
  adminUsername: string;
  adminPassword: string;
  adminDisplayName: string;
  employeeUsername: string;
  employeePassword: string;
  employeeName: string;
  orgTotalTokens: number | null;
  defaultUserTokens: number | null;
  quotaPeriod: 'monthly' | 'daily' | 'hourly';
  quotaTimezone: string;
}

export interface SetupModelForm {
  providerId: string;
  displayName: string;
  modelName: string;
  baseUrl: string;
  apiVersion: string;
  apiKey: string;
  capability: 'chat' | 'embedding' | 'rerank' | 'vision' | 'image';
}

export interface SetupOptionalModelForm {
  capability: 'embedding' | 'rerank' | 'vision' | 'image';
  enabled: boolean;
  model: SetupModelForm;
}

export type ModelTestState = 'idle' | 'testing' | 'success' | 'failed';

export interface SetupSearchForm {
  enabled: boolean;
  provider: SetupSearchProviderId;
  apiKey: string;
  endpoint: string;
  baseUrl: string;
  model: string;
  query: string;
}

export type SearchTestState = 'idle' | 'testing' | 'success' | 'failed';
