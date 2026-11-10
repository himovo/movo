export const inject = ['tools', 'commands', 'webServer', 'connection', 'llm', 'agentDefaultModel']
export const name = 'movo-dsh-test-bundle'

export function apply(ctx) {
  ctx.effect(() => ctx.webServer.register({
    kind: 'prefix', path: '/movo-fixture',
    handler: async (request, response) => {
      const rejection = ctx.connection.requestRejection(request)
      if (rejection) {
        response.writeHead(rejection)
        response.end()
        return
      }
      if (request.url === '/movo-fixture/model') {
        try {
          const selection = ctx.agentDefaultModel.currentSelection()
          const call = await ctx.llm.prepareCall(selection)
          let text = ''
          for await (const event of call.stream({
            ...call.config, system: 'Reply with a test marker',
            messages: [{ role: 'user', content: [{ type: 'text', text: 'test' }] }],
            sessionId: 'plugin-model-fixture',
          })) if (event.type === 'text-delta') text += event.text
          response.writeHead(200, { 'content-type': 'application/json' })
          response.end(JSON.stringify({ text, selection }))
        } catch (error) {
          response.writeHead(500)
          response.end(String(error))
        }
        return
      }
      response.writeHead(200, { 'content-type': 'application/json' })
      response.end(JSON.stringify({ marker: 'FIXTURE_UI_READY' }))
    },
  }), 'fixture plugin browser route')
  ctx.provide('movoDshTestBundle', { ready: true })
  ctx.commands.register({
    definitionId: 'movo-plugin-smoke-command',
    name: 'movo-smoke',
    description: 'Return a deterministic command execution marker.',
    handler: async ({ rawInput }) => ({ kind: 'success', text: `MOVO_COMMAND_EXECUTED${rawInput}` }),
  })
  ctx.tools.register({
    name: 'movo_plugin_smoke',
    description: 'Return a deterministic plugin execution marker.',
    parameters: { type: 'object', properties: {}, additionalProperties: false },
    output: {
      schema: { type: 'object', properties: { marker: { type: 'string' } }, required: ['marker'] },
      render: (_args, value) => [{ type: 'text', text: value.marker }],
    },
    execute: async () => ({ marker: 'MOVO_PLUGIN_EXECUTED' }),
  })
}
