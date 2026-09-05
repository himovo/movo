export function createStreamReadiness(): { ready: Promise<void>; settle: () => void } {
  let resolveReady!: () => void
  let settled = false
  const ready = new Promise<void>((resolve) => { resolveReady = resolve })
  return {
    ready,
    settle: () => {
      if (settled) return
      settled = true
      resolveReady()
    },
  }
}
