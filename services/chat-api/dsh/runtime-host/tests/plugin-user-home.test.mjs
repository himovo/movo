import assert from 'node:assert/strict'
import { mkdtemp, mkdir, readFile, rm, writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import test from 'node:test'

import { migrateLegacyHostStorage, migrateLegacyPluginHome, pluginUserHome } from '../src/plugin-user-home.mjs'
import { pluginChildEnvironment } from '../src/isolated-plugin-runtime.mjs'
import { buildAskaiHostOverlay } from '../src/official-host/overlay.mjs'

test('plugin home follows tenant and user across runtime profiles', () => {
  const root = '/runtime-storage'
  const first = pluginUserHome(root, {
    tenantId: 'tenant-a', modelProfile: { subjectUserId: 'user-a' }, isolationKey: 'profile-one',
  })
  const changedProfile = pluginUserHome(root, {
    tenantId: 'tenant-a', modelProfile: { subjectUserId: 'user-a' }, isolationKey: 'profile-two',
  })
  const otherUser = pluginUserHome(root, {
    tenantId: 'tenant-a', modelProfile: { subjectUserId: 'user-b' }, isolationKey: 'profile-three',
  })
  const otherTenant = pluginUserHome(root, {
    tenantId: 'tenant-b', modelProfile: { subjectUserId: 'user-a' }, isolationKey: 'profile-four',
  })
  assert.equal(first, changedProfile)
  assert.notEqual(first, otherUser)
  assert.notEqual(first, otherTenant)
  assert.notEqual(pluginUserHome(root, { tenantId: 'tenant-a', isolationKey: 'validation-one' }),
    pluginUserHome(root, { tenantId: 'tenant-a', isolationKey: 'validation-two' }))
})

test('legacy DSH plugin data is copied once into the durable user home', async () => {
  const root = await mkdtemp(join(tmpdir(), 'movo-plugin-home-'))
  const legacy = join(root, 'legacy')
  const home = join(root, 'personal', 'plugin-home')
  try {
    await mkdir(join(legacy, '.dsh', 'inspirations'), { recursive: true })
    await writeFile(join(legacy, '.dsh', 'inspirations', 'notes.json'), 'original')
    assert.equal(await migrateLegacyPluginHome(home, legacy), true)
    assert.equal(await readFile(join(home, '.dsh', 'inspirations', 'notes.json'), 'utf8'), 'original')
    await writeFile(join(home, '.dsh', 'inspirations', 'notes.json'), 'updated')
    assert.equal(await migrateLegacyPluginHome(home, legacy), false)
    assert.equal(await readFile(join(home, '.dsh', 'inspirations', 'notes.json'), 'utf8'), 'updated')
  } finally {
    await rm(root, { recursive: true, force: true })
  }
})

test('local plugin process receives only its assigned home', () => {
  const home = '/runtime-storage/personal/user/plugin-home'
  const env = pluginChildEnvironment('token', home)
  assert.equal(env.HOME, home)
  assert.equal(env.USERPROFILE, home)
  assert.equal(env.APPDATA, join(home, 'AppData', 'Roaming'))
  assert.equal(env.LOCALAPPDATA, join(home, 'AppData', 'Local'))
  assert.equal(env.DSH_HOME, undefined)
})

test('DSH native storage follows the user home across profiles', async () => {
  const root = await mkdtemp(join(tmpdir(), 'movo-plugin-storage-'))
  const home = join(root, 'personal', 'plugin-home')
  const firstProfile = join(root, 'profile-one')
  try {
    await mkdir(join(firstProfile, 'host-storage'), { recursive: true })
    await writeFile(join(firstProfile, 'host-storage', 'ideas.json'), 'saved')
    assert.equal(await migrateLegacyHostStorage(home, firstProfile), true)
    assert.equal(await readFile(join(home, 'host-storage', 'ideas.json'), 'utf8'), 'saved')
    const overlay = buildAskaiHostOverlay({
      storageRoot: join(root, 'profile-two'), durableStorageRoot: home,
      askaiPresetRoot: root,
    })
    const storage = overlay.flatMap(row => row.insert ?? []).find(row => row.id === 'storage-json')
    assert.equal(storage.config.root, join(home, 'host-storage'))
  } finally {
    await rm(root, { recursive: true, force: true })
  }
})
