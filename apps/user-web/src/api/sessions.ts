import axios from 'axios'

export type ChatMessage = {
  role: string
  content: string
  plan?: any
  progress?: { content: string; timestamp?: string }[]
  documents?: DocumentInfo[]
  images?: ImageInfo[]
  /** Server-minted id for this assistant turn (X-Message-Id from /chat/completions) */
  message_id?: string
  /** Persisted V3 events returned by GET /sessions/{id}; used for replay. */
  execution_events?: any[]
  trigger_source?: string
  scheduled_job_id?: string
  scheduled_run_id?: string
  created_at?: string
}

export type DocumentInfo = {
  type: 'pdf' | 'docx' | 'ppt' | 'pptx' | 'md' | 'xlsx'
  url: string
  filename?: string
  title?: string
  object_path?: string
}

export type ImageInfo = {
  object_path?: string
  url?: string
  signed_url?: string
  filename?: string
  content_type?: string
  size?: number
}

export type SessionSummary = {
  id: string
  user_id: string
  title: string
  created_at: string
  updated_at: string
  last_message_at?: string | null
  last_message_preview?: string | null
  message_count: number
  active_run?: {
    run_id: string
    message_id: string
    source: 'scheduled' | string
    status: 'running' | 'suspended' | string
    scheduled_job_id?: string
    started_at?: string
  } | null
  scheduled_unread?: boolean
  pending_approval_count?: number
  last_scheduled_run?: { run_id: string; status: string; finished_at?: string } | null
  execution_location?: 'server' | 'desktop' | 'remote_sandbox'
  runtime_preset_id?: string
  code_project?: { workspace_id: string; git_branch: string; worktree: boolean } | null
}

export type SessionDetail = SessionSummary & {
  messages: ChatMessage[]
}

export type SessionSearchResult = SessionSummary & {
  match_type: 'title' | 'preview' | 'message'
  snippets: string[]
  matched_message_count: number
}

export type SessionListPage = {
  items: SessionSummary[]
  offset: number
  limit: number
  has_more: boolean
}

export type SessionSearchPage = {
  items: SessionSearchResult[]
  offset: number
  limit: number
  has_more: boolean
}

const client = axios.create({
  timeout: 120000,
})

function authHeaders(authToken?: string | null) {
  return authToken ? { Authorization: `Bearer ${authToken}` } : {}
}

export type DesktopProject = {
  workspace_id: string
  title: string
  worktree: boolean
  created_at: string
  updated_at: string
}

export async function createDesktopProject(
  payload: Pick<DesktopProject, 'workspace_id' | 'title' | 'worktree'>,
  authToken?: string | null,
): Promise<DesktopProject> {
  const response = await client.post('/askai-api/api/projects', payload, { headers: authHeaders(authToken) })
  return response.data?.data
}

export async function listDesktopProjects(authToken?: string | null): Promise<DesktopProject[]> {
  const response = await client.get('/askai-api/api/projects', { headers: authHeaders(authToken) })
  return Array.isArray(response.data?.data) ? response.data.data : []
}

export async function listSessions(userId: string, mainId?: string, authToken?: string | null): Promise<SessionSummary[]> {
  const query = new URLSearchParams({ userId })
  if (mainId) query.set('mainId', mainId)
  const response = await client.get(`/askai-api/api/sessions?${query.toString()}`, {
    timeout: 15000, headers: authHeaders(authToken),
  })
  return response.data?.data || []
}

export async function listSessionsPaged(
  userId: string,
  mainId?: string,
  options: { limit?: number; offset?: number } = {},
  authToken?: string | null,
): Promise<SessionListPage> {
  const limit = options.limit ?? 30
  const offset = options.offset ?? 0
  const query = new URLSearchParams({
    userId,
    paged: 'true',
    limit: String(limit),
    offset: String(offset),
  })
  if (mainId) query.set('mainId', mainId)
  const response = await client.get(`/askai-api/api/sessions?${query.toString()}`, {
    timeout: 15000, headers: authHeaders(authToken),
  })
  const data = response.data?.data || {}
  return {
    items: Array.isArray(data.items) ? data.items : [],
    offset: typeof data.offset === 'number' ? data.offset : offset,
    limit: typeof data.limit === 'number' ? data.limit : limit,
    has_more: Boolean(data.has_more),
  }
}

export async function searchSessions(
  userId: string,
  mainId: string | undefined,
  queryText: string,
  options: { limit?: number; offset?: number } = {},
  authToken?: string | null,
): Promise<SessionSearchPage> {
  const limit = options.limit ?? 20
  const offset = options.offset ?? 0
  const query = new URLSearchParams({
    userId,
    q: queryText,
    limit: String(limit),
    offset: String(offset),
  })
  if (mainId) query.set('mainId', mainId)
  const response = await client.get(`/askai-api/api/sessions/search?${query.toString()}`, {
    timeout: 15000, headers: authHeaders(authToken),
  })
  const data = response.data?.data || {}
  return {
    items: Array.isArray(data.items) ? data.items : [],
    offset: typeof data.offset === 'number' ? data.offset : offset,
    limit: typeof data.limit === 'number' ? data.limit : limit,
    has_more: Boolean(data.has_more),
  }
}

export async function createSession(
  userId: string,
  mainId?: string,
  title?: string,
  messages?: ChatMessage[],
  authToken?: string | null,
): Promise<SessionSummary> {
  const response = await client.post('/askai-api/api/sessions', {
    user_id: userId,
    main_id: mainId,
    title: title || 'New Chat',
    messages: messages || [],
  }, { headers: authHeaders(authToken) })
  return response.data?.data
}

export async function getSession(sessionId: string, userId: string, mainId?: string, authToken?: string | null): Promise<SessionDetail> {
  const query = new URLSearchParams({ userId })
  if (mainId) query.set('mainId', mainId)
  const response = await client.get(`/askai-api/api/sessions/${sessionId}?${query.toString()}`, { headers: authHeaders(authToken) })
  return response.data?.data
}

export async function deleteSession(sessionId: string, userId: string, mainId?: string, authToken?: string | null): Promise<{ id: string }> {
  const query = new URLSearchParams({ userId })
  if (mainId) query.set('mainId', mainId)
  const response = await client.delete(`/askai-api/api/sessions/${sessionId}?${query.toString()}`, { headers: authHeaders(authToken) })
  return response.data?.data
}

export async function updateSessionTitle(
  sessionId: string,
  userId: string,
  mainId: string | undefined,
  title: string,
  authToken?: string | null,
): Promise<SessionSummary> {
  const response = await client.patch(`/askai-api/api/sessions/${sessionId}`, {
    user_id: userId,
    main_id: mainId,
    title,
  }, { headers: authHeaders(authToken) })
  return response.data?.data
}

export async function appendMessages(sessionId: string, userId: string, mainId: string | undefined, messages: ChatMessage[], authToken?: string | null): Promise<SessionSummary> {
  const response = await client.post(`/askai-api/api/sessions/${sessionId}/messages`, {
    user_id: userId,
    main_id: mainId,
    messages,
  }, { headers: authHeaders(authToken) })
  return response.data?.data
}
