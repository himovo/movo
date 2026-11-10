import assert from 'node:assert/strict'
import test from 'node:test'

import { globalPluginCapabilities, sessionPluginCapabilities } from '../src/official-host/plugin-capability-snapshot.mjs'

test('DSH skill and command registries remain the source of session capability discovery', async () => {
  const observed = []
  const skills = { list: async options => {
    observed.push(options)
    return [{
      name: 'paper-review', description: 'Review a paper', source: 'bundled',
      provider: 'paper-plugin', invocation: { modelInvocable: true, userInvocable: false },
    }]
  } }
  const commands = { list: agent => {
    assert.equal(agent.id, 'session-a')
    return [{ name: 'paper', description: 'Open a paper' }]
  } }
  const llm = {
    listProviders: () => [{ id: 'paper-provider', name: 'Paper Models' }],
    listModels: async () => { throw new Error('model catalog must not be queried') },
  }
  const webServer = {
    exact: new Map([['/papers/report', {}]]),
    prefixes: new Map([['/api', {}], ['/papers', {}]]),
  }
  const typertGateway = { collectSrcClaims: () => new Set(['paper/list']) }
  const typert = { local: { list: () => [{ namespace: 'paper', method: 'create' }] } }
  const ctx = { get: name => ({ skills, commands, llm, webServer, typertGateway, typert })[name] }
  const agent = { id: 'session-a', ctx: {}, session: { header: { cwd: '/workspace' } } }

  const global = await globalPluginCapabilities(ctx)
  const session = await sessionPluginCapabilities(ctx, agent)
  assert.equal(global.skills[0].userInvocable, false)
  assert.deepEqual(session.commands, [{ name: 'paper', description: 'Open a paper' }])
  assert.deepEqual(session.modelProviders, [{ id: 'paper-provider', name: 'Paper Models' }])
  assert.deepEqual(session.webRoutes, [
    { kind: 'prefix', path: '/api' },
    { kind: 'prefix', path: '/papers' },
    { kind: 'exact', path: '/papers/report' },
  ])
  assert.deepEqual(session.remoteEndpoints, ['paper/create', 'paper/list'])
  assert.equal(observed[1].cwd, '/workspace')
})
