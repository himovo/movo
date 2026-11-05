export class EventJournal {
  #events = new Map()
  #subscribers = new Map()
  #cursorFloors = new Map()

  append(sessionId, nativeType, data, nativeSeq = undefined) {
    const events = this.#events.get(sessionId) ?? []
    const cursor = Math.max(events.at(-1)?.cursor ?? 0, this.#cursorFloors.get(sessionId) ?? 0) + 1
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

  head(sessionId) {
    const events = this.#events.get(sessionId) ?? []
    return Math.max(events.at(-1)?.cursor ?? 0, this.#cursorFloors.get(sessionId) ?? 0)
  }

  ensureCursorFloor(sessionId, floor) {
    if (!Number.isSafeInteger(floor) || floor < 0) throw new TypeError('cursor floor must be a nonnegative safe integer')
    this.#cursorFloors.set(sessionId, Math.max(this.#cursorFloors.get(sessionId) ?? 0, floor))
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

  resetFromEvents(sessionId, persistedEvents) {
    this.#events.set(sessionId, [])
    this.#cursorFloors.delete(sessionId)
    for (const event of persistedEvents) {
      this.append(sessionId, event.type, event.data, event.seq)
    }
  }

  remove(sessionId) {
    this.#events.delete(sessionId)
    this.#subscribers.delete(sessionId)
    this.#cursorFloors.delete(sessionId)
  }
}
