import { apiClient } from './client';

export type QuotaPeriod = 'monthly' | 'daily' | 'hourly';
export type QuotaStatus = 'active' | 'disabled';

export interface TrafficAllocationOverview {
  orgPolicy: {
    totalTokens: number;
    period: QuotaPeriod;
    timezone: string;
    status: QuotaStatus;
    usedTokens: number;
    remainingTokens: number;
    periodStartAt: string;
    resetAt: string;
  };
  defaultPolicy: {
    quotaTokens: number;
    period: QuotaPeriod;
    status: QuotaStatus;
  };
  assignedTokens: number;
  assignedPolicyCount: number;
}

export interface UserAllocationItem {
  userId: string;
  name: string;
  loginName: string;
  email: string;
  mobile: string;
  status: string;
  departmentName: string;
  quotaTokens: number;
  usedTokens: number;
  remainingTokens: number;
  period: QuotaPeriod;
  resetAt: string;
}

export interface AllocationLogItem {
  id: string;
  userId: string;
  userName: string;
  action: string;
  beforeQuotaTokens: number;
  afterQuotaTokens: number;
  deltaTokens: number;
  reason: string;
  operator: string;
  createdAt: string;
}

export interface AllocationLogPage {
  page: number;
  pageSize: number;
  total: number;
  items: AllocationLogItem[];
}

export async function fetchTrafficAllocationOverview() {
  const { data } = await apiClient.get<TrafficAllocationOverview>('/api/traffic-allocations/overview');
  return data;
}

export async function updateOrgQuotaPolicy(payload: {
  totalTokens: number;
  period: QuotaPeriod;
  timezone: string;
  status: QuotaStatus;
}) {
  const { data } = await apiClient.put<{ success: boolean }>('/api/traffic-allocations/org-policy', payload);
  return data;
}

export async function updateDefaultQuotaPolicy(payload: {
  quotaTokens: number;
  period: QuotaPeriod;
  status: QuotaStatus;
}) {
  const { data } = await apiClient.put<{ success: boolean }>('/api/traffic-allocations/default-policy', payload);
  return data;
}

export async function fetchUserAllocations(params: { keyword?: string; statusFilter?: string }) {
  const { data } = await apiClient.get<UserAllocationItem[]>('/api/traffic-allocations/users', { params });
  return data;
}

export async function updateUserQuotaPolicy(userId: string, payload: {
  userId: string;
  quotaTokens: number;
  period: QuotaPeriod;
  reason: string;
}) {
  const { data } = await apiClient.put<{ success: boolean }>(`/api/traffic-allocations/users/${userId}/policy`, payload);
  return data;
}

export async function fetchAllocationLogs(params: { page?: number; pageSize?: number } = {}) {
  const { data } = await apiClient.get<AllocationLogPage>('/api/traffic-allocations/logs', { params });
  return data;
}
