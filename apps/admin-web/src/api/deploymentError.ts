/** Preserve the server's localized deployment-expiration explanation. */
export function deploymentErrorMessage(error: unknown, fallback: string): string {
  const payload = (error as { response?: { data?: { code?: string; message?: string } } })?.response?.data;
  return payload?.code === 'deployment_expired' && typeof payload.message === 'string'
    ? payload.message
    : fallback;
}
