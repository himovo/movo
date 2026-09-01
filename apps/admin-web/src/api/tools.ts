import { apiClient } from './client';

export type ToolType = 'http' | 'mcp';
export type ToolStatus = 'active' | 'disabled';
export type TestStatus = 'untested' | 'passed' | 'failed';

export interface ExternalToolItem {
  id: string;
  mainId: string;
  name: string;
  type: ToolType;
  description: string;
  usageHint: string;
  tags: string[];
  status: ToolStatus;
  config: Record<string, any>;
  lastTestStatus: TestStatus;
  lastTestAt: string;
  lastTestMessage: string;
  discoveredTools: Array<{ name: string; description: string; inputSchema?: Record<string, any> }>;
  createdAt: string;
  updatedAt: string;
}

export interface ToolPayload {
  name: string;
  type: ToolType;
  description: string;
  usageHint: string;
  tags: string[];
  status: ToolStatus;
  config: Record<string, any>;
}

export async function fetchTools(): Promise<ExternalToolItem[]> {
  const { data } = await apiClient.get<ExternalToolItem[]>('/api/tools');
  return data;
}

export async function fetchTool(id: string): Promise<ExternalToolItem> {
  const { data } = await apiClient.get<ExternalToolItem>(`/api/tools/${id}`);
  return data;
}

export async function createTool(payload: ToolPayload): Promise<ExternalToolItem> {
  const { data } = await apiClient.post<ExternalToolItem>('/api/tools', payload);
  return data;
}

export async function updateTool(id: string, payload: ToolPayload): Promise<ExternalToolItem> {
  const { data } = await apiClient.put<ExternalToolItem>(`/api/tools/${id}`, payload);
  return data;
}

export async function patchTool(id: string, payload: Partial<ToolPayload>): Promise<ExternalToolItem> {
  const { data } = await apiClient.patch<ExternalToolItem>(`/api/tools/${id}`, payload);
  return data;
}

export async function deleteTool(id: string): Promise<{ id: string }> {
  const { data } = await apiClient.delete<{ id: string }>(`/api/tools/${id}`);
  return data;
}

function toolTestTimeoutMs(payload?: ToolPayload): number {
  const timeoutSeconds = Number(payload?.config?.timeoutSeconds || 15);
  const safeTimeoutSeconds = Number.isFinite(timeoutSeconds) && timeoutSeconds > 0 ? timeoutSeconds : 15;
  return Math.max(10000, Math.ceil((safeTimeoutSeconds + 10) * 1000));
}

export async function testTool(id: string, input: Record<string, any>, timeoutSeconds?: number): Promise<Record<string, any>> {
  const timeout = Number(timeoutSeconds || 15);
  const { data } = await apiClient.post<Record<string, any>>(
    `/api/tools/${id}/test`,
    { input },
    { timeout: Math.max(10000, Math.ceil(((Number.isFinite(timeout) && timeout > 0 ? timeout : 15) + 10) * 1000)) },
  );
  return data;
}

export async function testDraftTool(payload: ToolPayload, input: Record<string, any>): Promise<Record<string, any>> {
  const { data } = await apiClient.post<Record<string, any>>('/api/tools/test-draft', { tool: payload, input }, { timeout: toolTestTimeoutMs(payload) });
  return data;
}

export async function discoverMcpTools(id: string): Promise<{ success: boolean; message: string; tools: ExternalToolItem['discoveredTools'] }> {
  const { data } = await apiClient.post<{ success: boolean; message: string; tools: ExternalToolItem['discoveredTools'] }>(`/api/tools/${id}/discover`);
  return data;
}

export async function generateToolDescription(payload: {
  name: string;
  type: ToolType;
  existingDescription?: string;
}): Promise<{ description: string }> {
  const { data } = await apiClient.post<{ description: string }>('/api/tools/generate-description', payload);
  return data;
}
