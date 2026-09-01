import { apiClient } from '@/api/client';

export function resolveAdminAssetUrl(value?: string | null): string {
  const raw = String(value || '').trim();
  if (!raw) return '';
  if (/^(?:https?:)?\/\//i.test(raw) || raw.startsWith('data:') || raw.startsWith('blob:')) {
    return raw;
  }

  const baseURL = String(apiClient.defaults.baseURL || '/admin-api').replace(/\/$/, '');
  const path = raw.startsWith('/') ? raw : `/${raw}`;
  if (baseURL && path === baseURL) {
    return path;
  }
  if (baseURL && path.startsWith(`${baseURL}/`)) {
    return path;
  }
  return `${baseURL}${path}`;
}

export function resolveAdminAssetUrlWithVersion(value?: string | null, version?: string | null): string {
  const url = resolveAdminAssetUrl(value);
  const actualVersion = String(version || value || '').trim();
  if (!url || !actualVersion) return url;
  const separator = url.includes('?') ? '&' : '?';
  return `${url}${separator}v=${encodeURIComponent(actualVersion)}`;
}
