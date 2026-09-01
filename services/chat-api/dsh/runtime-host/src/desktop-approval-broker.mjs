const OUTCOMES = new Set(['allowed-once', 'rejected', 'cancelled'])

function latestAskedEvent(session, request) {
  for (let index = session.events.length - 1; index >= 0; index -= 1) {
    const event = session.events[index]
    if (event.type !== 'approval/asked') continue
    if (event.data.toolName !== request.toolName) continue
    if (request.callId !== undefined && event.data.callId !== request.callId) continue
    return event
  }
  throw new Error('DSH approval request has no matching approval/asked event')
}

export class DesktopApprovalBroker {
  #pending = new Map()
  #sessionGrants = new Map()
  #dispose

  constructor(ctx, { excludedTools = [] } = {}) {
    this.excludedTools = new Set(excludedTools)
    this.#dispose = ctx.on('approval/request', async (request, next) => {
      if (this.excludedTools.has(request.toolName)) return next()
      const sessionId = String(request.agent.id)
      if (this.#sessionGrants.get(sessionId)?.has(request.toolName)) return 'allowed-once'
      const asked = latestAskedEvent(request.agent.session, request)
      const approvalId = String(asked.data.id)
      return await new Promise(resolve => {
        const finish = outcome => {
          request.signal?.removeEventListener('abort', abort)
          this.#pending.delete(approvalId)
          resolve(outcome)
        }
        const abort = () => finish('cancelled')
        this.#pending.set(approvalId, {
          approvalId,
          sessionId,
          toolName: request.toolName,
          callId: request.callId === undefined ? '' : String(request.callId),
          reason: request.reason ?? '',
          createdAt: Date.now(),
          finish,
        })
        request.signal?.addEventListener('abort', abort, { once: true })
      })
    })
  }

  list(sessionId) {
    return [...this.#pending.values()]
      .filter(item => item.sessionId === sessionId)
      .map(({ finish: _finish, ...item }) => ({ ...item }))
  }

  decide(sessionId, approvalId, outcome, grantScope = 'once') {
    if (!OUTCOMES.has(outcome)) throw new Error(`unsupported approval outcome: ${outcome}`)
    if (!['once', 'session'].includes(grantScope)) throw new Error(`unsupported approval grant scope: ${grantScope}`)
    const pending = this.#pending.get(approvalId)
    if (pending === undefined || pending.sessionId !== sessionId) throw new Error('pending approval not found')
    if (outcome === 'allowed-once' && grantScope === 'session') {
      const granted = this.#sessionGrants.get(sessionId) ?? new Set()
      granted.add(pending.toolName)
      this.#sessionGrants.set(sessionId, granted)
    }
    pending.finish(outcome)
    return { decided: true, approvalId, outcome, grantScope }
  }

  clearSession(sessionId) {
    for (const pending of [...this.#pending.values()]) {
      if (pending.sessionId === sessionId) pending.finish('cancelled')
    }
    this.#sessionGrants.delete(sessionId)
  }

  dispose() {
    for (const pending of [...this.#pending.values()]) pending.finish('cancelled')
    this.#sessionGrants.clear()
    this.#dispose?.()
  }
}
