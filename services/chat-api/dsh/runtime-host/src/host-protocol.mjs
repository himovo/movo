export const ASKAI_DSH_HOST_PROTOCOL_VERSION = 'askai.dsh-host.v1'
export const ASKAI_DSH_KERNEL_VERSION = '0.1.2-alpha.2'
export const ASKAI_DSH_READY_EVENT = 'askai-dsh-runtime-ready'

export function runtimeHealth(inventory) {
  return {
    ok: true,
    kernel: 'dsh',
    version: ASKAI_DSH_KERNEL_VERSION,
    protocolVersion: ASKAI_DSH_HOST_PROTOCOL_VERSION,
    runtimes: inventory,
  }
}
