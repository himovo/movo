import { validateJsonSchemaValue } from '@deepseek-ai/dsh-tools'
import { postGatewayJson } from './gateway-http-client.mjs'
import { assertNoDshCodeToolCollisions } from './official-host/tool-name-policy.mjs'

const APPROVAL_WAIT_SECONDS = 240
const TOOL_GATEWAY_DEADLINE_GRACE_MS = 30_000

export function validateDescriptorArguments(descriptor, args) {
  return validateJsonSchemaValue(descriptor.input_schema, args, 'arguments')
}

function unwrapGatewayResponse(response) {
  const payload = response.payload ?? {}
  if (!response.ok) {
    const detail = payload?.detail
    const message = typeof detail === 'string' ? detail : detail?.message
    throw new Error(message || `MOVO Tool Gateway returned ${response.status}`)
  }
  return payload
}

export class AskaiToolBridge {
  #config
  #disposers = []
  #approvalArguments = new Map()
  #requestJson

  constructor(ctx, config, { requestJson = postGatewayJson } = {}) {
    this.#config = Object.freeze(structuredClone(config))
    this.#requestJson = requestJson
    assertNoDshCodeToolCollisions(this.#config.tools)
    const nativeReplacements = new Set(this.#config.nativeReplacements ?? [])
    for (const descriptor of this.#config.tools) {
      if (nativeReplacements.has(descriptor.name)) continue
      this.#disposers.push(ctx.tools.register({
        name: descriptor.name,
        description: descriptor.description,
        parameters: descriptor.input_schema,
        output: {
          schema: descriptor.output_validation === 'none' ? {} : (descriptor.output_schema ?? {}),
          render: (_args, value) => [{ type: 'text', text: JSON.stringify(value) }],
        },
        // ASKAI's gateway owns the capability deadline and persists the final
        // receipt. Give it a short cleanup window before DSH aborts the HTTP
        // bridge so both layers cannot race at the exact same deadline.
        timeoutMs: descriptor.timeout_ms + TOOL_GATEWAY_DEADLINE_GRACE_MS,
        isConcurrencySafe: () => descriptor.risk_level === 'read',
        execute: async (args, exec) => {
          const violations = validateDescriptorArguments(descriptor, args)
          if (violations.length > 0) throw new Error(`invalid tool arguments: ${violations.join('; ')}`)
          const key = `${exec.agent?.id ?? ''}:${String(exec.callId)}`
          try {
            const payload = await this.#post('/execute', {
              profileVersion: this.#config.profileVersion,
              sessionId: exec.agent?.id,
              toolName: descriptor.name,
              actionId: String(exec.callId),
              idempotencyKey: `${exec.agent?.id ?? 'no-session'}:${String(exec.callId)}`,
              arguments: args,
            }, exec.signal)
            return payload.result
          } finally {
            this.#approvalArguments.delete(key)
          }
        },
      }))
    }
    this.#disposers.push(ctx.on('tools/pre-execute', async (exec, next) => {
      const descriptor = this.#config.tools.find(item => item.name === exec.name)
      if (descriptor === undefined || nativeReplacements.has(descriptor.name)) return next()
      const violations = validateDescriptorArguments(descriptor, exec.arguments)
      if (violations.length > 0) {
        return {
          kind: 'deny',
          reason: `invalid tool arguments: ${violations.join('; ')}`,
        }
      }
      const dynamicApproval = descriptor.approval_argument
        && Array.isArray(descriptor.approval_values)
        && descriptor.approval_values.includes(String(exec.arguments?.[descriptor.approval_argument] ?? ''))
      if (descriptor.approval_required || dynamicApproval) {
        this.#approvalArguments.set(`${exec.agent?.id ?? ''}:${String(exec.callId)}`, structuredClone(exec.arguments ?? {}))
        return { kind: 'ask', reason: `MOVO policy requires approval for ${descriptor.risk_level} tool ${descriptor.name}` }
      }
      return { kind: 'allow' }
    }))
    this.#disposers.push(ctx.on('approval/request', async (request, next) => {
      const descriptor = this.#config.tools.find(item => item.name === request.toolName)
      if (descriptor === undefined) return next()
      const key = `${request.agent.id}:${String(request.callId ?? '')}`
      try {
        const payload = await this.#post('/approval/request', {
          profileVersion: this.#config.profileVersion,
          sessionId: request.agent.id,
          toolName: request.toolName,
          actionId: String(request.callId ?? ''),
          reason: request.reason ?? '',
          arguments: this.#approvalArguments.get(key) ?? {},
          // Resolve before DSH's native approval answerer reaches its own deadline.
          timeoutSeconds: APPROVAL_WAIT_SECONDS,
        }, request.signal)
        return payload.outcome
      } finally {
        this.#approvalArguments.delete(key)
      }
    }))
  }

  updateCredential(accessToken) {
    if (typeof accessToken !== 'string' || !accessToken) throw new Error('Tool Gateway credential is empty')
    this.#config = Object.freeze({ ...this.#config, accessToken })
  }

  dispose() {
    this.#approvalArguments.clear()
    for (const dispose of this.#disposers.splice(0).reverse()) dispose()
  }

  async #post(path, body, signal) {
    const response = await this.#requestJson(`${this.#config.gatewayUrl}${path}`, body, {
      headers: { authorization: `Bearer ${this.#config.accessToken}` },
      signal,
    })
    return unwrapGatewayResponse(response)
  }
}
