import { randomUUID } from 'node:crypto'
import { KernelRuntime } from './kernel-runtime.mjs'
import { normalizeModelProfile } from './model-profile.mjs'

export class RuntimeManager {
  #runtimes = new Map()
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

  async create({ isolationKey, profileVersion, modelProfile }) {
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
      modelInstanceId: runtime.modelProfile?.modelInstanceId,
    }
  }

  async exportCompletedSeed(runtimeId, sessionId) {
    return await this.get(runtimeId).exportCompletedSeed(sessionId)
  }

  async dispose(runtimeId) {
    const runtime = this.get(runtimeId)
    this.#runtimes.delete(runtimeId)
    this.#isolationOwners.delete(runtime.isolationKey)
    await runtime.dispose()
  }

  async disposeAll() {
    for (const runtimeId of [...this.#runtimes.keys()]) await this.dispose(runtimeId)
  }

  inventory() {
    return [...this.#runtimes.values()].map(runtime => this.describe(runtime))
  }
}
