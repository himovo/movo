import { apiClient } from '@/api/client';

export interface TokenStatsSummary {
  totalCalls: number;
  totalTokens: number;
  promptTokens: number;
  completionTokens: number;
  avgTokens: number;
  lastCalledAt: string | null;
  last24hCalls: number;
  last24hTokens: number;
  activeUsers: number;
  activeDepartments: number;
  totalCost: number;
  avgCost: number;
  last24hCost: number;
}

export interface TokenStatsItem {
  requestId: string;
  userRequestId?: string;
  mainId: string;
  mainName: string;
  userName: string;
  departmentName: string;
  modelName: string;
  stage: string;
  status: string;
  requestTitle: string;
  promptPreview: string;
  totalTokens: number;
  promptTokens: number;
  completionTokens: number;
  createdAt: string | null;
  durationMs: number;
  calls?: number;
  sessionId?: string;
}

export interface TokenStatsOption {
  label: string;
  value: string;
}

export interface TokenStatsFilterOptions {
  enterprises: TokenStatsOption[];
  departments: TokenStatsOption[];
  models: TokenStatsOption[];
  stages: TokenStatsOption[];
  statuses: TokenStatsOption[];
}

export interface TokenStatsPage {
  summary: TokenStatsSummary;
  items: TokenStatsItem[];
  offset: number;
  limit: number;
  total: number;
  hasMore: boolean;
  filterOptions: TokenStatsFilterOptions;
}

export interface TokenStatsQuery {
  q?: string;
  departmentId?: string;
  modelName?: string;
  stage?: string;
  status?: string;
  offset?: number;
  limit?: number;
  groupBy?: string;
  sessionId?: string;
  userRequestId?: string;
}

const defaultSummary: TokenStatsSummary = {
  totalCalls: 0,
  totalTokens: 0,
  promptTokens: 0,
  completionTokens: 0,
  avgTokens: 0,
  lastCalledAt: null,
  last24hCalls: 0,
  last24hTokens: 0,
  activeUsers: 0,
  activeDepartments: 0,
  totalCost: 0,
  avgCost: 0,
  last24hCost: 0,
};

const defaultOptions: TokenStatsFilterOptions = {
  enterprises: [],
  departments: [],
  models: [],
  stages: [],
  statuses: [],
};

export async function fetchTokenStats(query: TokenStatsQuery = {}): Promise<TokenStatsPage> {
  const params = {
    q: query.q || '',
    departmentId: query.departmentId || '',
    modelName: query.modelName || '',
    stage: query.stage || '',
    status: query.status || '',
    offset: query.offset || 0,
    limit: query.limit || 20,
    groupBy: query.groupBy || 'user_request',
    sessionId: query.sessionId || '',
    userRequestId: query.userRequestId || '',
  };

  const { data } = await apiClient.get('/api/analytics/token-usage', { params });
  return {
    summary: {
      ...defaultSummary,
      ...(data?.summary || {}),
    },
    items: Array.isArray(data?.items) ? data.items : [],
    offset: Number(data?.offset || params.offset || 0),
    limit: Number(data?.limit || params.limit || 20),
    total: Number(data?.total || 0),
    hasMore: Boolean(data?.hasMore),
    filterOptions: {
      ...defaultOptions,
      ...(data?.filterOptions || {}),
    },
  };
}

export interface TokenStatsDetail {
  requestId: string;
  prompt: string;
  requestPayload: any;
  responsePayload: any;
}

export async function fetchTokenStatsDetail(requestId: string): Promise<TokenStatsDetail> {
  const { data } = await apiClient.get(`/api/analytics/token-usage/${requestId}`);
  return data;
}

export interface ChatMessageItem {
  id: string;
  role: string;
  content: string;
  plan?: any;
  progress?: any[];
  documents?: any[];
  images?: any[];
  createdAt: string | null;
}

export interface SessionChatHistory {
  sessionId: string;
  title: string;
  messages: ChatMessageItem[];
}

export async function fetchSessionChatHistory(requestId: string, sessionId?: string, userRequestId?: string): Promise<SessionChatHistory> {
  const params = {
    sessionId: sessionId || '',
    userRequestId: userRequestId || '',
  };
  const { data } = await apiClient.get(`/api/analytics/token-usage/${requestId}/chat-history`, { params });
  return data;
}
