import { compatibleSessionEvents } from './event-compat.mjs'

function stepKey(turn, step) {
  return `${turn}:${step}`
}

/** Bridge transient DSH frames into MOVO's cursor-based event stream. */
export class LiveAssistantStream {
  #journal
  #attempts = new Map()
  #commands = new Set()

  constructor(journal) {
    this.#journal = journal
  }

  observeFrame(sessionId, frame) {
    const attempts = this.#attempts.get(sessionId) ?? new Map()
    if (frame.type === 'start') {
      attempts.set(stepKey(frame.turn, frame.step), {
        attemptId: frame.attemptId,
        turn: frame.turn,
        step: frame.step,
      })
      this.#attempts.set(sessionId, attempts)
      return
    }

    const attempt = [...attempts.values()].find(value => value.attemptId === frame.attemptId)
    if (attempt === undefined) return
    if (frame.type === 'end') {
      attempts.delete(stepKey(attempt.turn, attempt.step))
      if (attempts.size === 0) this.#attempts.delete(sessionId)
      return
    }
    this.#journal.append(sessionId, 'assistant/chunk', {
      turn: attempt.turn,
      step: attempt.step,
      chunk: frame.chunk,
      live: {
        attemptId: frame.attemptId,
        revision: frame.revision,
        index: frame.index,
        time: frame.time,
      },
    })
  }

  observeSessionEvent(session, event) {
    const attempt = this.#attempts.get(session.id)?.get(stepKey(event.data?.turn, event.data?.step))
    const settled = event.type === 'assistant/message' || event.type === 'assistant/attempt'
    // DSH commits the durable event before publishing the matching end frame.
    const events = settled && attempt !== undefined ? [event] : compatibleSessionEvents(event, this.#commands)
    for (const compatible of events) {
      this.#journal.append(session.id, compatible.type, compatible.data, compatible.seq ?? event.seq)
    }
  }

  remove(sessionId) {
    this.#attempts.delete(sessionId)
  }
}
