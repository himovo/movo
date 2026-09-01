import assert from 'node:assert/strict'
import test from 'node:test'

import { AskaiSkillProvider } from '../src/askai-skill-provider.mjs'
import { normalizeTurnContext, renderTurnContext } from '../src/runtime-turn-context.mjs'
import { invokeSelectedSkill, resolveSkillTurnContext } from '../src/skill-turn-selection.mjs'

const profile = {
  skills: [{
    name: 'research-report-a1', version: 'skill-v1', source_id: 'workflow-1',
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
  assert.equal(selected.context.writing_style.instructions, 'Concise.')
  assert.throws(
    () => resolveSkillTurnContext(modelProfile, { selected_skill_id: 'stale' }),
    /immutable Runtime Profile/,
  )
})
