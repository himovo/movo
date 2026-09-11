export class SkillInvocationTracker {
  #skillsByName
  #manualBySession = new Map()
  #observedBySession = new Map()
  #activeBySession = new Map()

  constructor(skillProfile) {
    this.#skillsByName = new Map(
      (skillProfile?.skills ?? []).map(skill => [skill.name, Object.freeze({
        sourceId: skill.source_id,
        displayName: String(skill.display_name || skill.name),
        sourceScope: skill.source_scope,
      })]),
    )
  }

  expectManual(sessionId, skillName) {
    if (skillName) this.#manualBySession.set(sessionId, skillName)
    else this.#manualBySession.delete(sessionId)
  }

  observe(sessionId, event) {
    if (event?.type === 'turn/start') {
      this.#observedBySession.delete(sessionId)
      this.#activeBySession.delete(sessionId)
      return undefined
    }
    if (event?.type === 'turn/end') {
      this.#manualBySession.delete(sessionId)
      this.#observedBySession.delete(sessionId)
      this.#activeBySession.delete(sessionId)
      return undefined
    }
    const skillName = this.#invokedSkillName(event)
    if (!skillName) return undefined
    const skill = this.#skillsByName.get(skillName)
    if (skill === undefined) return undefined
    this.#activeBySession.set(sessionId, skillName)
    const observed = this.#observedBySession.get(sessionId) ?? new Set()
    if (observed.has(skillName)) return undefined
    observed.add(skillName)
    this.#observedBySession.set(sessionId, observed)
    const manual = this.#manualBySession.get(sessionId) === skillName
    if (manual) this.#manualBySession.delete(sessionId)
    return { ...skill, selectionMode: manual ? 'manual' : 'automatic' }
  }

  current(sessionId) {
    return this.#activeBySession.get(sessionId)
  }

  #invokedSkillName(event) {
    if (event?.type === 'user/message' && event?.data?.source?.kind === 'skill-invocation') {
      return String(event.data.source.name || '')
    }
    if (event?.type !== 'tool/call' || event?.data?.name !== 'skill') return ''
    const raw = event.data.arguments
    try {
      const args = typeof raw === 'string' ? JSON.parse(raw) : raw
      return args && typeof args === 'object' ? String(args.name || '') : ''
    } catch {
      return ''
    }
  }

  clear(sessionId) {
    this.#manualBySession.delete(sessionId)
    this.#observedBySession.delete(sessionId)
    this.#activeBySession.delete(sessionId)
  }
}
