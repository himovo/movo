import type { AdminProfile } from '@/stores/auth';

function digitsOnly(value?: string | null): string {
  return (value || '').replace(/\D/g, '');
}

export function isMobileLike(value?: string | null): boolean {
  const digits = digitsOnly(value);
  return /^1[3-9]\d{9}$/.test(digits);
}

export function maskMobile(value?: string | null, fallback = '-'): string {
  const digits = digitsOnly(value);
  if (!digits) return fallback;
  if (digits.length === 11) {
    return `${digits.slice(0, 3)}****${digits.slice(-4)}`;
  }
  if (digits.length >= 7) {
    return `${digits.slice(0, 3)}****${digits.slice(-2)}`;
  }
  return fallback;
}

export function isPlaceholderDisplayName(profile: Pick<AdminProfile, 'name' | 'username' | 'phone'> | null | undefined): boolean {
  const name = (profile?.name || '').trim();
  if (!isMobileLike(name)) return false;
  const nameDigits = digitsOnly(name);
  return nameDigits === digitsOnly(profile?.username) || nameDigits === digitsOnly(profile?.phone);
}

export function displayAdminName(profile: AdminProfile | null | undefined, fallback = '管理员'): string {
  const name = (profile?.name || '').trim();
  if (name && !isPlaceholderDisplayName(profile)) {
    return name;
  }
  if (profile?.email) {
    return profile.email.split('@')[0] || fallback;
  }
  if (isMobileLike(profile?.phone)) {
    return maskMobile(profile?.phone, fallback);
  }
  if (isMobileLike(profile?.username)) {
    return maskMobile(profile?.username, fallback);
  }
  return fallback;
}

export function displayProfileNameForEdit(profile: AdminProfile | null | undefined): string {
  if (!profile?.name || isPlaceholderDisplayName(profile)) {
    return '';
  }
  return profile.name;
}
