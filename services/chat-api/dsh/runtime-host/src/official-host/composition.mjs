import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { mkdir, readFile, writeFile } from 'node:fs/promises'

import { loadAssociatedAppBoot, resolveDshInstallation } from './installation.mjs'
import {
  ASKAI_DSH_HOST_OVERLAY_VERSION,
  buildAskaiHostOverlay,
} from './overlay.mjs'
import { collectInsertedEntryIds } from './overlay-planner.mjs'
import { extractOfficialPresetIsolation } from './preset-isolation.mjs'
import { readPluginInventory } from './inventory-compat.mjs'

const MODULE_DIR = dirname(fileURLToPath(import.meta.url))
const RUNTIME_HOST_ROOT = resolve(MODULE_DIR, '..', '..')
const ROOT_CONFIG = resolve(RUNTIME_HOST_ROOT, 'config', 'official-host-root.yml')
const ASKAI_PRESET_ROOT = resolve(RUNTIME_HOST_ROOT, 'config', 'agent-presets')

export class OfficialDshHostComposition {
  #ctx
  #inventory

  constructor({ storageRoot, webSearchProvider }) {
    this.storageRoot = resolve(storageRoot)
    this.webSearchProvider = webSearchProvider
  }

  async start() {
    if (this.#ctx !== undefined) throw new Error('official DSH Host composition is already started')
    const installation = await resolveDshInstallation()
    const appBoot = await loadAssociatedAppBoot(installation)
    const moduleHome = resolve(this.storageRoot, 'host-profile-home')
    const profileDir = resolve(moduleHome, 'profiles', 'askai-host')
    const profileRoot = resolve(profileDir, 'cordis.yml')
    await mkdir(profileDir, { recursive: true })
    await writeFile(profileRoot, await readFile(ROOT_CONFIG, 'utf8'))
    await healModuleFallback(appBoot, installation, moduleHome)
    const basePatches = appBoot.loadOverlayPatches('askai-dsh-host', installation.basePatchPath)
    const webAppPatches = appBoot.loadOverlayPatches(
      'askai-dsh-official-preset-isolation',
      installation.webAppPatchPath,
    )
    const presetIsolation = extractOfficialPresetIsolation(webAppPatches)
    const askaiOverlay = buildAskaiHostOverlay({
      storageRoot: this.storageRoot,
      askaiPresetRoot: ASKAI_PRESET_ROOT,
      shippedPresetRoot: installation.shippedPresetRoot,
      webSearchProvider: this.webSearchProvider,
      occupiedIds: collectInsertedEntryIds(basePatches),
      hostFeatures: {
        subagentModelSelection: installation.canResolveDependency(
          '@deepseek-ai/dsh-tool-subagent/model-selection-settings',
        ),
      },
    })
    this.#ctx = await appBoot.boot(
      'askai-dsh-host',
      profileRoot,
      [...basePatches, ...presetIsolation.patches, ...askaiOverlay],
      undefined,
      installation.moduleBaseUrl,
    )
    this.installation = installation
    this.presetIsolation = presetIsolation
    const gateway = this.#ctx.get('pluginInventory')
    if (gateway === undefined) throw new Error('official DSH plugin inventory is unavailable')
    this.#inventory = await readPluginInventory(gateway)
    return this.#ctx
  }

  get ctx() {
    if (this.#ctx === undefined) throw new Error('official DSH Host composition is not started')
    return this.#ctx
  }

  inventory() {
    if (this.#inventory === undefined) throw new Error('official DSH plugin inventory is unavailable')
    return {
      overlayVersion: ASKAI_DSH_HOST_OVERLAY_VERSION,
      dshVersion: this.installation.version,
      presetIsolationRows: this.presetIsolation.disabledIds,
      ...this.#inventory,
    }
  }

  async dispose() {
    const ctx = this.#ctx
    this.#ctx = undefined
    this.#inventory = undefined
    if (ctx !== undefined) await ctx.fiber.dispose()
  }
}

async function healModuleFallback(appBoot, installation, moduleHome) {
  const heal = appBoot.healProfilesModuleFallback
  if (typeof heal !== 'function') {
    throw new Error('official DSH app boot does not expose module fallback healing')
  }
  // DSH 0.1.2 moved module fallback healing to an asynchronous options
  // contract. Retain the positional call only for the approved rollback train.
  if (heal.constructor?.name === 'AsyncFunction') {
    await heal({ installAnchor: installation.dshManifestPath, home: moduleHome })
    return
  }
  await heal(installation.dshManifestPath, moduleHome)
}
