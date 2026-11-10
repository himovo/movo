import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const PACKAGE_MANAGER = resolve(dirname(fileURLToPath(import.meta.url)), 'pnpm-package-manager.mjs')

// DSH's manager only mounts when the Host supplies a real, writable profile.
// Keep the profile beside this Runtime's durable sessions, never in the image.
export async function prepareManagedProfile({ appBoot, installation, moduleHome, overlays }) {
  const name = 'askai-host'
  const dir = join(moduleHome, 'profiles', name)
  appBoot.initProfile(dir, ['@deepseek-ai/dsh-base'])
  const profile = appBoot.loadProfile(
    'askai-dsh-host', name, installation.dshManifestPath, moduleHome,
  )
  const context = {
    name,
    dir,
    patchPath: profile.patchPath,
    installAnchor: installation.dshManifestPath,
    startedBundles: profile.layers.map(layer => layer.packageName),
    cwd: process.cwd(),
    home: moduleHome,
    overlays,
    packageManager: {
      command: process.execPath,
      args: [PACKAGE_MANAGER],
      ...(process.versions.electron ? { env: { ELECTRON_RUN_AS_NODE: '1' } } : {}),
    },
    telemetryDisabledEnv: process.env.DSH_TELEMETRY_DISABLED,
  }
  const resolution = await appBoot.createRuntimeResolution({
    installAnchor: installation.dshManifestPath,
    profile,
    home: moduleHome,
  })
  return {
    context,
    resolution,
    patches: appBoot.readProfilePatches('askai-dsh-host', context, profile),
    basePatches: profile.layers.find(layer => layer.packageName === '@deepseek-ai/dsh-base')?.patches ?? [],
    root: join(dir, 'cordis.yml'),
  }
}
