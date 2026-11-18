// Reclaim idle plugin containers while preserving their durable session storage.
export class RuntimeIdleReaper {
  #entries = new Set()
  #timer

  constructor({ idleMs, onIdle, readIdleMs, intervalMs = 60_000 }) {
    this.setIdleMs(idleMs)
    this.readIdleMs = readIdleMs
    this.onIdle = onIdle
    this.#timer = setInterval(() => { this.sweep().catch(() => {}) }, intervalMs)
    this.#timer.unref?.()
  }

  setIdleMs(idleMs) {
    if (!Number.isFinite(idleMs) || idleMs < 0) throw new TypeError('idleMs must be nonnegative')
    this.idleMs = idleMs
  }

  async refreshPolicy() {
    if (this.readIdleMs) {
      try { this.setIdleMs(await this.readIdleMs()) }
      catch { /* retain the last confirmed policy */ }
    }
  }

  add(entry) {
    entry.lastUsedAt = Date.now()
    entry.inFlight = 0
    entry.retiring = false
    this.#entries.add(entry)
  }

  touch(entry) { entry.lastUsedAt = Date.now() }

  async use(entry, action) {
    if (entry.retiring) throw new Error('Plugin Runtime is retiring; retry the request')
    entry.inFlight += 1
    this.touch(entry)
    try { return await action() }
    finally {
      entry.inFlight -= 1
      this.touch(entry)
    }
  }

  delete(entry) { this.#entries.delete(entry) }

  async sweep(now = Date.now()) {
    await this.refreshPolicy()
    if (this.idleMs === 0) return
    const idle = [...this.#entries].filter(entry =>
      !entry.retiring && entry.inFlight === 0 && now - entry.lastUsedAt >= this.idleMs)
    for (const entry of idle) {
      if (entry.retiring || entry.inFlight || now - entry.lastUsedAt < this.idleMs || this.idleMs === 0) continue
      entry.retiring = true
      try { await this.onIdle(entry) }
      catch { entry.retiring = false; this.touch(entry) }
    }
  }

  async reclaimOne(now = Date.now(), minimumIdleMs = 60_000) {
    await this.refreshPolicy()
    if (this.idleMs === 0) return false
    const entry = [...this.#entries].filter(item => !item.retiring && item.inFlight === 0 &&
      now - item.lastUsedAt >= minimumIdleMs).sort((a, b) => a.lastUsedAt - b.lastUsedAt)[0]
    if (!entry) return false
    entry.retiring = true
    try { await this.onIdle(entry); return true }
    catch { entry.retiring = false; this.touch(entry); return false }
  }

  stop() { clearInterval(this.#timer) }
}
