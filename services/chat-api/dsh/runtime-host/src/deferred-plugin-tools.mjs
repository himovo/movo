import { createHash, randomUUID } from 'node:crypto'
import { scopeOf } from '@deepseek-ai/dsh-scope'
import { validateJsonSchemaValue } from '@deepseek-ai/dsh-tools'
import { assertNoDshCodeToolCollisions } from './official-host/tool-name-policy.mjs'

export const DEFERRED_PLUGIN_PREFIX = 'deferred-plugin:'

export function registerDeferredTools(ctx, plugins, invoke) {
  if (!plugins?.length) return () => {}
  if (!invoke) throw new Error('Deferred plugin executor is unavailable')
  assertNoDshCodeToolCollisions(plugins.flatMap(plugin => plugin.deferred_tool_contracts))
  const unregister = plugins.flatMap(plugin => plugin.deferred_tool_contracts.map(tool =>
    ctx.tools.register({
      name: tool.name,
      description: tool.description,
      parameters: tool.schema,
      output: { schema: {}, render: (_args, value) => value.content },
      timeoutMs: 180_000,
      execute: async (args, exec) => {
        if (validateJsonSchemaValue(tool.schema, args, 'arguments').length) {
          throw new Error('Invalid deferred plugin tool arguments')
        }
        return await invoke(plugin, tool.name, args, exec.signal)
      },
    })))
  return () => unregister.reverse().forEach(dispose => dispose())
}

export async function invokeDeferredTool(pool, prepareProfile, body, plugin, name, args, signal) {
  signal?.throwIfAborted()
  const { runtimePlacement, deferredPlugins, toolProfile, skillProfile, ...profile } = body.modelProfile
  const { deferred_tool_contracts, ...declaration } = plugin
  const key = createHash('sha256').update(JSON.stringify([body.isolationKey, plugin.installation_id])).digest('hex')
  const isolationKey = DEFERRED_PLUGIN_PREFIX + key
  const modelProfile = await prepareProfile({ ...profile, plugins: [declaration] })
  const runtime = pool.findByIsolation(isolationKey) ?? await pool.create({ ...body, isolationKey, modelProfile })
  signal?.throwIfAborted()
  return await pool.callDeferredTool(runtime.runtimeId, { name, args }, signal)
}

export async function executeDeferredTool(ctx, agent, name, args, signal) {
  if (!ctx.tools.executable(name, scopeOf(agent.ctx))) throw new Error('Deferred plugin tool is unavailable')
  const batch = await ctx.tools.execute({
    agent,
    signal,
    calls: [{ type: 'tool-call', id: randomUUID(), name, arguments: JSON.stringify(args) }],
  })
  const result = batch.results[0]?.result
  if (!result || result.isError) throw new Error(result?.error?.message || 'Deferred plugin tool failed')
  if (batch.additionalContexts.length || batch.concluded) {
    throw new Error('Deferred plugin tool requires a conversation-bound Runtime')
  }
  return { content: result.content }
}
