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
