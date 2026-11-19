const OUTCOMES = new Set(['allowed-once', 'rejected', 'cancelled'])

export class DesktopApprovalBroker {
  #pending = new Map()
  #sessionGrants = new Map()
  #asked = new Map()
  #calls = new Map()
  #context = new Map()
  #reviewers = new Map()
  #denials = new Map()
  #reviewWindow = new Map()
  #disposeApproval
  #disposeEvents

  constructor(ctx, { excludedTools = [], automaticReviewer } = {}) {
    this.excludedTools = new Set(excludedTools)
    this.automaticReviewer = automaticReviewer
    this.#disposeEvents = ctx.on('session/event', (session, event) => {
      if (event.type === 'tool/call') {
        const calls = this.#calls.get(session.id) ?? new Map()
        calls.set(String(event.data.callId), String(event.data.arguments ?? ''))
        if (calls.size > 100) calls.delete(calls.keys().next().value)
        this.#calls.set(session.id, calls)
      }
      if (event.type === 'tool/result') this.#calls.get(session.id)?.delete(String(event.data.callId))
      if (event.type === 'user/message' || event.type === 'assistant/message') {
        const context = this.#context.get(session.id) ?? []
        context.push(JSON.stringify(event.data ?? {}).slice(0, 2_000))
        this.#context.set(session.id, context.slice(-8))
      }
      if (event.type === 'approval/asked') {
        const asked = this.#asked.get(session.id) ?? []
        asked.push(event)
        this.#asked.set(session.id, asked)
      } else if (event.type === 'approval/decided') {
        const asked = this.#asked.get(session.id) ?? []
        this.#asked.set(session.id, asked.filter(item => item.data.id !== event.data.id))
      }
    }, { global: true })
    // Plugin Web mounts DSH's remote approval answerer before this broker.
    // MOVO owns native approvals even when that auxiliary UI is available.
    // The enterprise bridge is registered later with prepend and keeps its tools.
    this.#disposeApproval = ctx.on('approval/request', async (request, next) => {
      if (this.excludedTools.has(request.toolName)) return next()
      const sessionId = String(request.agent.id)
      const callArguments = this.#calls.get(sessionId)?.get(String(request.callId ?? '')) ?? ''
      const grantKey = JSON.stringify([request.toolName, callArguments, request.reason ?? ''])
      if (callArguments && this.#sessionGrants.get(sessionId)?.has(grantKey)) return 'allowed-once'
      if (this.#reviewers.get(sessionId) === 'auto_review') {
        const recent = this.#reviewWindow.get(sessionId) ?? []
        const breakerOpen = (this.#denials.get(sessionId) ?? 0) >= 3 || recent.filter(value => !value).length >= 10
        if (!breakerOpen && callArguments) {
          const timeout = AbortSignal.timeout(30_000)
          const signal = request.signal ? AbortSignal.any([request.signal, timeout]) : timeout
          const result = await this.automaticReviewer?.review({
            sessionId, toolName: request.toolName, reason: request.reason ?? '',
            argumentsJson: callArguments, context: this.#context.get(sessionId) ?? [], signal,
          }).catch(() => ({ allowed: false }))
          this.#reviewWindow.set(sessionId, [...recent.slice(-49), result?.allowed === true])
          if (result?.allowed) {
            this.#denials.set(sessionId, 0)
            return 'allowed-once'
          }
          this.#denials.set(sessionId, (this.#denials.get(sessionId) ?? 0) + 1)
          return 'rejected'
        }
        // Repeated denials or missing exact call arguments require a person.
        // The existing approval/asked event becomes the visible, narrow request.
      }
      const asked = [...(this.#asked.get(sessionId) ?? [])].reverse().find(event => (
        event.data.toolName === request.toolName
        && (request.callId === undefined || event.data.callId === request.callId)
      ))
      if (asked === undefined) throw new Error('DSH approval request has no matching approval/asked event')
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
          argumentsJson: callArguments,
          grantKey,
          createdAt: Date.now(),
          finish,
        })
        request.signal?.addEventListener('abort', abort, { once: true })
      })
    }, { global: true, prepend: true })
  }

  list(sessionId) {
    return [...this.#pending.values()]
      .filter(item => item.sessionId === sessionId)
      .map(({ finish: _finish, grantKey: _grantKey, ...item }) => ({ ...item }))
  }

  setReviewer(sessionId, reviewer) {
    if (!['user', 'auto_review'].includes(reviewer)) throw new Error('unsupported approval reviewer')
    this.#reviewers.set(sessionId, reviewer)
  }

  decide(sessionId, approvalId, outcome, grantScope = 'once') {
    if (!OUTCOMES.has(outcome)) throw new Error(`unsupported approval outcome: ${outcome}`)
    if (!['once', 'session'].includes(grantScope)) throw new Error(`unsupported approval grant scope: ${grantScope}`)
    const pending = this.#pending.get(approvalId)
    if (pending === undefined || pending.sessionId !== sessionId) throw new Error('pending approval not found')
    if (outcome === 'allowed-once' && grantScope === 'session' && pending.argumentsJson) {
      const granted = this.#sessionGrants.get(sessionId) ?? new Set()
      granted.add(pending.grantKey)
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
    this.#asked.delete(sessionId)
    this.#calls.delete(sessionId)
    this.#context.delete(sessionId)
    this.#reviewers.delete(sessionId)
    this.#denials.delete(sessionId)
    this.#reviewWindow.delete(sessionId)
  }

  dispose() {
    for (const pending of [...this.#pending.values()]) pending.finish('cancelled')
    this.#sessionGrants.clear()
    this.#asked.clear()
    this.#calls.clear()
    this.#context.clear()
    this.#reviewers.clear()
    this.#denials.clear()
    this.#reviewWindow.clear()
    this.#disposeApproval?.()
    this.#disposeEvents?.()
  }
}
