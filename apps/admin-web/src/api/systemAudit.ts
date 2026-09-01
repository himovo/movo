import { apiClient } from './client';

export type AuditCategory = 'management' | 'agent' | 'legacy';
export type AuditResult = 'success' | 'failed';

export type SystemAuditLog = {
  id: string;
  category: AuditCategory;
  module: string;
  action: string;
  actor: string;
  target: string;
  result: AuditResult;
  statusCode: number;
  occurredAt: string;
  details: Record<string, unknown>;
};

export type SystemAuditOverview = {
  managementOperations: number;
  failedOperations: number;
  agentActivities: number;
  permissionDenials: number;
};

export type SystemAuditPage = {
  page: number;
  pageSize: number;
  total: number;
  items: SystemAuditLog[];
};

export async function fetchSystemAuditOverview(): Promise<SystemAuditOverview> {
  return (await apiClient.get('/api/system-audit/overview')).data;
}

export async function fetchSystemAuditLogs(params: {
  category: AuditCategory;
  page: number;
  pageSize: number;
  keyword?: string;
  result?: '' | AuditResult;
  module?: string;
}): Promise<SystemAuditPage> {
  return (await apiClient.get('/api/system-audit/logs', { params })).data;
}
