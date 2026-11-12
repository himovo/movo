import { randomUUID } from 'node:crypto'

/** Bridges DSH's scoped human-question waterfall to the MOVO client. */
export class UserQuestionBroker {
  #pending = new Map()
  #answered = new Map()
  #dispose

  constructor(ctx) {
    this.#dispose = ctx.on('user-questions/request', (request, next) => {
      const sessionId = String(request.agent?.session?.id ?? '')
      if (!sessionId) return next()
      const questionId = String(request.wait?.callId ?? randomUUID())
      const key = JSON.stringify([sessionId, questionId])
      if (this.#pending.has(key)) throw new Error('duplicate user question call')
      return new Promise((resolve, reject) => {
        const abort = () => {
          request.signal?.removeEventListener('abort', abort)
          this.#pending.delete(key)
          reject(new Error('user question was cancelled'))
        }
        const settle = answer => {
          request.signal?.removeEventListener('abort', abort)
          this.#pending.delete(key)
          resolve(answer)
        }
        this.#pending.set(key, {
          id: questionId,
          sessionId,
          questions: structuredClone(request.questions),
          createdAt: Date.now(),
          settle,
          abort,
        })
        request.signal?.addEventListener('abort', abort, { once: true })
        if (request.signal?.aborted) abort()
      })
    }, { global: true })
  }

  list(sessionId) {
    return [...this.#pending.values()]
      .filter(item => item.sessionId === sessionId)
      .map(({ settle: _settle, abort: _abort, ...publicItem }) => publicItem)
  }

  answer(sessionId, questionId, answers) {
    const key = JSON.stringify([sessionId, questionId])
    const previous = this.#answered.get(key)
    if (previous) return structuredClone(previous)
    const item = this.#pending.get(key)
    if (!item || item.sessionId !== sessionId) throw new Error('pending user question not found')
    if (!Array.isArray(answers) || answers.length !== item.questions.length) {
      throw new Error('one answer is required for each question')
    }
    const questions = new Map(item.questions.map(question => [question.id, question]))
    const seen = new Set()
    for (const answer of answers) {
      if (!answer || typeof answer.id !== 'string' || !questions.has(answer.id) || seen.has(answer.id)
          || !Array.isArray(answer.selected) || answer.selected.some(value => typeof value !== 'string')
          || (answer.custom !== undefined && typeof answer.custom !== 'string')) {
        throw new Error('invalid user question answer')
      }
      const question = questions.get(answer.id)
      const allowed = new Set((question.options ?? []).map(option => option.label))
      if (answer.selected.some(value => !allowed.has(value))
          || new Set(answer.selected).size !== answer.selected.length
          || (!question.multiSelect && answer.selected.length > 1)
          || (!question.multiSelect && answer.selected.length && answer.custom !== undefined)
          || (!answer.selected.length && !answer.custom?.trim())
          || (answer.custom !== undefined && !answer.custom.trim())) {
        throw new Error('invalid user question choice')
      }
      seen.add(answer.id)
    }
    const receipt = { answered: true, questionId, questions: structuredClone(item.questions), answers: structuredClone(answers) }
    this.#answered.set(key, receipt)
    item.settle({ answers })
    return structuredClone(receipt)
  }

  clearSession(sessionId) {
    for (const item of [...this.#pending.values()]) if (item.sessionId === sessionId) item.abort()
    for (const key of this.#answered.keys()) if (JSON.parse(key)[0] === sessionId) this.#answered.delete(key)
  }

  dispose() {
    for (const item of [...this.#pending.values()]) item.abort()
    this.#dispose?.()
    this.#answered.clear()
  }
}
