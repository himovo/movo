export function authenticatedHeaders(
  headers: Record<string, string> = {},
): Record<string, string> {
  const token = typeof window !== 'undefined'
    ? window.localStorage.getItem('auth_token')
    : ''
  return {
    ...headers,
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  }
}


export function authenticatedJsonHeaders(): Record<string, string> {
  return authenticatedHeaders({ 'Content-Type': 'application/json' })
}
