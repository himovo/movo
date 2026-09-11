import assert from 'node:assert/strict'
import { createHash } from 'node:crypto'
import { mkdtemp, rm } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import test from 'node:test'
import { strToU8, zipSync } from 'fflate'

import { AskaiSkillProvider } from '../src/askai-skill-provider.mjs'
import { normalizeTurnContext, renderTurnContext } from '../src/runtime-turn-context.mjs'
import { invokeSelectedSkill, resolveSkillTurnContext } from '../src/skill-turn-selection.mjs'

const profile = {
  skills: [{
    name: 'research-report-a1', version: 'skill-v1', source_id: 'workflow-1',
    display_name: 'Research report',
    source_scope: 'organization', kind: 'workflow', description: 'Research report',
    when_to_use: 'Use for research reports', content: '# Steps\nUse governed tools.',
    capability_refs: ['research.progressive@v1'],
  }],
}

test('ASKAI provider exposes immutable DSH candidates and bodies', async () => {
  const provider = new AskaiSkillProvider(profile)
  const candidates = await provider.list()
  assert.equal(candidates.length, 1)
  assert.equal(candidates[0].provider, 'askai-enterprise')
  assert.equal(candidates[0].invocation.modelInvocable, true)
  const definition = await provider.get(candidates[0])
  assert.equal(definition.content, '# Steps\nUse governed tools.')
  assert.equal(definition.resourceBase.kind, 'opaque')
})

test('bundled Skill resources are exposed through the provider-managed reader', async () => {
  const root = await mkdtemp(join(tmpdir(), 'movo-provider-resource-'))
  const archive = Buffer.from(zipSync({
    'foshan/SKILL.md': strToU8('# Foshan'),
    'foshan/assets/contacts.json': strToU8('{"phone":"0757-123456"}'),
  }))
  const bundledProfile = { skills: [{
    ...profile.skills[0], name: 'foshan-guide', bundle_root: 'foshan/',
    bundle_digest: createHash('sha256').update(archive).digest('hex'),
    bundle_archive_base64: archive.toString('base64'),
  }] }
  try {
    const provider = new AskaiSkillProvider(bundledProfile, { storageRoot: root })
    const definition = await provider.get((await provider.list())[0])
    assert.equal(definition.resourceBase.kind, 'opaque')
    assert.match(definition.resourceBase.description, /skill_resource_read/)
    assert.deepEqual(await provider.readTextResource('foshan-guide', {
      path: 'assets/contacts.json',
    }), {
      skill: 'foshan-guide', path: 'assets/contacts.json', content: '{"phone":"0757-123456"}',
      startLine: 1, endLine: 1, totalLines: 1, truncated: false,
    })
  } finally {
    await rm(root, { recursive: true, force: true })
  }
})

test('writing standard prompt is explicitly scoped to writing only', () => {
  const rendered = renderTurnContext(normalizeTurnContext({
    writing_style: { name: 'Board style', instructions: 'Use concise prose.' },
  }))
  assert.match(rendered, /only when authoring or rewriting prose/)
  assert.match(rendered, /must not change retrieval choices/)
  assert.match(rendered, /If the task is not writing, ignore this standard completely/)
})

test('manual selection uses DSH native slash invocation and rejects stale profile ids', () => {
  const modelProfile = {
    skillProfile: {
      ...profile,
      writingStyles: [{ source_id: 'style-1', name: 'Board style', instructions: 'Concise.' }],
    },
  }
  const selected = resolveSkillTurnContext(modelProfile, {
    selected_skill_id: 'workflow-1', selected_writing_skill_id: 'style-1',
  })
  assert.equal(invokeSelectedSkill(selected.skillName, 'do it'), '/research-report-a1\ndo it')
  assert.deepEqual(selected.selectedSkill, {
    sourceId: 'workflow-1', displayName: 'Research report', sourceScope: 'organization',
  })
  assert.equal(selected.context.writing_style.instructions, 'Concise.')
  assert.throws(
    () => resolveSkillTurnContext(modelProfile, { selected_skill_id: 'stale' }),
    /immutable Runtime Profile/,
  )
})
