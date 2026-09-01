import { createRequire } from 'node:module'
import { dirname, join } from 'node:path'
import { pathToFileURL } from 'node:url'
import { readFile, readdir } from 'node:fs/promises'

const requireFromHost = createRequire(import.meta.url)

async function readManifest(path) {
  return JSON.parse(await readFile(path, 'utf8'))
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
  const webAppPatch = webAppManifest?.dsh?.bundle?.patch
  if (typeof webAppPatch !== 'string' || !webAppPatch) {
    throw new Error('@deepseek-ai/dsh-web-app does not declare dsh.bundle.patch')
  }
  const dshManifest = await readManifest(dshManifestPath)
  const presetManifestPath = requireFromDsh.resolve('@deepseek-ai/dsh-agent-presets/package.json')
  const shippedPresetRoot = await resolveShippedPresetRoot([
    // 0.1.2 packages presets with the roster implementation.
    join(dirname(presetManifestPath), 'presets'),
    // The approved 0.1.1 rollback train packages them with the DSH launcher.
    join(dshPackageDir, 'config', 'agent-presets'),
  ])
  return Object.freeze({
    version: String(dshManifest.version),
    dshManifestPath,
    dshPackageDir,
    moduleBaseUrl: pathToFileURL(dshManifestPath).href,
    basePatchPath: join(dirname(baseManifestPath), basePatch),
    webAppPatchPath: join(dirname(webAppManifestPath), webAppPatch),
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
