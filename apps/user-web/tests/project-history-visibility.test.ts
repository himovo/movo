import assert from 'node:assert/strict'
import { projectHistoryVisibility } from '../src/composables/code/projectHistoryVisibility'

const makeSession = (id: string, workspaceId?: string) => ({
  id, user_id: 'employee', title: id, created_at: '1', updated_at: '2', message_count: 1,
  ...(workspaceId ? { code_project: { workspace_id: workspaceId, git_branch: 'main', worktree: false } } : {}),
})
const workspaces = [
  { workspace_id: 'here', title: 'Local project', path: '/here', status: 'ok', session_ids: [], created_at: '1', updated_at: '2' },
  { workspace_id: 'away', title: 'Other computer', path: '', status: 'missing-dir', session_ids: [], created_at: '1', updated_at: '2' },
] as const

const result = projectHistoryVisibility(
  [makeSession('normal'), makeSession('local-history', 'here'), makeSession('remote-history', 'away'), makeSession('unknown-project', 'not-on-this-device')],
  workspaces, {},
)
assert.deepEqual(result.projects.map(group => group.workspaceId), ['here'])
assert.deepEqual(result.projects[0].items.map(item => item.id), ['local-history'])
assert.deepEqual(result.ordinary.map(item => item.id).sort(), ['normal', 'remote-history', 'unknown-project'])
assert.equal(result.unavailableIds.has('remote-history'), true)
assert.equal(result.unavailableIds.has('unknown-project'), true)
assert.equal(result.unavailableIds.has('normal'), false)
