import { createHash } from 'node:crypto'
import { cp, lstat, mkdir, rename, rm } from 'node:fs/promises'
import { join, resolve } from 'node:path'

import { personalSpaceKey } from './personal-space.mjs'

export function pluginUserHome(storageRoot, { tenantId, modelProfile, isolationKey }) {
  const personalKey = personalSpaceKey(tenantId, modelProfile?.subjectUserId)
  if (personalKey) return resolve(storageRoot, 'personal', personalKey, 'plugin-home')
  const runtimeKey = createHash('sha256').update(isolationKey).digest('hex')
  return resolve(storageRoot, 'plugin-validation-homes', runtimeKey)
}

async function migrateDirectory(source, destination) {
  if (resolve(source) === resolve(destination)) return false
  const sourceInfo = await lstat(source).catch(error => {
    if (error.code === 'ENOENT') return undefined
    throw error
  })
  if (!sourceInfo?.isDirectory()) return false
  await mkdir(resolve(destination, '..'), { recursive: true })
  const existing = await lstat(destination).catch(error => {
    if (error.code === 'ENOENT') return undefined
    throw error
  })
  if (existing) return false
  const staging = `${destination}.migration-${process.pid}`
  try {
    await cp(source, staging, { recursive: true, force: false, errorOnExist: true })
    await rename(staging, destination)
    return true
  } catch (error) {
    if (error.code === 'EEXIST') return false
    throw error
  } finally {
    await rm(staging, { recursive: true, force: true })
  }
}

export async function migrateLegacyPluginHome(home, legacyHome) {
  if (!legacyHome) return false
  return await migrateDirectory(join(legacyHome, '.dsh'), join(home, '.dsh'))
}

export async function migrateLegacyHostStorage(home, profileStorageRoot) {
  return await migrateDirectory(join(profileStorageRoot, 'host-storage'), join(home, 'host-storage'))
}
