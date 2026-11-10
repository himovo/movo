import assert from 'node:assert/strict'
import { createHash } from 'node:crypto'
import { mkdtemp, mkdir, readFile, rm, writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import test from 'node:test'

import { PluginHistoryMaterializer } from '../src/plugin-history-materializer.mjs'

const tenantId = 'tenant-a'
const oldProfile = `rp-${'a'.repeat(24)}`
const newProfile = `rp-${'b'.repeat(24)}`
const sessionId = 'dsh-12345678-1234-1234-1234-123456789abc'

function profilePath(root, profile) {
  const hash = createHash('sha256').update(`tenant:${tenantId}:profile:${profile}`).digest('hex')
  return join(root, hash, '_no-cwd')
}

test('copies a persisted session once into the current user profile', async () => {
  const root = await mkdtemp(join(tmpdir(), 'plugin-history-'))
  try {
    const source = join(profilePath(root, oldProfile), sessionId)
    await mkdir(source, { recursive: true })
    await writeFile(join(source, 'session.v4.jsonl'), 'persisted-session')
    const materializer = new PluginHistoryMaterializer(root)
    const input = { tenantId, targetProfileVersion: newProfile,
      sessions: [{ profileVersion: oldProfile, sessionId }] }
    assert.deepEqual(await materializer.hydrate(input), { copied: 1, refreshed: 0, unavailable: 0, availableSessionIds: [sessionId] })
    assert.deepEqual(await materializer.hydrate(input), { copied: 0, refreshed: 0, unavailable: 0, availableSessionIds: [sessionId] })
    assert.equal(await readFile(join(profilePath(root, newProfile), sessionId, 'session.v4.jsonl'), 'utf8'), 'persisted-session')
    await writeFile(join(source, 'session.v4.jsonl'), 'updated-session')
    const disposed = []
    assert.deepEqual(await materializer.hydrate(input, { beforeReplace: id => disposed.push(id) }), {
      copied: 0, refreshed: 1, unavailable: 0, availableSessionIds: [sessionId],
    })
    assert.deepEqual(disposed, [sessionId])
    assert.equal(await readFile(join(profilePath(root, newProfile), sessionId, 'session.v4.jsonl'), 'utf8'), 'updated-session')
    await assert.rejects(materializer.hydrate({ ...input, sessions: [{ profileVersion: '../other', sessionId }] }), TypeError)
  } finally {
    await rm(root, { recursive: true, force: true })
  }
})
