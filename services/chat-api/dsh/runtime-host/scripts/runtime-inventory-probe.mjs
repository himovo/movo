import { mkdtemp, rm } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'

import { KernelRuntime } from '../src/kernel-runtime.mjs'

const root = await mkdtemp(join(tmpdir(), 'askai-dsh-inventory-'))
const runtime = new KernelRuntime({
  runtimeId: 'upgrade-inventory',
  isolationKey: 'upgrade:inventory',
  profileVersion: 'upgrade-inventory-v1',
  storageRoot: root,
  modelProfile: {
    profileVersion: 'upgrade-inventory-v1',
    modelInstanceId: 'upgrade-inventory-model',
    modelName: 'upgrade-inventory-model',
    gatewayUrl: 'http://127.0.0.1:9/model',
    accessToken: 'UPGRADE_INVENTORY_MODEL_TOKEN',
    toolProfile: {
      gatewayUrl: 'http://127.0.0.1:9/tools',
      accessToken: 'UPGRADE_INVENTORY_TOOL_TOKEN',
      tools: [],
      nativeReplacements: [],
    },
  },
})

try {
  await runtime.start()
  const ordinary = await runtime.createSession({ sessionId: 'ordinary' })
  const code = await runtime.createSession({ sessionId: 'code', presetId: 'code', cwd: root })
  const ordinaryContracts = await runtime.upgradeContractInventory('ordinary')
  const codeContracts = await runtime.upgradeContractInventory('code')
  const inventory = runtime.pluginInventory().official
  process.stdout.write(`${JSON.stringify({
    dshVersion: inventory.dshVersion,
    overlayVersion: inventory.overlayVersion,
    enabledModules: inventory.entries
      .filter(entry => entry.enabled)
      .map(entry => entry.moduleName)
      .sort(),
    presets: {
      ordinary: {
        id: ordinary.presetId,
        modelTools: ordinary.modelTools,
        capabilityTools: ordinary.capabilityTools,
        toolContracts: ordinaryContracts,
      },
      code: {
        id: code.presetId,
        modelTools: code.modelTools,
        capabilityTools: code.capabilityTools,
        toolContracts: codeContracts,
      },
    },
  })}\n`)
} finally {
  await runtime.dispose()
  await rm(root, { recursive: true, force: true })
}
