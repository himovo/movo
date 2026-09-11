import assert from 'node:assert/strict'
import test from 'node:test'

import { registerSkillResourceTool, SKILL_RESOURCE_READ_TOOL } from '../src/skill-resource-tool.mjs'

test('reads resources only from the Skill active in the current session', async () => {
  let contract
  const ctx = { tools: { register(value) { contract = value; return () => {} } } }
  const calls = []
  const provider = {
    hasResourceBundles: () => true,
    async readTextResource(name, options) { calls.push({ name, options }); return { content: 'ok' } },
  }
  const invocations = { current: sessionId => sessionId === 'session-a' ? 'sample' : undefined }
  registerSkillResourceTool(ctx, { provider, invocations })
  assert.equal(contract.name, SKILL_RESOURCE_READ_TOOL)
  assert.deepEqual(await contract.execute(
    { path: 'assets/contacts.json', start_line: 3, line_count: 20 },
    { agent: { id: 'session-a' } },
  ), { content: 'ok' })
  assert.deepEqual(calls, [{
    name: 'sample',
    options: { path: 'assets/contacts.json', startLine: 3, lineCount: 20 },
  }])
  await assert.rejects(
    contract.execute({ path: 'assets/contacts.json' }, { agent: { id: 'session-b' } }),
    /Select or invoke a Skill/,
  )
})

test('does not register a resource tool when the profile has no package resources', () => {
  let registered = false
  const ctx = { tools: { register() { registered = true } } }
  const result = registerSkillResourceTool(ctx, {
    provider: { hasResourceBundles: () => false }, invocations: {},
  })
  assert.equal(result, undefined)
  assert.equal(registered, false)
})
