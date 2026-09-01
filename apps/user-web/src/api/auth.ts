import axios from 'axios'
import { t } from '../composables/i18n'
import { installAuthExpiryInterceptor } from './authExpiry'

const client = axios.create({
  baseURL: '/askai-api/api',
  timeout: 15000,
})
installAuthExpiryInterceptor(client)

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

export type BillingOrder = {
  orderNo: string
  mainId: string
  source: string
  planCode: string
  planName: string
  targetTier: string
  amountCents: number
  amountText: string
  currency: string
  status: 'created' | 'pending' | 'paid' | 'applied' | 'closed' | 'failed' | string
  paymentMethod: string
  paymentUrl: string
  createdAt: string
  paidAt: string
  appliedAt: string
}

function isOk(payload: any) {
  return payload?.code === 0 || payload?.code === '0' || payload?.success === true
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

// ==========================================
// 计费与多组织（SSO）管理新增 API
// ==========================================

export async function registerUser(
  username: string,
  password: string,
  email: string,
  emailCode: string,
  displayName = '',
  orgName = '',
  inviteCode = '',
): Promise<AuthResult> {
  try {
    const response = await client.post('/auth/register', { username, password, email, emailCode, displayName, orgName, inviteCode })
    const payload = response.data
    if (!isOk(payload)) {
      return { ok: false, message: payload?.message || t('api.auth.register_failed') }
    }
    const token = payload?.data?.token
    const profile = payload?.data?.profile
    if (!token) return { ok: false, message: t('api.auth.missing_token') }
    return { ok: true, token, profile }
  } catch (error: any) {
    return { ok: false, message: error?.response?.data?.message || error?.message || t('api.auth.register_failed') }
  }
}

export async function sendEmailCode(email: string, purpose: 'register' | 'password_reset'): Promise<{ ok: boolean; message?: string }> {
  try {
    const response = await client.post('/auth/email-code', { email, purpose })
    const payload = response.data
    if (!isOk(payload)) {
      return { ok: false, message: payload?.message || t('api.auth.send_code_failed') }
    }
    return { ok: true, message: payload?.message || t('api.auth.code_sent') }
  } catch (error: any) {
    return { ok: false, message: error?.response?.data?.message || error?.message || t('api.auth.send_code_failed') }
  }
}

export type CaptchaValidate = {
  lot_number: string
  captcha_output: string
  pass_token: string
  gen_time: string
}

export async function fetchCaptchaConfig(): Promise<{ ok: boolean; enabled: boolean; captchaId?: string; message?: string }> {
  try {
    const response = await client.get('/auth/captcha-config')
    const payload = response.data
    if (!isOk(payload)) {
      return { ok: false, enabled: true, message: payload?.message || t('api.auth.get_captcha_failed') }
    }
    return {
      ok: true,
      enabled: payload?.data?.enabled !== false,
      captchaId: payload?.data?.captchaId || '',
    }
  } catch (error: any) {
    return { ok: false, enabled: true, message: error?.response?.data?.message || error?.message || t('api.auth.get_captcha_failed') }
  }
}

export async function sendSmsCode(
  phone: string,
  purpose: 'login' | 'register' = 'login',
  captcha?: CaptchaValidate,
): Promise<{ ok: boolean; message?: string }> {
  try {
    const response = await client.post('/auth/sms-code', { phone, purpose, ...(captcha || {}) })
    const payload = response.data
    if (!isOk(payload)) {
      return { ok: false, message: payload?.message || t('api.auth.send_code_failed') }
    }
    return { ok: true, message: payload?.message || t('api.auth.code_sent') }
  } catch (error: any) {
    return { ok: false, message: error?.response?.data?.message || error?.message || t('api.auth.send_code_failed') }
  }
}

export async function loginWithPhoneCode(
  phone: string,
  code: string,
  inviteCode = '',
  orgName = '',
): Promise<AuthResult> {
  try {
    const response = await client.post('/auth/phone-login', { phone, code, inviteCode, orgName })
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

export async function resetPasswordByEmail(
  email: string,
  code: string,
  newPassword: string,
): Promise<{ ok: boolean; message?: string; usernames?: string[] }> {
  try {
    const response = await client.post('/auth/password-reset/confirm', { email, code, newPassword })
    const payload = response.data
    if (!isOk(payload)) {
      return { ok: false, message: payload?.message || t('api.auth.reset_password_failed') }
    }
    return {
      ok: true,
      message: payload?.message || t('api.auth.password_reset'),
      usernames: Array.isArray(payload?.data?.usernames) ? payload.data.usernames : [],
    }
  } catch (error: any) {
    return { ok: false, message: error?.response?.data?.message || error?.message || t('api.auth.reset_password_failed') }
  }
}

export async function createNewOrg(orgName: string, token: string): Promise<AuthResult> {
  try {
    const response = await client.post(
      '/organizations/create',
      { orgName },
      {
        headers: { Authorization: `Bearer ${token}` }
      }
    )
    const payload = response.data
    if (!isOk(payload)) {
      return { ok: false, message: payload?.message || t('api.auth.create_org_failed') }
    }
    const nextToken = payload?.data?.token
    const profile = payload?.data?.profile
    if (!nextToken) return { ok: false, message: t('api.auth.missing_token') }
    return { ok: true, token: nextToken, profile }
  } catch (error: any) {
    return { ok: false, message: error?.response?.data?.message || error?.message || t('api.auth.create_org_failed') }
  }
}

export async function renameOrg(orgName: string, token: string): Promise<AuthResult> {
  try {
    const response = await client.post(
      '/organizations/rename',
      { orgName },
      {
        headers: { Authorization: `Bearer ${token}` }
      }
    )
    const payload = response.data
    if (!isOk(payload)) {
      return { ok: false, message: payload?.message || t('api.auth.rename_org_failed') }
    }
    const nextToken = payload?.data?.token
    const profile = payload?.data?.profile
    if (!nextToken) return { ok: false, message: t('api.auth.missing_token') }
    return { ok: true, token: nextToken, profile }
  } catch (error: any) {
    return { ok: false, message: error?.response?.data?.message || error?.message || t('api.auth.rename_org_failed') }
  }
}

export async function addOrgMember(username: string, password: string, displayName: string, token: string): Promise<{ ok: boolean; message?: string }> {
  try {
    const response = await client.post(
      '/organizations/add-member',
      { username, password, displayName },
      {
        headers: { Authorization: `Bearer ${token}` }
      }
    )
    const payload = response.data
    if (!isOk(payload)) {
      return { ok: false, message: payload?.message || t('api.auth.add_member_failed') }
    }
    return { ok: true }
  } catch (error: any) {
    return { ok: false, message: error?.response?.data?.message || error?.message || t('api.auth.add_member_failed') }
  }
}

export async function upgradeOrg(tier: string, token: string): Promise<{ ok: boolean; message?: string; data?: any }> {
  try {
    const response = await client.post(
      '/organizations/upgrade',
      { tier },
      {
        headers: { Authorization: `Bearer ${token}` }
      }
    )
    const payload = response.data
    if (!isOk(payload)) {
      return { ok: false, message: payload?.message || t('api.auth.upgrade_failed') }
    }
    return { ok: true, message: payload?.message, data: payload?.data }
  } catch (error: any) {
    return { ok: false, message: error?.response?.data?.message || error?.message || t('api.auth.upgrade_failed') }
  }
}

export async function createBillingOrder(
  planCode: string,
  token: string,
  paymentMethod = 'wechat_native',
): Promise<{ ok: boolean; message?: string; order?: BillingOrder }> {
  try {
    const response = await client.post(
      '/billing/orders',
      { planCode, paymentMethod },
      {
        headers: { Authorization: `Bearer ${token}` }
      }
    )
    const payload = response.data
    if (!isOk(payload)) {
      return { ok: false, message: payload?.message || t('billing.payment_order_failed') }
    }
    return { ok: true, message: payload?.message, order: payload?.data?.order }
  } catch (error: any) {
    return { ok: false, message: error?.response?.data?.message || error?.message || t('billing.payment_order_failed') }
  }
}

export async function confirmBillingOrderDev(
  orderNo: string,
  token: string,
): Promise<{ ok: boolean; message?: string; order?: BillingOrder }> {
  try {
    const response = await client.post(
      `/billing/orders/${encodeURIComponent(orderNo)}/confirm-dev`,
      null,
      {
        headers: { Authorization: `Bearer ${token}` }
      }
    )
    const payload = response.data
    if (!isOk(payload)) {
      return { ok: false, message: payload?.message || t('billing.payment_confirm_failed') }
    }
    return { ok: true, message: payload?.message, order: payload?.data?.order }
  } catch (error: any) {
    return { ok: false, message: error?.response?.data?.message || error?.message || t('billing.payment_confirm_failed') }
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
