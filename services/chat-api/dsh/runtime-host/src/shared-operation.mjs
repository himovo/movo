/** Share one in-flight initialization per identity, then allow later retries. */
export class SharedOperation {
  #pending = new Map()

  run(key, operation) {
    const existing = this.#pending.get(key)
    if (existing) return existing
    const pending = Promise.resolve().then(operation).finally(() => {
      if (this.#pending.get(key) === pending) this.#pending.delete(key)
    })
    this.#pending.set(key, pending)
    return pending
  }

  async drain() {
    await Promise.allSettled([...this.#pending.values()])
  }
}
