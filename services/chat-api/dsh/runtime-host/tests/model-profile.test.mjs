import assert from 'node:assert/strict'
import test from 'node:test'

import { normalizeModelProfile } from '../src/model-profile.mjs'

const valid = {
  profileVersion: 'profile-a',
  modelInstanceId: 'model-a',
  modelName: 'deepseek-chat',
  gatewayUrl: 'http://127.0.0.1/model',
  accessToken: 'ephemeral-token',
}

test('model profile accepts only the secret-free ephemeral Host schema', () => {
  assert.equal(normalizeModelProfile(valid, 'profile-a').modelInstanceId, 'model-a')
  assert.throws(
    () => normalizeModelProfile({ ...valid, apiKey: 'long-lived-secret' }, 'profile-a'),
    /forbidden fields: apiKey/,
  )
  assert.throws(
    () => normalizeModelProfile(valid, 'profile-b'),
    /version mismatch/,
  )
})

test('model profile validates deployment assistant identity', () => {
  assert.equal(normalizeModelProfile({ ...valid, agentName: 'Atlas' }, 'profile-a').agentName, 'Atlas')
  assert.throws(() => normalizeModelProfile({ ...valid, agentName: '' }, 'profile-a'), /agentName/)
  assert.throws(() => normalizeModelProfile({ ...valid, agentName: 'A'.repeat(81) }, 'profile-a'), /agentName/)
})

test('model profile rejects malformed or ambiguous Skill definitions', () => {
  const skill = {
    name: 'report-a1', version: 'skill-v1', source_id: 'skill-1',
    source_scope: 'organization', kind: 'ordinary', description: 'Report',
    content: 'Write a report.', capability_refs: [],
  }
  assert.throws(
    () => normalizeModelProfile({
      ...valid,
      skillProfile: { skills: [skill, { ...skill }], writingStyles: [] },
    }, 'profile-a'),
    /invalid Skill definition/,
  )
  assert.throws(
    () => normalizeModelProfile({
      ...valid,
      skillProfile: {
        skills: [],
        writingStyles: [{
          ref: 'style-a', version: 'style-v1', source_id: 'style-1',
          source_scope: 'organization', name: 'Report', instructions: '',
        }],
      },
    }, 'profile-a'),
    /invalid writing standard/,
  )
})

test('plugin tool prerequisites must name declared tools and supported capabilities', () => {
  const plugin = {
    name: 'office-example', version: '1.0.0', spec: 'office-example@1.0.0',
    source_scope: 'organization', tool_names: ['word_create'],
    tool_requirements: { word_create: ['workspace'] },
  }
  assert.equal(normalizeModelProfile({ ...valid, plugins: [plugin] }, 'profile-a')
    .plugins[0].tool_requirements.word_create[0], 'workspace')
  assert.throws(() => normalizeModelProfile({ ...valid, plugins: [{
    ...plugin, tool_requirements: { other_tool: ['workspace'] },
  }] }, 'profile-a'), /invalid DSH plugin declaration/)
  assert.throws(() => normalizeModelProfile({ ...valid, plugins: [{
    ...plugin, tool_requirements: { word_create: ['unknown'] },
  }] }, 'profile-a'), /invalid DSH plugin declaration/)
})
