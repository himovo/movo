import axios from 'axios'
import { t } from '../composables/i18n'
import { installAuthExpiryInterceptor } from './authExpiry'

const client = axios.create({
  baseURL: '/askai-api/api',
  timeout: 15000,
})
installAuthExpiryInterceptor(client)

function isOk(payload: any): boolean {
  return payload?.code === 0 || payload?.success === true
}

export type AuthResult = {
  ok: boolean
  token?: string
  profile?: UserProfile
  message?: string
  requiresTenantSelection?: boolean
  challengeToken?: string
  tenantCandidates?: TenantCandidate[]
}

export type TenantCandidate = {
  mainId: string
  orgName: string
  spaceType?: 'personal' | 'enterprise'
  userId: string
  displayName: string
  username: string
  canAccessAdmin?: boolean
  edition?: 'community' | 'cloud'
  billingEnabled?: boolean
  memberLimit?: number | null
}

export type UserProfile = {
  userId?: number | string
  name?: string
  username?: string
  phone?: string
  email?: string
  avatar?: string
  mainId?: string
  orgName?: string
  spaceType?: 'personal' | 'enterprise'
  canAccessAdmin?: boolean
  tier?: 'community' | 'free' | 'plus' | 'pro' | 'enterprise'
  edition?: 'community' | 'cloud'
  billingEnabled?: boolean
  memberLimit?: number | null
  availableTenants?: TenantCandidate[]
  agentPolicy?: AgentPolicySnapshot
}

export type AgentCapabilityKey =
  | 'content_generation'
  | 'image_generation'
  | 'code_generation'
  | 'browser_automation'
  | 'internal_knowledge'

export type AgentPolicySnapshot = {
  capabilities: Record<AgentCapabilityKey, boolean>
  toolAccessMode: 'all' | 'selected'
  toolIds: string[]
  skillAccessMode: 'all' | 'selected'
  skillIds: string[]
  roleIds: string[]
  roleNames: string[]
  migrationPending?: boolean
  version?: string
}


export async function loginWithPassword(
  username: string,
  password: string,
  mainId = ''
): Promise<AuthResult> {
  try {
    const response = await client.post('/auth/login', { username, password, mainId })
    const payload = response.data
    if (payload?.data?.requiresTenantSelection) {
      return {
        ok: false,
        requiresTenantSelection: true,
        challengeToken: payload?.data?.challengeToken,
        tenantCandidates: payload?.data?.candidates || [],
        message: payload?.message || t('api.auth.select_org'),
      }
    }
    if (!isOk(payload)) {
      return { ok: false, message: payload?.message || t('api.auth.login_failed') }
    }
    const token = payload?.data?.token
    const profile = payload?.data?.profile
    if (!token) return { ok: false, message: t('api.auth.missing_token') }
    return { ok: true, token, profile }
  } catch (error: any) {
    return { ok: false, message: error?.response?.data?.message || error?.message || t('api.auth.login_failed') }
  }
}

export async function selectTenantAndLogin(challengeToken: string, mainId: string): Promise<AuthResult> {
  try {
    const response = await client.post('/auth/login/select-tenant', { challengeToken, mainId })
    const payload = response.data
    if (!isOk(payload)) {
      return { ok: false, message: payload?.message || t('api.auth.login_failed') }
    }
    const token = payload?.data?.token
    const profile = payload?.data?.profile
    if (!token) return { ok: false, message: t('api.auth.missing_token') }
    return { ok: true, token, profile }
  } catch (error: any) {
    return { ok: false, message: error?.response?.data?.message || error?.message || t('api.auth.login_failed') }
  }
}

export async function switchTenant(token: string, mainId: string): Promise<AuthResult> {
  try {
    const response = await client.post(
      '/auth/switch-tenant',
      { mainId },
      {
        headers: {
          Authorization: `Bearer ${token}`,
        },
      }
    )
    const payload = response.data
    if (!isOk(payload)) {
      return { ok: false, message: payload?.message || t('api.auth.switch_org_failed') }
    }
    const nextToken = payload?.data?.token
    const profile = payload?.data?.profile
    if (!nextToken) return { ok: false, message: t('api.auth.missing_token') }
    return { ok: true, token: nextToken, profile }
  } catch (error: any) {
    return { ok: false, message: error?.response?.data?.message || error?.message || t('api.auth.switch_org_failed') }
  }
}

