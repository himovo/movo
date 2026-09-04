const dateTimeParts = (value: Date, timeZone: string) => {
  const parts = new Intl.DateTimeFormat('en-CA', {
    timeZone,
    year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false,
  }).formatToParts(value)
  return Object.fromEntries(parts.filter(part => part.type !== 'literal').map(part => [part.type, part.value]))
}

const pad = (value: number) => String(value).padStart(2, '0')

/** Convert a persisted instant into the synthetic local timestamp expected by NDatePicker. */
export function instantToPickerValue(value: string, timeZone: string): number | null {
  if (!/(?:Z|[+-]\d{2}:?\d{2})$/i.test(value.trim())) {
    const match = value.trim().match(/^(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2})(?::(\d{2}))?/)
    if (!match) return null
    return new Date(Number(match[1]), Number(match[2]) - 1, Number(match[3]), Number(match[4]), Number(match[5]), Number(match[6] || 0)).getTime()
  }
  const instant = new Date(value)
  if (Number.isNaN(instant.getTime())) return null
  const parts = dateTimeParts(instant, timeZone)
  const hour = parts.hour === '24' ? 0 : Number(parts.hour)
  return new Date(Number(parts.year), Number(parts.month) - 1, Number(parts.day), hour, Number(parts.minute), Number(parts.second)).getTime()
}

export function formatScheduledWallTime(value: string, locale: string, includeDate = false): string {
  const match = value.trim().match(/^(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2})(?::(\d{2}))?/)
  if (!match) return '-'
  const wallAsUtc = new Date(Date.UTC(Number(match[1]), Number(match[2]) - 1, Number(match[3]), Number(match[4]), Number(match[5]), Number(match[6] || 0)))
  return new Intl.DateTimeFormat(locale, {
    ...(includeDate ? { year: 'numeric', month: '2-digit', day: '2-digit' } : {}),
    hour: '2-digit', minute: '2-digit', hour12: false, timeZone: 'UTC',
  }).format(wallAsUtc)
}

/** Serialize picker wall-clock fields without an offset; the backend applies the named task timezone. */
export function pickerValueToWallDateTime(value: number): string {
  const date = new Date(value)
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`
}

export function defaultPickerValue(timeZone: string, now = new Date()): number {
  const tomorrow = new Date(now.getTime() + 24 * 60 * 60 * 1000)
  return instantToPickerValue(tomorrow.toISOString(), timeZone) ?? tomorrow.getTime()
}

export function formatScheduledInstant(value: string, timeZone: string, locale: string, includeDate = false): string {
  const instant = new Date(value)
  if (Number.isNaN(instant.getTime())) return '-'
  return new Intl.DateTimeFormat(locale, {
    ...(includeDate ? { year: 'numeric', month: '2-digit', day: '2-digit' } : {}),
    hour: '2-digit', minute: '2-digit', hour12: false, timeZone,
  }).format(instant)
}
