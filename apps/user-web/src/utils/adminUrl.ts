const DEFAULT_ADMIN_WEB_URL = 'http://localhost:3100'

export function buildAdminSsoUrl(ssoToken: string): string {
  const configuredBase = String((import.meta as any).env?.VITE_ADMIN_WEB_URL || DEFAULT_ADMIN_WEB_URL).trim()
  const base = configuredBase || DEFAULT_ADMIN_WEB_URL
  try {
    const url = new URL(base, window.location.origin)
    url.searchParams.set('sso_token', ssoToken)
    return url.toString()
  } catch {
    const separator = base.includes('?') ? '&' : '?'
    return `${base}${separator}sso_token=${encodeURIComponent(ssoToken)}`
  }
}