export async function fetchUserProfile(token: string): Promise<{ ok: boolean; data?: UserProfile; message?: string }> {
  try {
    const response = await client.get('/auth/me', {
      headers: {
        Authorization: `Bearer ${token}`,
      },
    })
    const payload = response.data
    if (!isOk(payload)) {
      return { ok: false, message: payload?.message || t('api.auth.get_user_info_failed') }
    }
    const data = payload?.data || {}
    return {
      ok: true,
      data: {
        userId: data.userId,
        name: data.name || '',
        username: data.username || '',
        phone: data.phone || '',
        email: data.email || '',
        avatar: data.avatar || '',
        mainId: data.mainId || 'default',
        orgName: data.orgName || '',
        spaceType: data.spaceType === 'personal' ? 'personal' : 'enterprise',
        canAccessAdmin: data.canAccessAdmin === true,
        edition: data.edition === 'community' ? 'community' : 'cloud',
        billingEnabled: data.billingEnabled !== false,
        memberLimit: typeof data.memberLimit === 'number' ? data.memberLimit : null,
        availableTenants: Array.isArray(data.availableTenants) ? data.availableTenants : [],
        agentPolicy: data.agentPolicy,
      },
    }
  } catch (error: any) {
    return { ok: false, message: error?.response?.data?.message || error?.message || t('api.auth.get_user_info_failed') }
  }
}

export async function updateUserProfile(
  token: string,
  name: string,
): Promise<{ ok: boolean; data?: UserProfile; message?: string }> {
  try {
    const response = await client.patch(
      '/auth/profile',
      { name },
      { headers: { Authorization: `Bearer ${token}` } },
    )
    const payload = response.data
    if (!isOk(payload)) {
      return { ok: false, message: payload?.message || t('api.auth.update_profile_failed') }
    }
    return { ok: true, data: payload?.data, message: payload?.message }
  } catch (error: any) {
    return { ok: false, message: error?.response?.data?.message || error?.message || t('api.auth.update_profile_failed') }
  }
}

export async function uploadUserAvatar(
  token: string,
  file: File,
): Promise<{ ok: boolean; data?: UserProfile; message?: string }> {
  try {
    const form = new FormData()
    form.append('file', file)
    const response = await client.post('/auth/profile/avatar', form, {
      headers: { Authorization: `Bearer ${token}` },
    })
    const payload = response.data
    if (!isOk(payload)) {
      return { ok: false, message: payload?.message || t('api.auth.upload_avatar_failed') }
    }
    return { ok: true, data: payload?.data, message: payload?.message }
  } catch (error: any) {
    return { ok: false, message: error?.response?.data?.message || error?.message || t('api.auth.upload_avatar_failed') }
  }
}

export async function logoutWithToken(token: string): Promise<void> {
  try {
    await client.post('/auth/logout', null, {
      headers: {
        Authorization: `Bearer ${token}`,
      },
    })
  } catch {
    // ignore
  }
}

export async function fetchOrgBilling(token: string): Promise<{ ok: boolean; data?: any; message?: string }> {
  try {
    const response = await client.get('/quota/me', {
      headers: { Authorization: `Bearer ${token}` }
    })
    const payload = response.data
    if (!isOk(payload)) {
      return { ok: false, message: payload?.message || t('api.auth.get_quota_failed') }
    }
    return { ok: true, data: payload?.data }
  } catch (error: any) {
    return { ok: false, message: error?.response?.data?.message || error?.message || t('api.auth.get_quota_failed') }
  }
}

export async function getAdminSSOToken(token: string): Promise<{ ok: boolean; ssoToken?: string; message?: string }> {
  try {
    const response = await client.post(
      '/auth/admin-sso',
      null,
      {
        headers: { Authorization: `Bearer ${token}` }
      }
    )
    const payload = response.data
    if (!isOk(payload)) {
      return { ok: false, message: payload?.message || t('api.auth.auth_failed') }
    }
    return { ok: true, ssoToken: payload?.data?.sso_token }
  } catch (error: any) {
    return { ok: false, message: error?.response?.data?.message || error?.message || t('api.auth.auth_failed') }
  }
}
