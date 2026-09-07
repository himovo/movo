import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { inheritedDraftProjectContext } from '../src/composables/code/draftProjectContext'

const workspace = {
  workspace_id: 'movo',
  title: 'movo',
  path: '/workspace/movo',
  status: 'ok',
  session_ids: [],
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-02T00:00:00Z',
  git_branch: 'main',
} as const

assert.equal(inheritedDraftProjectContext({
  workspace: null,
  worktree: false,
  sourceRef: '',
}), null, 'an ordinary conversation must create another ordinary conversation')

assert.deepEqual(inheritedDraftProjectContext({
  workspace,
  worktree: true,
  sourceRef: 'refs/heads/release',
}), {
  workspace,
  worktree: true,
  sourceRef: 'refs/heads/release',
}, 'a project conversation must inherit only its draft project configuration')

assert.equal(inheritedDraftProjectContext({
  workspace,
  worktree: false,
  sourceRef: '',
})?.sourceRef, 'refs/heads/main', 'the current project branch is the safe fallback')

const appShell = readFileSync('src/App.vue', 'utf8')
const runtime = readFileSync('src/composables/code/useDshCodeRuntime.ts', 'utf8')
const picker = readFileSync('src/components/code/WorkspaceContextPicker.vue', 'utf8')

assert.doesNotMatch(runtime, /recommendRecent|function recommend\(/, 'recent projects must never be selected implicitly')
assert.match(appShell, /icon === 'plus'\) startLocalSession\(\{ inheritCurrentProject: true \}\)/)
assert.match(appShell, /@click="\(\) => startLocalSession\(\{ inheritCurrentProject: true \}\)"/)
assert.match(appShell, /startLocalSession\(\{ shouldNavigate: currentView\.value === 'chat' \}\)/)
assert.match(picker, /'切换项目…'/)
assert.match(picker, /'设为普通对话'/)
assert.doesNotMatch(picker, /'移除项目'/)

console.log('new-session project context tests passed')
