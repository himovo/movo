// Adapt native DSH dispatch to MOVO admission; never replace tool implementations.
import { AsyncLocalStorage } from 'node:async_hooks'
import { randomUUID } from 'node:crypto'

const executions = new AsyncLocalStorage()
export function currentExecutionPermit() { return executions.getStore()?.token ?? '' }

export function installIsolatedExecutionAdmission(ctx, { bridgeTools = [], request = fetch } = {}) {
  const base = process.env.MOVO_EXECUTION_ADMISSION_URL
  const credential = process.env.MOVO_EXECUTION_ADMISSION_TOKEN
  if (!base || !credential) return () => {}
  // These native protocol tools wait for humans or select resources; they do not
  // execute isolated workload. MOVO bridge handlers apply their own admission.
  const excluded = new Set([...bridgeTools, 'ask_user_question', 'skill', 'present'])
  const post = async (operation, body, signal) => {
    const response = await request(`${base}/${operation}`, {
      method: 'POST', headers: { authorization: `Bearer ${credential}`, 'content-type': 'application/json' },
      body: JSON.stringify(body), signal: signal ?? AbortSignal.timeout(25_000),
    })
    const value = await response.json()
    if (!response.ok) throw new Error(value.detail ?? value.error?.message ?? 'Isolation admission unavailable')
    return value
  }
  return ctx.on('tools/execute', async (exec, next) => {
    if (excluded.has(exec.name)) return next()
    const key = `${exec.agent?.id ?? 'host'}:${String(exec.callId)}:${randomUUID()}`
    let lease
    try { lease = await post('acquire', { key, parent: currentExecutionPermit() }, exec.signal) }
    catch (error) {
      await post('cancel', { key }).catch(() => {})
      throw error
    }
    const controller = new AbortController()
    const original = exec.signal
    exec.signal = original ? AbortSignal.any([original, controller.signal]) : controller.signal
    let beating = false
    const heartbeat = setInterval(async () => {
      if (beating) return
      beating = true
      try { await post('heartbeat', { token: lease.token }) }
      catch (error) { controller.abort(error) }
      finally { beating = false }
    }, 10_000)
    heartbeat.unref?.()
    const stopHeartbeat = () => clearInterval(heartbeat)
    exec.signal?.addEventListener('abort', stopHeartbeat, { once: true })
    try {
      return await executions.run({ token: lease.token }, next)
    } finally {
      clearInterval(heartbeat)
      exec.signal?.removeEventListener('abort', stopHeartbeat)
      exec.signal = original
      await post('release', { token: lease.token }).catch(() => {})
    }
  })
}
