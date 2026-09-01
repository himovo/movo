import { mkdir } from 'node:fs/promises'
import { resolve } from 'node:path'

import { KernelRuntime } from '../src/kernel-runtime.mjs'

function options(argv) {
  const parsed = {}
  for (let index = 0; index < argv.length; index += 2) {
    const key = argv[index]
    const value = argv[index + 1]
    if (!key?.startsWith('--') || value === undefined) throw new Error(`invalid argument: ${key ?? ''}`)
    parsed[key.slice(2)] = value
  }
  for (const required of ['mode', 'storage-root', 'session-id', 'isolation-key']) {
    if (!parsed[required]) throw new Error(`--${required} is required`)
  }
  if (!['create', 'resume'].includes(parsed.mode)) throw new Error('--mode must be create or resume')
  return parsed
}

const args = options(process.argv.slice(2))
const storageRoot = resolve(args['storage-root'])
await mkdir(storageRoot, { recursive: true })
const runtime = new KernelRuntime({
  runtimeId: `upgrade-probe-${args.mode}`,
  isolationKey: args['isolation-key'],
  profileVersion: 'upgrade-probe-v1',
  storageRoot,
})

try {
  await runtime.start()
  const session = args.mode === 'create'
    ? await runtime.createSession({
        sessionId: args['session-id'],
        presetId: args['preset-id'] ?? 'code',
        cwd: storageRoot,
      })
    : await runtime.resumeSession(args['session-id'])
  process.stdout.write(`${JSON.stringify({ ok: true, mode: args.mode, session })}\n`)
} finally {
  await runtime.dispose()
}
