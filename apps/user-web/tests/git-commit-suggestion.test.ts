import assert from 'node:assert/strict'
import test from 'node:test'
import { suggestCommitMessage } from '../src/components/code/commitMessageSuggestion'
import type { DshWorkspaceSummary } from '../src/platform/types'

function summary(changes: DshWorkspaceSummary['changes']): DshWorkspaceSummary {
  return {
    generated_at: Date.now(), branch: 'feature/test', git_available: true, changes,
    head_commit: 'abc123', upstream: '', ahead: null, behind: null, remote_names: [],
  }
}

test('generates an editable message for one modified file', () => {
  const value = suggestCommitMessage(summary([
    { path: 'src/runtime.ts', status: ' M', additions: 3, deletions: 1, binary: false },
  ]), 'zh')
  assert.equal(value, '更新 runtime.ts')
})

test('summarizes a multi-file change without inventing implementation semantics', () => {
  const value = suggestCommitMessage(summary([
    { path: 'src/runtime.ts', status: ' M', additions: 3, deletions: 1, binary: false },
    { path: 'tests/runtime.test.ts', status: '??', additions: null, deletions: null, binary: false },
  ]), 'en')
  assert.equal(value, 'Update runtime.ts and 1 related files')
})
