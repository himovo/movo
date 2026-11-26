import { randomUUID } from 'node:crypto'
import { rm } from 'node:fs/promises'
import { KernelRuntime } from './kernel-runtime.mjs'
import { normalizeModelProfile } from './model-profile.mjs'
import { SharedOperation } from './shared-operation.mjs'

export class RuntimeManager {
  #runtimes = new Map()
  #creation = new SharedOperation()
  #isolationOwners = new Map()

  constructor({ storageRoot }) {
    this.storageRoot = storageRoot
  }

  async probe() {
    const runtime = await this.create({
      isolationKey: `startup-probe-${randomUUID()}`,
      profileVersion: 'startup-probe',
    })
    await this.dispose(runtime.runtimeId)
  }

  async create(body, options = {}) {
    return this.#creation.run(body.isolationKey, () => this.#create(body, options))
  }

  async #create({ isolationKey, profileVersion, modelProfile }, options = {}) {
    if (this.#isolationOwners.has(isolationKey)) {
      throw new Error(`isolation key already has a runtime: ${isolationKey}`)
    }
    const runtimeId = randomUUID()
    const runtime = new KernelRuntime({
      runtimeId,
      isolationKey,
      profileVersion,
      storageRoot: this.storageRoot,
      modelProfile: normalizeModelProfile(modelProfile, profileVersion),
      invokeDeferredTool: options.invokeDeferredTool,
    })
    await runtime.start()
    this.#runtimes.set(runtimeId, runtime)
    this.#isolationOwners.set(isolationKey, runtimeId)
    return runtime
  }

  get(runtimeId) {
    const runtime = this.#runtimes.get(runtimeId)
    if (runtime === undefined) throw new Error(`runtime not found: ${runtimeId}`)
    return runtime
  }

  findByIsolation(isolationKey) {
    const runtimeId = this.#isolationOwners.get(isolationKey)
    return runtimeId === undefined ? undefined : this.#runtimes.get(runtimeId)
  }

  describe(runtime) {
    return {
      runtimeId: runtime.runtimeId,
      isolationKey: runtime.isolationKey,
      profileVersion: runtime.profileVersion,
      modelInstanceId: runtime.modelProfile?.modelInstanceId ?? runtime.modelInstanceId,
    }
  }

  async exportCompletedSeed(runtimeId, sessionId) {
    return await this.get(runtimeId).exportCompletedSeed(sessionId)
  }

  async dispose(runtimeId, { purge = false } = {}) {
    const runtime = this.get(runtimeId)
    if (purge && !runtime.isolationKey.startsWith('plugin-install-validation:')) {
      throw new Error('only plugin validation runtimes may be purged')
    }
    this.#runtimes.delete(runtimeId)
    this.#isolationOwners.delete(runtime.isolationKey)
    await runtime.dispose()
    if (purge) await rm(runtime.storageRoot, { recursive: true, force: true })
  }

  async disposeAll() {
    await this.#creation.drain()
    for (const runtimeId of [...this.#runtimes.keys()]) await this.dispose(runtimeId)
  }

  inventory() {
    return [...this.#runtimes.values()].map(runtime => this.describe(runtime))
  }
}
