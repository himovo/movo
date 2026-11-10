import test from 'node:test'
import assert from 'node:assert/strict'
import { mkdtemp, rm, writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'

import { packageManagerEnvironment } from '../src/official-host/pnpm-offline-config.mjs'

test('DSH package manager uses the imported pnpm store and switches to strict offline mode', async () => {
  const root = await mkdtemp(join(tmpdir(), 'movo-pnpm-offline-'))
  try {
    const before = packageManagerEnvironment({ MOVO_OFFLINE_PACKAGE_ROOT: root })
    assert.equal(before.pnpm_config_store_dir, join(root, 'pnpm'))
    assert.equal(before.pnpm_config_cache_dir, join(root, 'pnpm-cache'))
    assert.equal(before.pnpm_config_offline, 'false')
    await writeFile(join(root, 'offline-only'), '')
    const after = packageManagerEnvironment({ MOVO_OFFLINE_PACKAGE_ROOT: root })
    assert.equal(after.pnpm_config_offline, 'true')
  } finally {
    await rm(root, { recursive: true, force: true })
  }
})
