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
import { pluginClientShellPatches } from './plugin-client-shell.mjs'
import { resolvePresetModules } from './preset-module-resolution.mjs'
import { readPluginInventory } from './inventory-compat.mjs'
import { prepareManagedProfile } from './managed-profile.mjs'
import { reconcileProfilePlugins } from './plugin-reconciler.mjs'
import { recoverWindowsStaleModuleLock } from './windows-stale-module-lock.mjs'
import { recoverWindowsEmptyModuleFallbacks } from './windows-empty-module-fallbacks.mjs'

const MODULE_DIR = dirname(fileURLToPath(import.meta.url))
const RUNTIME_HOST_ROOT = resolve(MODULE_DIR, '..', '..')
const ROOT_CONFIG = resolve(RUNTIME_HOST_ROOT, 'config', 'official-host-root.yml')
const ASKAI_PRESET_ROOT = resolve(RUNTIME_HOST_ROOT, 'config', 'agent-presets')

export class OfficialDshHostComposition {
  #ctx
  #inventory

  constructor({ storageRoot, durableStorageRoot, webSearchProvider, plugins = [], pluginModelName }) {
    this.storageRoot = resolve(storageRoot)
    this.durableStorageRoot = durableStorageRoot
    this.webSearchProvider = webSearchProvider
    this.plugins = plugins
    this.pluginModelName = pluginModelName
  }

  async start() {
    if (this.#ctx !== undefined) throw new Error('official DSH Host composition is already started')
    await this.#boot()
    try {
      const unavailable = new Map()
      if (await reconcileProfilePlugins(this.#ctx.get('pluginManager'), this.plugins, {
        onUnavailable: (plugin, error) => unavailable.set(plugin.name, { name: plugin.name, reason: error.code }),
      })) {
        await this.dispose()
        await this.#boot()
      }
      this.unavailablePlugins = [...unavailable.values()]
      this.availablePlugins = this.plugins.filter(plugin => !unavailable.has(plugin.name))
      const active = new Map((await this.#ctx.get('pluginManager').listBundles())
        .map(item => [item.name, item]))
      for (const plugin of this.availablePlugins) {
        const item = active.get(plugin.name)
        if (!item?.enabled || item.version !== plugin.version || item.error) {
          throw new Error(`DSH plugin ${plugin.name} did not activate in this Runtime Profile`)
        }
        for (const row of item.rows ?? []) {
          const entry = this.#inventory.entries.find(candidate => candidate.entryId === row.entryId)
          if (!entry || (entry.enabled && entry.fiberPhase !== 'active')) {
            const reason = entry?.error?.message ?? entry?.error?.code ?? entry?.problem ?? entry?.fiberPhase ?? 'missing'
            throw new Error(`DSH plugin ${plugin.name} row ${row.rowId} did not become active (${reason})`)
          }
        }
      }
      return this.#ctx
    } catch (error) {
      await this.dispose()
      throw error
    }
  }

  async #boot() {
    const installation = await resolveDshInstallation()
    const appBoot = await loadAssociatedAppBoot(installation)
    const moduleHome = resolve(this.storageRoot, 'host-profile-home')
    await mkdir(moduleHome, { recursive: true })
    await recoverWindowsStaleModuleLock(moduleHome)
    await recoverWindowsEmptyModuleFallbacks(moduleHome)
    await healModuleFallback(appBoot, installation, moduleHome)
    const initialProfile = await prepareManagedProfile({
      appBoot, installation, moduleHome, overlays: [],
    })
    const basePatches = initialProfile.basePatches
    const webAppPatches = installation.webAppPatchPaths.flatMap(path => appBoot.loadOverlayPatches(
      'askai-dsh-official-preset-isolation', path,
    ))
    const presetIsolation = extractOfficialPresetIsolation(webAppPatches)
    const askaiOverlay = buildAskaiHostOverlay({
      storageRoot: this.storageRoot,
      durableStorageRoot: this.durableStorageRoot,
      askaiPresetRoot: ASKAI_PRESET_ROOT,
      shippedPresetRoot: installation.shippedPresetRoot,
      declarativePresets: presetIsolation.declarative,
      webSearchProvider: this.webSearchProvider,
      pluginWeb: this.plugins.length > 0,
      pluginModelName: this.pluginModelName,
      occupiedIds: collectInsertedEntryIds(basePatches),
      hostFeatures: {
        subagentModelSelection: installation.canResolveDependency(
          '@deepseek-ai/dsh-tool-subagent/model-selection-settings',
        ),
      },
    })
    const clientPatches = this.plugins.length === 0 ? [] : pluginClientShellPatches(webAppPatches)
    const overlays = [...resolvePresetModules([...presetIsolation.patches, ...clientPatches, ...askaiOverlay], installation)]
    const managedProfile = await prepareManagedProfile({
      appBoot, installation, moduleHome, overlays,
    })
    await writeFile(managedProfile.root, await readFile(ROOT_CONFIG, 'utf8'))
    this.#ctx = await appBoot.boot(
      'askai-dsh-host',
      managedProfile.root,
      managedProfile.patches,
      async ctx => {
        ctx.provide('profileContext', managedProfile.context)
        await ctx.plugin(appBoot.PluginPackages, { resolution: managedProfile.resolution })
      },
      undefined,
    )
    this.installation = installation
    this.presetIsolation = presetIsolation
    const gateway = this.#ctx.get('pluginInventory')
    if (gateway === undefined) throw new Error('official DSH plugin inventory is unavailable')
    this.#inventory = await readPluginInventory(gateway)
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
    return
  }
  // DSH 0.1.2 moved module fallback healing to an asynchronous options
  // contract. Retain the positional call only for the approved rollback train.
  if (heal.constructor?.name === 'AsyncFunction') {
    await heal({ installAnchor: installation.dshManifestPath, home: moduleHome })
    return
  }
  await heal(installation.dshManifestPath, moduleHome)
}
