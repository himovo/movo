export class EventJournal {
  #events = new Map()
  #subscribers = new Map()

  append(sessionId, nativeType, data, nativeSeq = undefined) {
    const events = this.#events.get(sessionId) ?? []
    const cursor = events.length === 0 ? 1 : events.at(-1).cursor + 1
    const event = Object.freeze({
      cursor,
      nativeType,
      nativeSeq,
      time: Date.now(),
      data: structuredClone(data ?? {}),
    })
    events.push(event)
    this.#events.set(sessionId, events)
    for (const subscriber of this.#subscribers.get(sessionId) ?? []) subscriber(event)
    return event
  }

  replay(sessionId, afterCursor = -1) {
    return (this.#events.get(sessionId) ?? []).filter(event => event.cursor > afterCursor)
  }

  subscribe(sessionId, afterCursor, subscriber) {
    const subscribers = this.#subscribers.get(sessionId) ?? new Set()
    subscribers.add(subscriber)
    this.#subscribers.set(sessionId, subscribers)
    const replay = this.replay(sessionId, afterCursor)
    return {
      replay,
      unsubscribe: () => {
        subscribers.delete(subscriber)
        if (subscribers.size === 0) this.#subscribers.delete(sessionId)
      },
    }
  }

  resetFromSession(session) {
    this.#events.set(session.id, [])
    for (const event of session.events) {
      this.append(session.id, event.type, event.data, event.seq)
    }
  }

  remove(sessionId) {
    this.#events.delete(sessionId)
    this.#subscribers.delete(sessionId)
  }
}
