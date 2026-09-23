import { createApiClient } from './client'
import { installAuthExpiryInterceptor } from './authExpiry'

const api = createApiClient({ baseURL: '/askai-api/api', timeout: 120000 })
installAuthExpiryInterceptor(api)

function dataOf<T>(res: { data?: any }): T {
  return res.data?.data ?? res.data
}

// Server error codes returned by services/chat-api session_shares.py, plus the
// generic fallbacks. The type is derived from this array so the union and the
// runtime membership check cannot drift; a new server code is added here and
// every exhaustive switch over SessionShareError.code fails to compile until
// the new code is handled.
const SESSION_SHARE_ERROR_CODES = [
  'session_not_found',
  'session_share_not_found',
  'session_share_owner_required',
  'session_share_participant_required',
  'session_share_no_binding',
  'session_share_not_server',
  'session_share_inactive',
  'session_share_token_required',
  'http_error',
] as const

export type SessionShareErrorCode = (typeof SESSION_SHARE_ERROR_CODES)[number]

export type SessionShareError = {
  code: SessionShareErrorCode
  status: number
  message: string
}

export type SessionShareResult<T> =
  | { ok: true; data: T }
  | { ok: false; error: SessionShareError }

function isSessionShareErrorCode(value: unknown): value is SessionShareErrorCode {
  return typeof value === 'string' && (SESSION_SHARE_ERROR_CODES as readonly string[]).includes(value)
}

function errorOf(error: any): SessionShareError {
  const status = Number(error?.response?.status) || 0
  const detail = error?.response?.data?.detail
  const code = isSessionShareErrorCode(detail?.code) ? detail.code : 'http_error'
  const message = detail?.message || error?.message || 'Request failed'
  return { code, status, message }
}

export interface SessionShareCreated {
  /** Raw share token: shown once, only ever placed in the clipboard or link input. */
  token: string
  expires_at: string
  participant_count: number
}

export interface SessionShareJoined {
  session_id: string
}

export interface SessionShareMember {
  user_id: string
  display_name: string
  role: 'owner' | 'participant'
  joined_at: string | null
}

export interface SessionShareMemberPage {
  items: SessionShareMember[]
}

export interface SessionShareMutation {
  session_id: string
  user_id?: string
}

export async function createSessionShare(sessionId: string, expiresInDays: number): Promise<SessionShareResult<SessionShareCreated>> {
  try {
    const res = await api.post(`/sessions/${sessionId}/share`, { expiresInDays })
    return { ok: true, data: dataOf<SessionShareCreated>(res) }
  } catch (error) {
    return { ok: false, error: errorOf(error) }
  }
}

export async function revokeSessionShare(sessionId: string): Promise<SessionShareResult<SessionShareMutation>> {
  try {
    const res = await api.delete(`/sessions/${sessionId}/share`)
    return { ok: true, data: dataOf<SessionShareMutation>(res) }
  } catch (error) {
    return { ok: false, error: errorOf(error) }
  }
}

export async function joinSessionShare(token: string): Promise<SessionShareResult<SessionShareJoined>> {
  try {
    const res = await api.post(`/session-shares/${encodeURIComponent(token)}/join`)
    return { ok: true, data: dataOf<SessionShareJoined>(res) }
  } catch (error) {
    return { ok: false, error: errorOf(error) }
  }
}

export async function listSessionParticipants(sessionId: string): Promise<SessionShareResult<SessionShareMemberPage>> {
  try {
    const res = await api.get(`/sessions/${sessionId}/participants`)
    return { ok: true, data: dataOf<SessionShareMemberPage>(res) }
  } catch (error) {
    return { ok: false, error: errorOf(error) }
  }
}

export async function leaveSession(sessionId: string): Promise<SessionShareResult<SessionShareMutation>> {
  try {
    const res = await api.delete(`/sessions/${sessionId}/participants/me`)
    return { ok: true, data: dataOf<SessionShareMutation>(res) }
  } catch (error) {
    return { ok: false, error: errorOf(error) }
  }
}

export async function removeParticipant(sessionId: string, userId: string): Promise<SessionShareResult<SessionShareMutation>> {
  try {
    const res = await api.delete(`/sessions/${sessionId}/participants/${encodeURIComponent(userId)}`)
    return { ok: true, data: dataOf<SessionShareMutation>(res) }
  } catch (error) {
    return { ok: false, error: errorOf(error) }
  }
}
