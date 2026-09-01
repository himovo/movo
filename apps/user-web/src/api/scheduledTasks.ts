import axios from 'axios'
import { installAuthExpiryInterceptor } from './authExpiry'

export type ScheduleKind = 'once' | 'daily' | 'weekly'
export type ScheduledSessionMode = 'fixed' | 'new_per_run'

export type ScheduledJob = {
  id: string
  name: string
  prompt: string
  schedule_kind: ScheduleKind
  timezone: string
  run_at: string
  weekdays: number[]
  session_mode: ScheduledSessionMode
  session_id?: string | null
  session_title_template: string
  enabled: boolean
  output_spec: Record<string, any>
  next_run_at?: string | null
  last_run_at?: string | null
  last_run_status?: string
  last_session_id?: string | null
  created_at: string
  updated_at: string
}

export type ScheduledJobDraft = Pick<
  ScheduledJob,
  'name' | 'prompt' | 'schedule_kind' | 'timezone' | 'run_at' | 'weekdays' |
  'session_mode' | 'session_id' | 'session_title_template' | 'enabled' | 'output_spec'
>

const client = axios.create({ baseURL: '/askai-api/api', timeout: 20000 })
installAuthExpiryInterceptor(client)

function config(token: string) {
  return { headers: { Authorization: `Bearer ${token}` } }
}

export async function listScheduledJobs(token: string): Promise<ScheduledJob[]> {
  const response = await client.get('/scheduled-jobs', config(token))
  return response.data?.data || []
}

export async function createScheduledJob(token: string, draft: ScheduledJobDraft): Promise<ScheduledJob> {
  const response = await client.post('/scheduled-jobs', draft, config(token))
  return response.data?.data
}

export async function updateScheduledJob(token: string, id: string, patch: Partial<ScheduledJobDraft>): Promise<ScheduledJob> {
  const response = await client.patch(`/scheduled-jobs/${id}`, patch, config(token))
  return response.data?.data
}

export async function deleteScheduledJob(token: string, id: string): Promise<void> {
  await client.delete(`/scheduled-jobs/${id}`, config(token))
}

export async function runScheduledJobNow(token: string, id: string): Promise<void> {
  await client.post(`/scheduled-jobs/${id}/run-now`, {}, config(token))
}
