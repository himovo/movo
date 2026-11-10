import assert from 'node:assert/strict'
import { mkdtemp, mkdir, writeFile, rm } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import test from 'node:test'

import { ManagedPluginBridge } from '../src/managed-plugin-bridge.mjs'

test('reads compatibility metadata from the package installed in the DSH profile', async () => {
  const dir = await mkdtemp(join(tmpdir(), 'movo-plugin-manifest-'))
  try {
    const packageDir = join(dir, 'node_modules', 'example-plugin')
    await mkdir(packageDir, { recursive: true })
    await writeFile(join(dir, 'package.json'), '{}')
    await writeFile(join(packageDir, 'package.json'), JSON.stringify({
      name: 'example-plugin', version: '1.0.0',
      dsh: { compatibility: { dshReleases: { '0.2.1-rc.2+': 'compatible' } } },
    }))
    const manager = {
      profile: { dir, installAnchor: join(dir, 'package.json') },
      listBundles: async () => [{ name: 'example-plugin', installed: true }],
    }
    const bridge = new ManagedPluginBridge({ get: () => manager })
    assert.deepEqual((await bridge.manifest('example-plugin')).compatibility, {
      dshReleases: { '0.2.1-rc.2+': 'compatible' },
    })
    await assert.rejects(bridge.manifest('other-plugin'), /plugin_not_installed/)
  } finally {
    await rm(dir, { recursive: true, force: true })
  }
})
