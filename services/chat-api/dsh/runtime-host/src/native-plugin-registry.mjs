const ALLOWED_NATIVE_PLUGINS = new Set([
  '@deepseek-ai/cordis-plugin-timer',
])

export class NativePluginRegistry {
  #ctx
  #fibers = new Map()
  #composed

  constructor(ctx, { composed = () => false } = {}) {
    this.#ctx = ctx
    this.#composed = composed
  }

  async load(specifier) {
    if (!ALLOWED_NATIVE_PLUGINS.has(specifier)) {
      throw new Error(`native plugin is not admitted: ${specifier}`)
    }
    if (this.#fibers.has(specifier)) return { specifier, loaded: true, reused: true }
    if (this.#composed(specifier)) {
      this.#fibers.set(specifier, null)
      return { specifier, loaded: true, reused: true }
    }
    const module = await import(specifier)
    const plugin = module.default ?? module
    const fiber = await this.#ctx.plugin(plugin)
    this.#fibers.set(specifier, fiber)
    return { specifier, loaded: true, reused: false }
  }

  async probe(specifier) {
    if (!this.#fibers.has(specifier)) throw new Error(`native plugin is not loaded: ${specifier}`)
    if (specifier === '@deepseek-ai/cordis-plugin-timer') {
      const startedAt = Date.now()
      await this.#ctx.timeout(2)
      return { specifier, capability: 'timer.timeout', elapsedMs: Date.now() - startedAt }
    }
    throw new Error(`native plugin has no probe: ${specifier}`)
  }

  async unload(specifier) {
    if (!this.#fibers.has(specifier)) return { specifier, unloaded: false }
    const fiber = this.#fibers.get(specifier)
    this.#fibers.delete(specifier)
    await fiber?.dispose()
    return { specifier, unloaded: true }
  }

  list() {
    return [...this.#fibers.keys()].sort()
  }
}
