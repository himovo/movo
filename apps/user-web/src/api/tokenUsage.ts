import axios from 'axios'
import { installAuthExpiryInterceptor } from './authExpiry'

const client = axios.create({
  timeout: 20000,
})
installAuthExpiryInterceptor(client)

export type TokenUsageSummary = {
  total_calls: number
  internal_calls: number
  total_tokens: number
  prompt_tokens: number
  completion_tokens: number
  avg_tokens: number
  last_called_at?: string | null
  last_24h_calls: number
  last_24h_internal_calls: number
  last_24h_tokens: number
  top_models: Array<{ model_name: string; calls: number; tokens: number }>
}

export type TokenUsageItem = {
  request_id: string
  user_request_id?: string
  main_id: string
  user_id: string
  session_id: string
  trace_id: string
  stage: string
  intent: string
  node_id: string
  status: string
  model_name: string
  model_names?: string[]
  model_id: string
  prompt: string
  request_title_zh: string
  request_title_en: string
  start_time: number
  end_time: number
  total_tokens: number
  prompt_tokens: number
  completion_tokens: number
  calls?: number
  push_status: string
  push_error: string
  created_at?: string | null
  updated_at?: string | null
}

export type TokenUsagePage = {
  summary: TokenUsageSummary
  items: TokenUsageItem[]
  offset: number
  limit: number
  total: number
  has_more: boolean
}

export async function listTokenUsage(
  userId: string,
  options: {
    mainId?: string
    limit?: number
    offset?: number
    q?: string
    stage?: string
    status?: string
    token?: string
  } = {}
): Promise<TokenUsagePage> {
  const query = new URLSearchParams({
    userId,
    limit: String(options.limit ?? 12),
    offset: String(options.offset ?? 0),
  })
  if (options.mainId) query.set('mainId', options.mainId)
  if (options.q) query.set('q', options.q)
  if (options.stage) query.set('stage', options.stage)
  if (options.status) query.set('status', options.status)
  const response = await client.get(`/askai-api/api/token-usage?${query.toString()}`, {
    headers: {
      ...(options.token ? { Authorization: `Bearer ${options.token}` } : {}),
    },
  })
  const data = response.data?.data || {}
  return {
    summary: {
      total_calls: Number(data.summary?.total_calls || 0),
      internal_calls: Number(data.summary?.internal_calls || 0),
      total_tokens: Number(data.summary?.total_tokens || 0),
      prompt_tokens: Number(data.summary?.prompt_tokens || 0),
      completion_tokens: Number(data.summary?.completion_tokens || 0),
      avg_tokens: Number(data.summary?.avg_tokens || 0),
      last_called_at: data.summary?.last_called_at || null,
      last_24h_calls: Number(data.summary?.last_24h_calls || 0),
      last_24h_internal_calls: Number(data.summary?.last_24h_internal_calls || 0),
      last_24h_tokens: Number(data.summary?.last_24h_tokens || 0),
      top_models: Array.isArray(data.summary?.top_models) ? data.summary.top_models : [],
    },
    items: Array.isArray(data.items) ? data.items : [],
    offset: Number(data.offset || 0),
    limit: Number(data.limit || options.limit || 12),
    total: Number(data.total || 0),
    has_more: Boolean(data.has_more),
  }
}
