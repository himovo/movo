export type TokenNumberLocale = 'zh' | 'en'

function normalizedAmount(value: number): number {
  const amount = Number(value || 0)
  return Number.isFinite(amount) ? Math.max(0, amount) : 0
}

function formatScaled(value: number, divisor: number, unit: string, locale: TokenNumberLocale): string {
  const scaled = value / divisor
  return `${new Intl.NumberFormat(locale === 'zh' ? 'zh-CN' : 'en-US', {
    maximumFractionDigits: scaled >= 100 ? 1 : 2,
  }).format(scaled)} ${unit}`
}

export function formatTokenAmount(value: number, locale: TokenNumberLocale): string {
  const amount = normalizedAmount(value)
  if (locale === 'zh') {
    if (amount >= 100_000_000) return formatScaled(amount, 100_000_000, '亿', locale)
    if (amount >= 10_000) return formatScaled(amount, 10_000, '万', locale)
    return new Intl.NumberFormat('zh-CN').format(amount)
  }
  if (amount >= 1_000_000_000) return formatScaled(amount, 1_000_000_000, 'B', locale)
  if (amount >= 1_000_000) return formatScaled(amount, 1_000_000, 'M', locale)
  if (amount >= 1_000) return formatScaled(amount, 1_000, 'K', locale)
  return new Intl.NumberFormat('en-US').format(amount)
}

export function formatExactTokenAmount(value: number, locale: TokenNumberLocale): string {
  return new Intl.NumberFormat(locale === 'zh' ? 'zh-CN' : 'en-US').format(normalizedAmount(value))
}

export function quotaUsagePercent(used: number, total: number): number {
  const normalizedTotal = normalizedAmount(total)
  if (!normalizedTotal) return 0
  return Math.max(0, Math.min(100, (normalizedAmount(used) / normalizedTotal) * 100))
}

export function formatQuotaUsagePercent(used: number, total: number): string {
  const percent = quotaUsagePercent(used, total)
  if (percent === 0) return '0'
  if (percent < 0.01) return '<0.01'
  return new Intl.NumberFormat('en-US', {
    maximumFractionDigits: percent < 1 ? 2 : 1,
  }).format(percent)
}
