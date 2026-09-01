import { LlmAdapter } from '@deepseek-ai/dsh-llm'

const DEFAULT_DELAY_MS = 5

function abortableDelay(delayMs, signal) {
  if (signal?.aborted) return Promise.reject(signal.reason ?? new Error('aborted'))
  return new Promise((resolve, reject) => {
    const timer = setTimeout(resolve, delayMs)
    signal?.addEventListener('abort', () => {
      clearTimeout(timer)
      reject(signal.reason ?? new Error('aborted'))
    }, { once: true })
  })
}

function latestUserText(messages) {
  const message = messages.findLast(item => item.role === 'user' && item.source?.kind === 'user')
    ?? messages.findLast(item => item.role === 'user')
  if (message === undefined) return ''
  return message.content
    .filter(block => block.type === 'text')
    .map(block => block.text)
    .join('\n')
}

class AskaiDeterministicAdapter extends LlmAdapter {
  async listModels(provider) {
    return [{ id: 'deterministic-v1', name: 'MOVO deterministic v1', provider }]
  }

  async resolveModel(provider, model) {
    return { provider, id: model, name: model, contextWindow: 32_768 }
  }

  async *stream(options) {
    const input = latestUserText(options.messages)
    const delayMs = input.includes('[slow]') ? 1_500 : DEFAULT_DELAY_MS
    await abortableDelay(delayMs, options.signal)
    options.signal?.throwIfAborted()

    const text = `DSH deterministic: ${input}`
    yield { type: 'block-start', index: 0, blockType: 'text' }
    yield { type: 'text-delta', index: 0, text }
    yield { type: 'block-end', index: 0, block: { type: 'text', text } }
    yield {
      type: 'usage',
      usage: {
        inputTokens: Math.max(1, Math.ceil(input.length / 4)),
        outputTokens: Math.max(1, Math.ceil(text.length / 4)),
      },
    }
    yield { type: 'finish', reason: { kind: 'stop' } }
  }
}

export const name = 'askai-deterministic-model'
export const inject = ['llm']

export function apply(ctx) {
  return ctx.llm.registerAdapter(['askai-deterministic'], new AskaiDeterministicAdapter())
}
