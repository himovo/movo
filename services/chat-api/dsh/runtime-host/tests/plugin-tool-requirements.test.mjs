import test from 'node:test'
import assert from 'node:assert/strict'

import { eligibleEnterpriseTools } from '../src/official-host/session-composer.mjs'

test('ordinary sessions omit only tools whose declared workspace prerequisite is absent', () => {
  const names = ['run_script', 'word_create', 'word_read', 'other_tool']
  const plugins = [{
    name: 'office-example',
    tool_names: ['word_create', 'word_read'],
    tool_requirements: { word_create: ['workspace'], word_read: ['workspace'] },
  }]
  assert.deepEqual(eligibleEnterpriseTools(names, plugins, { hasWorkspace: false }),
    ['run_script', 'other_tool'])
  assert.deepEqual(eligibleEnterpriseTools(names, plugins, { hasWorkspace: true }),
    [...names, 'present'])
})
