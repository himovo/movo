import assert from 'node:assert/strict'
import test from 'node:test'
import { mkdtemp, mkdir, writeFile, symlink, rm } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { deferredToolOwners } from '../src/deferred-plugin-registry.mjs'
import { readPluginSkillResource } from '../src/deferred-skill-resources.mjs'
import { registerDeferredSkills } from '../src/deferred-plugin-skills.mjs'

test('mixed plugins publish only unique nonreserved tool contracts', () => {
  const contract = name => ({ name, description: name, schema: { type: 'object' } })
  const plugins = [
    { name: 'mixed', skills: [{ name: 'review' }], deferred_tool_contracts: [contract('lookup'), contract('read'), contract('duplicate')] },
    { name: 'legacy' },
    { name: 'ui', commands: [{}], deferred_tool_contracts: [contract('duplicate'), contract('occupied')] },
  ]
  assert.deepEqual(deferredToolOwners(plugins, ['occupied']).map(({ tool }) => tool.name), ['lookup'])
})

test('Skill listing does not execute a plugin, loading invokes only its owner', async () => {
  let provider
  const calls = []
  const ctx = { skills: { registerProvider(factory) { provider = factory(); return () => {} } } }
  registerDeferredSkills(ctx, [{
    installation_id: 'owner', skills: [{ name: 'review', description: 'Review', userInvocable: true, modelInvocable: true }],
  }], async (...args) => { calls.push(args); return { content: 'instructions' } })
  const [candidate] = await provider.list()
  assert.equal(calls.length, 0)
  const agent = { session: {} }
  assert.equal((await provider.get(candidate, { scope: agent })).content, 'instructions')
  assert.equal(calls[0][0].installation_id, 'owner')
  assert.equal(calls[0][3].operation, 'skill')
})

test('Skill resource reads stay inside the actual package including symlink targets', async () => {
  const root = await mkdtemp(join(tmpdir(), 'movo-deferred-resource-'))
  const directory = join(root, 'package')
  try {
    await mkdir(directory)
    await writeFile(join(directory, 'guide.txt'), 'resource content')
    await writeFile(join(root, 'secret.txt'), 'outside')
    await symlink(join(root, 'secret.txt'), join(directory, 'escape.txt'))
    const skill = { resourceBase: { kind: 'directory', path: directory } }
    assert.equal((await readPluginSkillResource(skill, 'guide.txt')).content[0].text, 'resource content')
    await assert.rejects(readPluginSkillResource(skill, '../secret.txt'))
    await assert.rejects(readPluginSkillResource(skill, 'escape.txt'))
    await assert.rejects(readPluginSkillResource(skill, join(root, 'secret.txt')))
  } finally { await rm(root, { recursive: true, force: true }) }
})
