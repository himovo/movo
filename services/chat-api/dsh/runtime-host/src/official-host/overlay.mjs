import { resolve } from 'node:path'

import { planOverlayRows } from './overlay-planner.mjs'

export const ASKAI_DSH_HOST_OVERLAY_VERSION = 'askai-dsh-host-v1'
export const ASKAI_ENTERPRISE_PRESET_ID = 'askai-enterprise'

function hostRows({ askaiPresetRoot, shippedPresetRoot, storageDomainRoot, hostFeatures }) {
  return [
    {
      id: 'agent-presets',
      name: '@deepseek-ai/dsh-agent-presets',
      config: {
        default: ASKAI_ENTERPRISE_PRESET_ID,
        // Own the complete root order explicitly. 0.1.2 introduced an implicit
        // shipped root while the rollback train requires the same root in this
        // list; disabling the implicit root prevents duplicate preset mounts.
        includeShippedRoot: false,
        roots: [
          { path: resolve(askaiPresetRoot), trust: 'system' },
          { path: resolve(shippedPresetRoot), trust: 'system' },
        ],
        includeUserRoot: false,
      },
    },
    ...(hostFeatures.subagentModelSelection
      ? [{
          id: 'subagent-model-selection-settings',
          name: '@deepseek-ai/dsh-tool-subagent/model-selection-settings',
        }]
      : []),
    { id: 'code-runtime', name: '@deepseek-ai/dsh-code-runtime-worker-thread' },
    { id: 'storage', name: '@deepseek-ai/dsh-storage' },
    {
      id: 'storage-json',
      name: '@deepseek-ai/dsh-storage-json',
      config: { root: storageDomainRoot },
    },
    {
      id: 'storage-domain',
      name: '@deepseek-ai/dsh-storage-domain',
      config: { backend: 'json' },
    },
    { id: 'workspace', name: '@deepseek-ai/dsh-workspace' },
    { id: 'plugin-inventory', name: '@deepseek-ai/dsh-host-plugin-inventory' },
  ]
}

export function buildAskaiHostOverlay({
  storageRoot,
  askaiPresetRoot,
  shippedPresetRoot = askaiPresetRoot,
  webSearchProvider,
  occupiedIds = new Set(),
  hostFeatures = { subagentModelSelection: false },
}) {
  const sessionRoot = resolve(storageRoot)
  const runtimeHome = resolve(storageRoot, 'dsh-home')
  const storageDomainRoot = resolve(storageRoot, 'host-storage')
  const rows = hostRows({
    askaiPresetRoot,
    shippedPresetRoot,
    storageDomainRoot,
    hostFeatures,
  })
  return [
    { id: 'hmr', disabled: true },
    // ASKAI owns the durable conversation title in its enterprise database.
    // Keep DSH's title service/API, but do not pay for a second first-prompt LLM
    // title that has no authoritative consumer in this deployment.
    { id: 'session-title-llm', disabled: true },
    {
      id: 'session-persistence-jsonl',
      config: { root: sessionRoot, compression: 'none' },
    },
    { id: 'settings', config: { dshHome: runtimeHome, watch: false } },
    { id: 'credentials', config: { dshHome: runtimeHome, watch: false } },
    { id: 'attachment-local', config: { dshHome: runtimeHome } },
    ...(webSearchProvider
      ? [{ id: 'web', config: { searchProvider: webSearchProvider } }]
      : []),
    ...planOverlayRows(rows, occupiedIds),
  ]
}
