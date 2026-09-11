import assert from 'node:assert/strict'
import { createHash } from 'node:crypto'
import { mkdtemp, readFile, rm } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import test from 'node:test'
import { zipSync, strToU8 } from 'fflate'

import { SkillBundleMaterializer } from '../src/skill-bundle-materializer.mjs'

test('materializes an immutable nested Skill bundle for DSH directory resources', async () => {
  const root = await mkdtemp(join(tmpdir(), 'movo-skill-bundle-'))
  const archive = Buffer.from(zipSync({
    'sample/SKILL.md': strToU8('---\nname: sample\ndescription: Sample\n---\nBody'),
    'sample/references/a.txt': strToU8('resource'),
  }))
  const digest = createHash('sha256').update(archive).digest('hex')
  try {
    const path = await new SkillBundleMaterializer(root).materialize({
      name: 'sample', bundle_digest: digest, bundle_root: 'sample/',
      bundle_archive_base64: archive.toString('base64'),
    })
    assert.equal(await readFile(join(path, 'references/a.txt'), 'utf8'), 'resource')
  } finally {
    await rm(root, { recursive: true, force: true })
  }
})

test('rejects a bundle whose immutable digest does not match', async () => {
  const root = await mkdtemp(join(tmpdir(), 'movo-skill-bundle-'))
  try {
    await assert.rejects(
      new SkillBundleMaterializer(root).materialize({
        name: 'sample', bundle_digest: '0'.repeat(64), bundle_archive_base64: Buffer.from('bad').toString('base64'),
      }),
      /digest mismatch/,
    )
  } finally {
    await rm(root, { recursive: true, force: true })
  }
})
