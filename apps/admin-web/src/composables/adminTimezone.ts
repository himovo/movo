const TIMEZONE_STORAGE_KEY = 'askai-admin-timezone';
const FALLBACK_TIMEZONE = 'Asia/Shanghai';

export function getBrowserTimezone(): string {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || FALLBACK_TIMEZONE;
  } catch {
    return FALLBACK_TIMEZONE;
  }
}

export function getAdminTimezone(): string {
  if (typeof window === 'undefined') {
    return FALLBACK_TIMEZONE;
  }
  return localStorage.getItem(TIMEZONE_STORAGE_KEY) || getBrowserTimezone();
}

export function setAdminTimezone(timezone: string): void {
  if (typeof window === 'undefined') {
    return;
  }
  localStorage.setItem(TIMEZONE_STORAGE_KEY, timezone || getBrowserTimezone());
}

function normalizeDateInput(value: string): string {
  const trimmed = value.trim();
  if (!trimmed) return trimmed;
  if (/(?:Z|[+-]\d{2}:?\d{2})$/i.test(trimmed)) {
    return trimmed;
  }
  return `${trimmed.replace(' ', 'T')}Z`;
}

export function parseAdminDate(value?: string | null): Date | null {
  if (!value) return null;
  const date = new Date(normalizeDateInput(value));
  return Number.isNaN(date.getTime()) ? null : date;
}

export function formatAdminDateTime(value?: string | null, fallback = '-'): string {
  const date = parseAdminDate(value);
  if (!date) return fallback;
  return new Intl.DateTimeFormat('zh-CN', {
    timeZone: getAdminTimezone(),
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  }).format(date);
}

export function formatAdminShortDateTime(value?: string | null, fallback = '-'): string {
  const date = parseAdminDate(value);
  if (!date) return fallback;
  return new Intl.DateTimeFormat('zh-CN', {
    timeZone: getAdminTimezone(),
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  }).format(date);
}

export function formatAdminTime(value?: string | null, fallback = ''): string {
  const date = parseAdminDate(value);
  if (!date) return fallback;
  return new Intl.DateTimeFormat('zh-CN', {
    timeZone: getAdminTimezone(),
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
  }).format(date);
}

export { TIMEZONE_STORAGE_KEY };
