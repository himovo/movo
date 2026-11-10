import assert from 'node:assert/strict'
import test from 'node:test'

import { pluginClientShellPatches } from '../src/official-host/plugin-client-shell.mjs'

test('plugin client shell includes native workspace and conversation providers', () => {
  const names = [
    '@deepseek-ai/dsh-client-ui-renderer',
    '@deepseek-ai/dsh-api-workspace-controller',
    '@deepseek-ai/dsh-client-ui-conversation',
    '@deepseek-ai/dsh-client-ui-layout',
  ]
  const [patch] = pluginClientShellPatches([{ insert: names.map((name, id) => ({ id: String(id), name })) }])
  assert.deepEqual(patch.insert.map(row => row.name), names.slice(0, 3))
})
