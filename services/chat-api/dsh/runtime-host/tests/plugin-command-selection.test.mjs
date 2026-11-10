import assert from 'node:assert/strict'
import test from 'node:test'

import { requireCurrentCommand, resolvePluginCommand } from '../src/plugin-command-selection.mjs'

const selectedId = `dsh_plugin_command:${'a'.repeat(24)}:${Buffer.from('paper:import').toString('base64url')}`
const profile = {
  plugins: [{ installation_id: 'a'.repeat(24), commands: [{ name: 'paper:import', definitionId: 'paper-plugin/import' }] }],
}

test('command selection requires an authorized profile entry and exact DSH definition', () => {
  const selected = resolvePluginCommand(profile, selectedId, '/paper:import 1234')
  assert.equal(selected.command.name, 'paper:import')
  assert.equal(requireCurrentCommand({ list: () => [{ name: 'paper:import', definitionId: 'paper-plugin/import' }] }, {}, selected).name, 'paper:import')
  assert.throws(() => requireCurrentCommand({ list: () => [{ name: 'paper:import', definitionId: 'other-plugin/import' }] }, {}, selected), /not provided/)
  assert.throws(() => resolvePluginCommand(profile, selectedId, '/paper:import-other'), /unavailable/)
  assert.throws(() => resolvePluginCommand({ plugins: [] }, selectedId, '/paper:import'), /unavailable/)
})
