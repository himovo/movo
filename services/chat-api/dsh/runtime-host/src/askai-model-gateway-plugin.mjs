import { LlmAdapter, LlmError } from '@deepseek-ai/dsh-llm'

async function *readNdjson(response) {
  if (response.body === null) throw new Error('MOVO Model Gateway returned an empty stream')
  const decoder = new TextDecoder()
  let buffer = ''
  for await (const chunk of response.body) {
    buffer += decoder.decode(chunk, { stream: true })
    while (buffer.includes('\n')) {
      const index = buffer.indexOf('\n')
      const line = buffer.slice(0, index).trim()
      buffer = buffer.slice(index + 1)
      if (line) yield JSON.parse(line)
    }
  }
  buffer += decoder.decode()
  if (buffer.trim()) yield JSON.parse(buffer)
}

export class AskaiModelGatewayAdapter extends LlmAdapter {
  constructor(config) {
    super()
    this.config = Object.freeze(structuredClone(config))
  }

  updateCredential({ gatewayUrl, accessToken }) {
    if (!gatewayUrl || !accessToken) throw new Error('MOVO Model Gateway credential is incomplete')
    this.config = Object.freeze({ ...this.config, gatewayUrl, accessToken })
  }

  async listModels(provider) {
    return [{
      id: this.config.modelName,
      name: this.config.displayName || this.config.modelName,
      provider,
      contextWindow: this.config.contextWindow || undefined,
    }]
  }

  async resolveModel(provider, model) {
    if (model !== this.config.modelName) throw new Error(`profile model mismatch: ${model}`)
    return {
      provider,
      id: model,
      name: this.config.displayName || model,
      contextWindow: this.config.contextWindow || undefined,
    }
  }

  async *stream(options) {
    const response = await fetch(this.config.gatewayUrl, {
      method: 'POST',
      headers: {
        authorization: `Bearer ${this.config.accessToken}`,
        'content-type': 'application/json',
      },
      body: JSON.stringify({
        profileVersion: this.config.profileVersion,
        modelInstanceId: this.config.modelInstanceId,
        provider: options.provider,
        model: options.model,
        system: options.system,
        messages: options.messages,
        tools: options.tools,
        maxTokens: options.maxTokens,
        sessionId: options.sessionId,
      }),
      signal: options.signal,
    })
    if (!response.ok) {
      const payload = await response.json().catch(() => ({}))
      const code = payload?.error?.code ?? 'askai_model_gateway_error'
      const message = payload?.error?.message ?? `MOVO Model Gateway returned ${response.status}`
      throw new LlmError(message, String(code).toUpperCase(), { status: response.status })
    }
    let text = ''
    let textStarted = false
    let nextBlockIndex = 0
    let usage
    let finishReason = { kind: 'stop' }
    for await (const event of readNdjson(response)) {
      if (event?.type === 'text-delta') {
        const delta = String(event.text ?? '')
        if (!delta) continue
        if (!textStarted) {
          textStarted = true
          yield { type: 'block-start', index: nextBlockIndex, blockType: 'text' }
        }
        text += delta
        yield { type: 'text-delta', index: nextBlockIndex, text: delta }
      } else if (event?.type === 'tool-call') {
        if (textStarted) {
          yield { type: 'block-end', index: nextBlockIndex, block: { type: 'text', text } }
          nextBlockIndex += 1
          textStarted = false
        }
        const id = String(event.id ?? '')
        const name = String(event.name ?? '')
        const args = String(event.arguments ?? '{}')
        yield { type: 'block-start', index: nextBlockIndex, blockType: 'tool-call' }
        yield { type: 'tool-call-delta', index: nextBlockIndex, id, name, argumentsDelta: args }
        yield { type: 'block-end', index: nextBlockIndex, block: { type: 'tool-call', id, name, arguments: args } }
        nextBlockIndex += 1
      } else if (event?.type === 'usage') {
        usage = event.usage
      } else if (event?.type === 'finish') {
        finishReason = event.reason ?? finishReason
      } else if (event?.type === 'error') {
        const code = event.error?.code ?? 'askai_model_gateway_error'
        const message = event.error?.message ?? 'MOVO Model Gateway stream failed'
        throw new LlmError(message, String(code).toUpperCase(), { retryable: Boolean(event.error?.retryable) })
      }
    }
    if (textStarted) yield { type: 'block-end', index: nextBlockIndex, block: { type: 'text', text } }
    if (usage !== undefined) yield { type: 'usage', usage }
    yield { type: 'finish', reason: finishReason }
  }
}

export const name = 'askai-model-gateway'
export const inject = ['llm']

export function apply(ctx, config) {
  if (!config?.gatewayUrl || !config?.accessToken || !config?.modelInstanceId || !config?.modelName) {
    throw new Error('MOVO Model Gateway profile is incomplete')
  }
  return ctx.llm.registerAdapter(['askai-model-gateway'], new AskaiModelGatewayAdapter(config))
}
