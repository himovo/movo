import { randomUUID } from 'node:crypto'

/** Dispatch the native human command without scheduling an LLM user turn. */
export class NativeCompactionCommand {
  #active = new Map()

  accepts(content) {
    return content.length === 1 && content[0].type === 'text'
      && String(content[0].data?.text ?? '').trim() === '/compact'
  }

  isActive(sessionId) {
    return this.#active.has(sessionId)
  }

  start(ctx, agent) {
    if (this.isActive(agent.id)) throw new Error('Session already has an active compaction command')
    const commands = ctx.get('commands')
    const command = commands?.list(agent).find(item => item.name === 'compact')
    if (command?.definitionId !== '@deepseek-ai/dsh-command-compact') throw new Error('Native /compact command is unavailable')
    const controller = new AbortController()
    const operation = commands.execute(agent, '/compact', [], controller.signal)
    const settled = operation.catch(() => {
      // The native command registry persists the failure as command/done.
    }).finally(() => this.#active.delete(agent.id))
    this.#active.set(agent.id, { controller, settled })
    return { accepted: true, messageId: randomUUID() }
  }

  async cancel(sessionId) {
    const active = this.#active.get(sessionId)
    if (!active) return
    active.controller.abort()
    await active.settled
  }
}
