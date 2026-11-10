import { createRequire } from 'node:module'

const require = createRequire(import.meta.url)
const installedDshVersion = require('@deepseek-ai/dsh/package.json').version
const lockedDshVersion = require('../package.json').dependencies['@deepseek-ai/dsh']

export const ASKAI_DSH_HOST_PROTOCOL_VERSION = 'askai.dsh-host.v1'
export const ASKAI_DSH_KERNEL_VERSION = installedDshVersion
export const ASKAI_DSH_READY_EVENT = 'askai-dsh-runtime-ready'

export function runtimeHealth(inventory) {
  return {
    ok: installedDshVersion === lockedDshVersion,
    kernel: 'dsh',
    version: ASKAI_DSH_KERNEL_VERSION,
    lockedVersion: lockedDshVersion,
    protocolVersion: ASKAI_DSH_HOST_PROTOCOL_VERSION,
    runtimes: inventory,
  }
}
