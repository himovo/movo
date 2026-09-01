import { createApiClient } from './client'

const api = createApiClient({
  baseURL: '/askai-api/api',
  timeout: 30000,
})

export type SiteProfile = {
  id: string
  owner_user_id: string
  name: string
  domain: string
  entry_url: string
  auth_method: string
  hints: string
  visibility: 'private' | 'team' | 'global'
  created_at?: string
  updated_at?: string
}

export type SiteProfileInput = {
  name: string
  domain?: string
  entry_url?: string
  auth_method?: string
  hints?: string
  visibility?: 'private' | 'team' | 'global'
}

export async function listSiteProfiles(userId: string): Promise<SiteProfile[]> {
  const res = await api.get('/site-profiles', { params: { userId } })
  return (res.data?.data || []) as SiteProfile[]
}

export async function getSiteProfile(userId: string, profileId: string): Promise<SiteProfile | null> {
  const res = await api.get(`/site-profiles/${profileId}`, { params: { userId } })
  return (res.data?.data || null) as SiteProfile | null
}

export async function createSiteProfile(userId: string, input: SiteProfileInput): Promise<SiteProfile> {
  const res = await api.post('/site-profiles', { user_id: userId, ...input })
  return res.data?.data as SiteProfile
}

export async function updateSiteProfile(
  userId: string,
  profileId: string,
  input: Partial<SiteProfileInput>,
): Promise<SiteProfile> {
  const res = await api.put(`/site-profiles/${profileId}`, { user_id: userId, ...input })
  return res.data?.data as SiteProfile
}

export async function deleteSiteProfile(userId: string, profileId: string): Promise<void> {
  await api.delete(`/site-profiles/${profileId}`, { params: { userId } })
}
