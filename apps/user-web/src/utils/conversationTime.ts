import { getAppTimezone, parseAppDate } from '../composables/appTimezone'
import type { SessionSummary } from '../api/sessions'
import type { ChatMessage } from '../components/chat/chatMessage'
import { isExecutionEventV3 } from '../features/execution-v3/domain/protocol'

export type TimeLocale = 'zh' | 'en'

function calendarDay(date: Date, timezone: string): string {
  const parts = new Intl.DateTimeFormat('en-US', { timeZone: timezone, year: 'numeric', month: '2-digit', day: '2-digit' }).formatToParts(date)
  const value = (type: string) => parts.find(part => part.type === type)?.value || ''
  return `${value('year')}-${value('month')}-${value('day')}`
}

function calendarDayNumber(day: string): number {
  const [year, month, date] = day.split('-').map(Number)
  return Math.floor(Date.UTC(year, month - 1, date) / 86_400_000)
}

export function formatFullConversationTime(value: string | number | undefined, locale: TimeLocale): string {
  const date = typeof value === 'number' ? new Date(value) : parseAppDate(value)
  if (!date || Number.isNaN(date.getTime())) return ''
  return new Intl.DateTimeFormat(locale === 'zh' ? 'zh-CN' : 'en-US', {
    timeZone: getAppTimezone(), year: 'numeric', month: 'long', day: 'numeric',
    hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false,
  }).format(date)
}

export function formatConversationClock(value: string | number | undefined, locale: TimeLocale, now = Date.now()): string {
  const date = typeof value === 'number' ? new Date(value) : parseAppDate(value)
  if (!date || Number.isNaN(date.getTime())) return ''
  const timezone = getAppTimezone()
  const parts = new Intl.DateTimeFormat('en-US', {
    timeZone: timezone, year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit', second: '2-digit', hourCycle: 'h23',
  }).formatToParts(date)
  const valueOf = (type: string) => parts.find(part => part.type === type)?.value || ''
  const clock = `${valueOf('hour')}:${valueOf('minute')}:${valueOf('second')}`
  const day = calendarDay(date, timezone)
  const today = calendarDay(new Date(now), timezone)
  if (day === today) return clock
  const month = Number(valueOf('month'))
  const dayOfMonth = Number(valueOf('day'))
  const currentYear = today.slice(0, 4)
  if (locale === 'zh') {
    const prefix = day.slice(0, 4) === currentYear ? '' : `${valueOf('year')}\u5e74`
    return `${prefix}${month}\u6708${dayOfMonth}\u65e5 ${clock}`
  }
  const prefix = day.slice(0, 4) === currentYear ? '' : `${valueOf('year')}/`
  return `${prefix}${month}/${dayOfMonth} ${clock}`
}

export function formatSessionActivity(session: Pick<SessionSummary, 'last_message_at' | 'updated_at' | 'created_at'>, locale: TimeLocale, now = Date.now()): string {
  const date = parseAppDate(session.last_message_at || session.updated_at || session.created_at)
  if (!date) return ''
  const timezone = getAppTimezone()
  const today = calendarDay(new Date(now), timezone)
  const day = calendarDay(date, timezone)
  const delta = Math.max(0, now - date.getTime())
  if (day === today && delta < 60 * 60_000) {
    const minutes = Math.max(1, Math.floor(delta / 60_000))
    return locale === 'zh' ? `${minutes}\u5206\u949f\u524d` : `${minutes}m ago`
  }
  if (day === today) {
    const hours = Math.max(1, Math.floor(delta / 3_600_000))
    return locale === 'zh' ? `${hours}\u5c0f\u65f6\u524d` : `${hours}h ago`
  }
  if (calendarDayNumber(today) - calendarDayNumber(day) === 1) return locale === 'zh' ? '\u6628\u5929' : 'Yesterday'
  const sameYear = day.slice(0, 4) === today.slice(0, 4)
  return new Intl.DateTimeFormat(locale === 'zh' ? 'zh-CN' : 'en-US', {
    timeZone: timezone, ...(sameYear ? {} : { year: 'numeric' }), month: 'numeric', day: 'numeric',
  }).format(date)
}

export function assistantMessageTime(message: ChatMessage): { value: string | number; completed: boolean } | null {
  const events = (message._execV3?.state.rawEvents || message.execution_events || []).filter(isExecutionEventV3)
  const terminal = [...events].reverse().find(event => ['run.completed', 'run.failed', 'run.cancelled'].includes(event.type))
  if (terminal && Number.isFinite(terminal.ts)) return { value: terminal.ts, completed: terminal.type === 'run.completed' }
  return message.created_at ? { value: message.created_at, completed: false } : null
}
