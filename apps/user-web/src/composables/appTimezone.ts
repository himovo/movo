import { ref } from 'vue'

const FALLBACK_TIMEZONE = 'Asia/Shanghai'

export function getBrowserTimezone(): string {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || FALLBACK_TIMEZONE
  } catch {
    return FALLBACK_TIMEZONE
  }
}

const currentTimezone = ref(getBrowserTimezone())

export function getAppTimezone(): string {
  return currentTimezone.value || getBrowserTimezone()
}

export function setAppTimezone(timezone?: string | null): string {
  currentTimezone.value = timezone || getBrowserTimezone()
  return currentTimezone.value
}

function normalizeDateInput(value: string): string {
  const trimmed = value.trim()
  if (!trimmed) return trimmed
  if (/(?:Z|[+-]\d{2}:?\d{2})$/i.test(trimmed)) {
    return trimmed
  }
  return `${trimmed.replace(' ', 'T')}Z`
}

export function parseAppDate(value?: string | null): Date | null {
  if (!value) return null
  const date = new Date(normalizeDateInput(value))
  return Number.isNaN(date.getTime()) ? null : date
}

export function formatAppDateTime(value?: string | null, fallback = '-'): string {
  const date = parseAppDate(value)
  if (!date) return fallback
  return new Intl.DateTimeFormat('zh-CN', {
    timeZone: getAppTimezone(),
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  }).format(date)
}

export function formatAppShortDateTime(value?: string | null, fallback = '-'): string {
  const date = parseAppDate(value)
  if (!date) return fallback
  return new Intl.DateTimeFormat('zh-CN', {
    timeZone: getAppTimezone(),
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  }).format(date)
}

export function formatAppTime(value?: string | null, fallback = ''): string {
  const date = parseAppDate(value)
  if (!date) return fallback
  return new Intl.DateTimeFormat('zh-CN', {
    timeZone: getAppTimezone(),
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
  }).format(date)
}
