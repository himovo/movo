import type { ExecutionEventV3 } from './protocol'

export const TERMINAL_RUN_EVENT_TYPES = new Set<ExecutionEventV3['type']>([
  'run.completed',
  'run.failed',
  'run.cancelled',
  'run.blocked',
])

export function elapsedRunMs(startedAt: number | null, endedAt: number | null, now: number): number | null {
  if (!startedAt) return null
  return Math.max(0, (endedAt || now) - startedAt)
}

export function formatRunDuration(durationMs: number | null, locale: 'zh' | 'en'): string {
  if (durationMs === null) return ''
  const totalSeconds = Math.max(0, Math.floor(durationMs / 1000))
  const hours = Math.floor(totalSeconds / 3600)
  const minutes = Math.floor((totalSeconds % 3600) / 60)
  const seconds = totalSeconds % 60

  if (locale === 'en') {
    if (hours) return `${hours}h ${minutes}m ${seconds}s`
    if (minutes) return `${minutes}m ${seconds}s`
    return `${seconds}s`
  }
  if (hours) return `${hours}小时${minutes}分${seconds}秒`
  if (minutes) return `${minutes}分${seconds}秒`
  return `${seconds}秒`
}
