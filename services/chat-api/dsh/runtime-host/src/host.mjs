import { readFile, rm } from 'node:fs/promises'
import { resolve } from 'node:path'

import { ASKAI_DSH_HOST_PROTOCOL_VERSION, ASKAI_DSH_KERNEL_VERSION, ASKAI_DSH_READY_EVENT } from './host-protocol.mjs'
import { RuntimeHttpServer } from './runtime-http-server.mjs'

function parseArgs(argv) {
  const values = { host: '127.0.0.1', port: 8101, storageRoot: './storage', authTokenFile: '' }
  for (let index = 0; index < argv.length; index += 2) {
    const name = argv[index]
    const value = argv[index + 1]
    if (value === undefined) throw new Error(`missing value for ${name}`)
    if (name === '--host') values.host = value
    else if (name === '--port') values.port = Number(value)
    else if (name === '--storage-root') values.storageRoot = value
    else if (name === '--auth-token-file') values.authTokenFile = value
    else throw new Error(`unknown argument: ${name}`)
  }
  return values
}

async function consumeTokenFile(path) {
  if (!path) return ''
  const token = (await readFile(path, 'utf8')).trim()
  await rm(path, { force: true })
  return token
}

async function main() {
  const options = parseArgs(process.argv.slice(2))
  const runtime = new RuntimeHttpServer({
    host: options.host,
    port: options.port,
    storageRoot: resolve(options.storageRoot),
    authToken: (await consumeTokenFile(options.authTokenFile)) || process.env.DSH_RUNTIME_HOST_TOKEN || '',
  })
  const address = await runtime.start()
  process.stdout.write(`${JSON.stringify({
    type: ASKAI_DSH_READY_EVENT,
    host: address.host,
    port: address.port,
    kernel: 'dsh',
    kernelVersion: ASKAI_DSH_KERNEL_VERSION,
    protocolVersion: ASKAI_DSH_HOST_PROTOCOL_VERSION,
    pid: process.pid,
  })}\n`)
  let stopping = false
  const shutdown = async () => {
    if (stopping) return
    stopping = true
    await runtime.stop()
  }
  process.once('SIGTERM', () => { void shutdown().then(() => process.exit(0)) })
  process.once('SIGINT', () => { void shutdown().then(() => process.exit(0)) })
}

main().catch(error => {
  process.stderr.write(`[askai-dsh-runtime] ${error instanceof Error ? error.message : String(error)}\n`)
  process.exitCode = 1
})
