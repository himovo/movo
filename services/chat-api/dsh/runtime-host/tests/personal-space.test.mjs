import test from 'node:test'
import assert from 'node:assert/strict'

import { personalSpaceKey, validConversationSpaceKey } from '../src/personal-space.mjs'
import { normalizeTurnContext } from '../src/runtime-turn-context.mjs'

test('personal keys isolate users and conversations without exposing identity', () => {
  const first = personalSpaceKey('tenant-a', 'user-a')
  assert.match(first, /^[0-9a-f]{64}$/)
  assert.equal(first, personalSpaceKey('tenant-a', 'user-a'))
  assert.notEqual(first, personalSpaceKey('tenant-a', 'user-b'))
  assert.notEqual(first, personalSpaceKey('tenant-b', 'user-a'))
  assert.equal(validConversationSpaceKey(first), true)
  assert.equal(validConversationSpaceKey('../other'), false)
})

test('only staged workspace paths are shown to plugin tools', () => {
  const localPath = `/job/home/conversations/${'a'.repeat(64)}/inputs/${'b'.repeat(32)}/0-report.docx`
  const context = normalizeTurnContext({ documents: [{
    object_path: 'alice/report.docx', filename: 'report.docx', local_path: localPath,
  }] })
  assert.equal(context.documents[0].local_path, localPath)
  const invalid = normalizeTurnContext({ documents: [{
    object_path: 'alice/report.docx', local_path: '/etc/passwd',
  }] })
  assert.equal(invalid.documents[0].local_path, undefined)
})
