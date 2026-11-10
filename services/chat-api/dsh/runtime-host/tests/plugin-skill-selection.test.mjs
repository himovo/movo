import assert from 'node:assert/strict'
import test from 'node:test'

import { resolveSkillTurnContext } from '../src/skill-turn-selection.mjs'

const id = `dsh_plugin_skill:${'a'.repeat(24)}:${Buffer.from('paper-review').toString('base64url')}`
const profile = {
  plugins: [{
    installation_id: 'a'.repeat(24), name: 'paper-plugin',
    skills: [{ name: 'paper-review', provider: 'paper-plugin', source: 'bundled', userInvocable: true }],
  }],
}

test('a selected plugin Skill resolves only from the immutable authorized plugin profile', () => {
  const selected = resolveSkillTurnContext(profile, { selected_skill_id: id })
  assert.equal(selected.skillName, 'paper-review')
  assert.equal(selected.selectedSkill.pluginName, 'paper-plugin')
  assert.throws(() => resolveSkillTurnContext(profile, {
    selected_skill_id: `dsh_plugin_skill:${'b'.repeat(24)}:${Buffer.from('paper-review').toString('base64url')}`,
  }), /unavailable/)
  assert.throws(() => resolveSkillTurnContext(profile, {
    selected_skill_id: `dsh_plugin_skill:${'a'.repeat(24)}:${Buffer.from('other-skill').toString('base64url')}`,
  }), /unavailable/)
})
