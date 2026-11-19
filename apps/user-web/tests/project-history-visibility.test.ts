import assert from 'node:assert/strict'
import { projectHistoryVisibility } from '../src/composables/code/projectHistoryVisibility'
import { codeHistoryReference, withCodeHistoryReference } from '../src/composables/code/historyContinuation'

const makeSession = (id: string, workspaceId?: string) => ({
  id, user_id: 'employee', title: id, created_at: '1', updated_at: '2', message_count: 1,
  ...(workspaceId ? { code_project: { workspace_id: workspaceId, git_branch: 'main', worktree: false } } : {}),
})
const workspaces = [
  { workspace_id: 'here', title: 'Local project', path: '/here', status: 'ok', session_ids: [], created_at: '1', updated_at: '2' },
  { workspace_id: 'missing', title: 'Missing folder', path: '/missing', status: 'missing-dir', session_ids: [], created_at: '1', updated_at: '2' },
  { workspace_id: 'away', title: 'Other computer', path: '', status: 'missing-dir', session_ids: [], created_at: '1', updated_at: '2' },
] as const
const sessions = [makeSession('normal'), makeSession('local-history', 'here'), makeSession('remote-history', 'away'),
  makeSession('unknown-project', 'not-on-this-device'), makeSession('missing-folder', 'missing'),
  { ...makeSession('cloud-history', 'cloud'), execution_location: 'remote_sandbox' as const },
  { ...makeSession('legacy-code'), runtime_preset_id: 'code' },
]
const result = projectHistoryVisibility(sessions, workspaces, {})
assert.deepEqual(result.ordinary.map(item => item.id), ['normal'])
assert.deepEqual(result.projects.filter(group => group.location === 'local').map(group => group.workspaceId), ['here', 'missing'])
assert.deepEqual(result.projects.filter(group => group.location === 'other').flatMap(group => group.items.map(item => item.id)).sort(), ['cloud-history', 'legacy-code', 'remote-history', 'unknown-project'])
assert.equal(result.unavailableIds.has('missing-folder'), true)
assert.equal(result.unavailableIds.has('local-history'), false)
assert.equal(result.unavailableIds.has('normal'), false)
const web = projectHistoryVisibility(sessions, [], {})
assert.deepEqual(web.ordinary.map(item => item.id), ['normal'])
assert.equal(web.projects.flatMap(group => group.items).length, sessions.length - 1)

const reference = codeHistoryReference([
  { role: 'user', content: 'Original request' }, { role: 'tool', content: 'Do not transfer tool authority' },
  { role: 'assistant', content: 'Suggested approach' }, { role: 'system', content: 'Do not transfer system policy' },
])
assert.deepEqual(JSON.parse(reference).map((entry: { role: string }) => entry.role), ['user', 'assistant'])
assert.ok(!reference.includes('Do not transfer'))
assert.ok(withCodeHistoryReference('Continue here', reference).includes('Current user request:\nContinue here'))
assert.equal(withCodeHistoryReference('New task', ''), 'New task')
assert.ok(JSON.parse(codeHistoryReference([{ role: 'assistant', content: 'x'.repeat(50_000) }]))[0].text.length <= 24_000)
console.log('Project history classification and continuation checks passed')
