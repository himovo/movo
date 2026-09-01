const CONTEXT_NAME = 'askai:trusted-time'

function requiredText(value, field) {
  const text = typeof value === 'string' ? value.trim() : ''
  if (!text) throw new TypeError(`temporalContext.${field} is required`)
  return text
}

function requireIsoTimestamp(value, field) {
  const text = requiredText(value, field)
  if (!Number.isFinite(Date.parse(text))) {
    throw new TypeError(`temporalContext.${field} must be an ISO 8601 timestamp`)
  }
  return text
}

function requireIanaTimezone(value) {
  const timezone = requiredText(value, 'user_timezone')
  try {
    new Intl.DateTimeFormat('en', { timeZone: timezone }).format(0)
  } catch (error) {
    throw new TypeError(`temporalContext.user_timezone must be a valid IANA timezone`, { cause: error })
  }
  return timezone
}

export function normalizeTemporalContext(value) {
  if (value === null || typeof value !== 'object' || Array.isArray(value)) {
    throw new TypeError('temporalContext must be an object')
  }
  const allowed = new Set(['captured_at_utc', 'user_local_time', 'user_timezone'])
  const unknown = Object.keys(value).filter(key => !allowed.has(key))
  if (unknown.length > 0) throw new TypeError(`temporalContext has unknown fields: ${unknown.join(', ')}`)
  return Object.freeze({
    capturedAtUtc: requireIsoTimestamp(value.captured_at_utc, 'captured_at_utc'),
    userLocalTime: requireIsoTimestamp(value.user_local_time, 'user_local_time'),
    userTimezone: requireIanaTimezone(value.user_timezone),
  })
}

export function renderTemporalContext(value) {
  if (value === undefined) return ''
  return `Trusted time context supplied by MOVO for this turn:
- Current UTC time: ${value.capturedAtUtc}
- User local time: ${value.userLocalTime}
- User timezone: ${value.userTimezone}

Use this trusted clock and timezone to interpret relative expressions such as now, just now, today, yesterday, tomorrow, and next week. Never invent a calendar date. When an optional tool timestamp cannot be resolved reliably, omit it so the business service can apply its trusted server time.`
}

export class RuntimeTemporalContext {
  #bySession = new Map()
  #dispose

  install(ctx) {
    if (this.#dispose !== undefined) throw new Error('runtime temporal context is already installed')
    this.#dispose = ctx.systemPrompt.context({
      name: CONTEXT_NAME,
      order: 20,
      text: context => {
        const sessionId = context.agent?.id
        return renderTemporalContext(sessionId === undefined ? undefined : this.#bySession.get(sessionId))
      },
    })
  }

  update(sessionId, value) {
    this.#bySession.set(sessionId, normalizeTemporalContext(value))
  }

  remove(sessionId) {
    this.#bySession.delete(sessionId)
  }

  dispose() {
    this.#bySession.clear()
    this.#dispose?.()
    this.#dispose = undefined
  }
}
