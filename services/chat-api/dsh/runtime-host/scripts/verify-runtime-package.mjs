import { createRequire } from 'node:module'
import { readFileSync, readdirSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const hostRoot = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const hostManifest = JSON.parse(readFileSync(resolve(hostRoot, 'package.json'), 'utf8'))
const fromHost = createRequire(resolve(hostRoot, 'package.json'))

function resolveDependencies(fromPackage, dependencies) {
  for (const name of Object.keys(dependencies ?? {})) {
    try {
      fromPackage.resolve(`${name}/package.json`)
    } catch (error) {
      if (error?.code !== 'ERR_PACKAGE_PATH_NOT_EXPORTED') throw error
      fromPackage.resolve(name)
    }
  }
}

resolveDependencies(fromHost, hostManifest.dependencies)
const dshManifestPath = fromHost.resolve('@deepseek-ai/dsh/package.json')
const dshManifest = JSON.parse(readFileSync(dshManifestPath, 'utf8'))
if (dshManifest.version !== hostManifest.dependencies['@deepseek-ai/dsh']) {
  throw new Error(`DSH version mismatch: expected ${hostManifest.dependencies['@deepseek-ai/dsh']}, found ${dshManifest.version}`)
}

const fromDsh = createRequire(dshManifestPath)
resolveDependencies(fromDsh, dshManifest.dependencies)
const officeManifestPath = fromDsh.resolve('@deepseek-ai/dsh-skill-office/package.json')
const skillFiles = readdirSync(resolve(dirname(officeManifestPath), 'assets'), {
  recursive: true,
  withFileTypes: true,
}).filter(entry => entry.isFile() && entry.name === 'SKILL.md')
if (skillFiles.length === 0) throw new Error('DSH Office Skill resources are missing')

console.log(`Verified DSH ${dshManifest.version}: ${Object.keys(dshManifest.dependencies ?? {}).length} runtime dependencies and ${skillFiles.length} Office Skills`)
