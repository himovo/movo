// The DSH manager owns package installation, compatibility checks, profile
// locking and rollback. The MOVO Host only exposes its operations to its
// authenticated control plane; it never runs pnpm or imports user specs here.
import { createRequire } from 'node:module'
import { readFile } from 'node:fs/promises'
import { join } from 'node:path'

export class ManagedPluginBridge {
  constructor(ctx) {
    const manager = ctx.get('pluginManager')
    if (manager === undefined) throw new Error('managed DSH plugin profile is unavailable')
    this.manager = manager
  }

  async list() {
    return { bundles: await this.manager.listBundles() }
  }

  async manifest(name) {
    const inventory = await this.manager.listBundles()
    if (!inventory.some(item => item.name === name && item.installed)) throw new Error('plugin_not_installed')
    for (const anchor of [this.manager.profile.installAnchor, join(this.manager.profile.dir, 'package.json')]) {
      for (const path of createRequire(anchor).resolve.paths(name) ?? []) {
        try {
          const manifest = JSON.parse(await readFile(join(path, name, 'package.json'), 'utf8'))
          if (manifest.name === name) return {
            name: manifest.name,
            version: manifest.version,
            engines: { dsh: manifest.engines?.dsh },
            compatibility: manifest.dsh?.compatibility,
          }
        } catch (error) {
          if (error?.code !== 'ENOENT') throw error
        }
      }
    }
    throw new Error('plugin_manifest_not_found')
  }

  async inspect(spec, registry) {
    return await this.manager.inspect(spec, registry ? { registry } : undefined)
  }

  async install(spec, { registry, requestId } = {}) {
    return await this.manager.installBundle(spec, {
      enabled: false,
      ...(registry ? { registry } : {}),
      ...(requestId ? { requestId } : {}),
    })
  }

  async enable(name, enabled) {
    return await this.manager.setBundleEnabled(name, enabled)
  }

  async remove(name) {
    return await this.manager.removeBundle(name)
  }
}
