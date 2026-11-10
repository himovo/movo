import { createHash, randomUUID } from 'node:crypto'
import { createReadStream } from 'node:fs'
import { cp, lstat, mkdir, readdir, rename, rm } from 'node:fs/promises'
import { join, resolve } from 'node:path'

const PROFILE = /^rp-[a-f0-9]{24}$/
const SESSION = /^dsh-[a-f0-9-]{36}$/
const TENANT = /^[A-Za-z0-9._-]{1,128}$/

function profileRoot(storageRoot, tenantId, profileVersion) {
  const isolationKey = `tenant:${tenantId}:profile:${profileVersion}`
  const key = createHash('sha256').update(isolationKey).digest('hex')
  return resolve(storageRoot, key, '_no-cwd')
}

async function sessionJournalState(directory) {
  const names = (await readdir(directory)).filter(name => /^session(?:\.v\d+)?\.jsonl$/.test(name))
  const entries = await Promise.all(names.map(async name => {
    const hash = createHash('sha256')
    for await (const chunk of createReadStream(join(directory, name))) hash.update(chunk)
    return `${name}:${hash.digest('hex')}`
  }))
  return entries.sort().join('|')
}

export class PluginHistoryMaterializer {
  constructor(storageRoot) { this.storageRoot = resolve(storageRoot) }

  async hydrate({ tenantId, targetProfileVersion, sessions }, { beforeReplace } = {}) {
    if (!TENANT.test(tenantId) || !PROFILE.test(targetProfileVersion) ||
        !Array.isArray(sessions) || sessions.length > 100 ||
        sessions.some(item => !PROFILE.test(item?.profileVersion) || !SESSION.test(item?.sessionId))) {
      throw new TypeError('invalid plugin history request')
    }
    const destinationRoot = profileRoot(this.storageRoot, tenantId, targetProfileVersion)
    await mkdir(destinationRoot, { recursive: true })
    let copied = 0
    let refreshed = 0
    let unavailable = 0
    const availableSessionIds = []
    for (const { profileVersion, sessionId } of sessions) {
      if (profileVersion === targetProfileVersion) {
        const current = await lstat(join(destinationRoot, sessionId)).catch(error => {
          if (error.code === 'ENOENT') return undefined
          throw error
        })
        if (current?.isDirectory()) availableSessionIds.push(sessionId)
        else unavailable++
        continue
      }
      const source = join(profileRoot(this.storageRoot, tenantId, profileVersion), sessionId)
      const destination = join(destinationRoot, sessionId)
      const sourceInfo = await lstat(source).catch(error => {
        if (error.code === 'ENOENT') return undefined
        throw error
      })
      if (!sourceInfo?.isDirectory()) { unavailable++; continue }
      const existing = await lstat(destination).catch(error => {
        if (error.code === 'ENOENT') return undefined
        throw error
      })
      if (existing && await sessionJournalState(source) === await sessionJournalState(destination)) {
        availableSessionIds.push(sessionId)
        continue
      }
      const staging = `${destination}.migration-${randomUUID()}`
      try {
        await cp(source, staging, { recursive: true, force: false, errorOnExist: true, preserveTimestamps: true })
        if (existing) {
          if (beforeReplace) await beforeReplace(sessionId)
          await rm(destination, { recursive: true })
        }
        await rename(staging, destination)
        if (existing) refreshed++
        else copied++
        availableSessionIds.push(sessionId)
      } catch (error) {
        if (error.code !== 'EEXIST' && error.code !== 'ENOTEMPTY') throw error
        availableSessionIds.push(sessionId)
      } finally {
        await rm(staging, { recursive: true, force: true })
      }
    }
    return { copied, refreshed, unavailable, availableSessionIds }
  }
}
