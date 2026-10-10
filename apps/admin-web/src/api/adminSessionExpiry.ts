import { useAuthStore } from '@/stores/auth';

export function isAdminLoginRequest(path: string | undefined): boolean {
  return /^\/?api\/auth\/login(?:\/select-tenant)?(?:\?|$)/.test(path || '');
}

export function expireAdminSession(): void {
  const authStore = useAuthStore();
  if (!authStore.token) return;

  authStore.clearSession();
  if (typeof window === 'undefined') return;

  const base = import.meta.env.BASE_URL;
  const loginPath = `${base.endsWith('/') ? base : `${base}/`}login`;
  if (window.location.pathname !== loginPath) {
    window.location.replace(loginPath);
  }
}
