import { createHash } from 'node:crypto'
import { mkdir, mkdtemp, rename, rm, stat, writeFile } from 'node:fs/promises'
import { dirname, join, normalize, resolve, sep } from 'node:path'
import { unzipSync } from 'fflate'

const MAX_FILES = 256
const MAX_EXPANDED_BYTES = 20 * 1024 * 1024

function safeRelativePath(value) {
  const raw = String(value ?? '').replaceAll('\\', '/')
  const normalized = normalize(raw)
  if (!raw || raw.startsWith('/') || normalized === '..' || normalized.startsWith(`..${sep}`)) {
    throw new Error(`unsafe Skill bundle path: ${raw}`)
  }
  return normalized
}

async function exists(path) {
  try {
    return (await stat(path)).isDirectory()
  } catch (error) {
    if (error?.code === 'ENOENT') return false
    throw error
  }
}

export class SkillBundleMaterializer {
  constructor(storageRoot) {
    this.root = resolve(storageRoot, 'imported-skills')
  }

  async materialize(skill) {
    const encoded = String(skill?.bundle_archive_base64 ?? '')
    if (!encoded) return undefined
    const digest = String(skill?.bundle_digest ?? '')
    const archive = Buffer.from(encoded, 'base64')
    if (!/^[0-9a-f]{64}$/.test(digest) || createHash('sha256').update(archive).digest('hex') !== digest) {
      throw new Error(`Skill bundle digest mismatch: ${skill?.name ?? 'unknown'}`)
    }
    const destination = resolve(this.root, digest)
    const rootPrefix = safeRelativePath(String(skill?.bundle_root || '.'))
    const resourceRoot = resolve(destination, rootPrefix)
    if (await exists(destination)) return resourceRoot

    const entries = Object.entries(unzipSync(new Uint8Array(archive)))
    if (entries.length > MAX_FILES) throw new Error('Skill bundle contains too many files')
    let total = 0
    await mkdir(this.root, { recursive: true })
    const temporary = await mkdtemp(join(this.root, '.install-'))
    try {
      for (const [entryName, bytes] of entries) {
        if (entryName.endsWith('/')) continue
        const relative = safeRelativePath(entryName)
        total += bytes.byteLength
        if (total > MAX_EXPANDED_BYTES) throw new Error('Skill bundle expands beyond the runtime limit')
        const target = resolve(temporary, relative)
        if (target !== temporary && !target.startsWith(`${temporary}${sep}`)) {
          throw new Error(`Skill bundle path escapes materialization root: ${entryName}`)
        }
        await mkdir(dirname(target), { recursive: true })
        await writeFile(target, bytes, { mode: 0o600 })
      }
      try {
        await rename(temporary, destination)
      } catch (error) {
        if (error?.code !== 'EEXIST' && error?.code !== 'ENOTEMPTY') throw error
      }
    } finally {
      await rm(temporary, { recursive: true, force: true })
    }
    return resourceRoot
  }
}
