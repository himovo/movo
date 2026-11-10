import { createRequire } from 'node:module'
import { dirname, join } from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'
import { readFile, readdir } from 'node:fs/promises'

const requireFromHost = createRequire(import.meta.url)

async function readManifest(path) {
  return JSON.parse(await readFile(path, 'utf8'))
}

export function assertLockedDshVersion(actualVersion, hostManifest) {
  const expectedVersion = hostManifest.dependencies?.['@deepseek-ai/dsh']
  if (typeof expectedVersion !== 'string' || !expectedVersion || expectedVersion !== actualVersion) {
    throw new Error(`Installed DSH ${actualVersion} does not match the MOVO Runtime lock ${expectedVersion ?? 'missing'}`)
  }
}

async function resolveShippedPresetRoot(candidates) {
  for (const candidate of candidates) {
    try {
      if ((await readdir(candidate)).length > 0) return candidate
    } catch (error) {
      if (error?.code !== 'ENOENT' && error?.code !== 'ENOTDIR') throw error
    }
  }
  throw new Error('the installed DSH release does not expose a shipped agent preset root')
}

export async function resolveDshInstallation() {
  const dshManifestPath = requireFromHost.resolve('@deepseek-ai/dsh/package.json')
  const dshPackageDir = dirname(dshManifestPath)
  const requireFromDsh = createRequire(dshManifestPath)
  const baseManifestPath = requireFromDsh.resolve('@deepseek-ai/dsh-base/package.json')
  const baseManifest = await readManifest(baseManifestPath)
  const basePatch = baseManifest?.dsh?.bundle?.patch
  if (typeof basePatch !== 'string' || !basePatch) {
    throw new Error('@deepseek-ai/dsh-base does not declare dsh.bundle.patch')
  }
  const webAppManifestPath = requireFromDsh.resolve('@deepseek-ai/dsh-web-app/package.json')
  const webAppManifest = await readManifest(webAppManifestPath)
  const declaredWebPatches = webAppManifest?.dsh?.bundle?.patch
  const webAppPatches = (Array.isArray(declaredWebPatches) ? declaredWebPatches : [declaredWebPatches])
    .filter(patch => typeof patch === 'string' && patch.length > 0)
  if (webAppPatches.length === 0) {
    throw new Error('@deepseek-ai/dsh-web-app does not declare dsh.bundle.patch')
  }
  const dshManifest = await readManifest(dshManifestPath)
  const hostManifest = await readManifest(join(dirname(dirname(dirname(fileURLToPath(import.meta.url)))), 'package.json'))
  assertLockedDshVersion(dshManifest.version, hostManifest)
  let shippedPresetRoot
  if (webAppPatches.length === 1) {
    const presetManifestPath = requireFromDsh.resolve('@deepseek-ai/dsh-agent-presets/package.json')
    shippedPresetRoot = await resolveShippedPresetRoot([
      join(dirname(presetManifestPath), 'presets'),
      join(dshPackageDir, 'config', 'agent-presets'),
    ])
  }
  return Object.freeze({
    version: String(dshManifest.version),
    dshManifestPath,
    dshPackageDir,
    moduleBaseUrl: pathToFileURL(dshManifestPath).href,
    basePatchPath: join(dirname(baseManifestPath), basePatch),
    webAppPatchPaths: webAppPatches.map(patch => join(dirname(webAppManifestPath), patch)),
    shippedPresetRoot,
    resolveDependency(specifier) {
      return requireFromDsh.resolve(specifier)
    },
    canResolveDependency(specifier) {
      try {
        requireFromDsh.resolve(specifier)
        return true
      } catch (error) {
        if (
          error?.code === 'ERR_PACKAGE_PATH_NOT_EXPORTED'
          || error?.code === 'MODULE_NOT_FOUND'
        ) return false
        throw error
      }
    },
  })
}

export async function loadAssociatedAppBoot(installation) {
  const entry = installation.resolveDependency('@deepseek-ai/dsh-app-boot')
  return import(pathToFileURL(entry).href)
}
