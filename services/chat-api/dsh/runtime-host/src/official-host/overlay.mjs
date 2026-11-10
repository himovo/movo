import { resolve } from 'node:path'

import { planOverlayRows } from './overlay-planner.mjs'

export const ASKAI_DSH_HOST_OVERLAY_VERSION = 'askai-dsh-host-v2'
export const ASKAI_ENTERPRISE_PRESET_ID = 'askai-enterprise'

function hostRows({ askaiPresetRoot, shippedPresetRoot, storageDomainRoot, hostFeatures, declarativePresets, pluginWeb }) {
  return [
    ...(declarativePresets ? [] : [{
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
    }]),
    ...(declarativePresets ? [{
      id: 'preset-askai-enterprise',
      name: '@deepseek-ai/dsh-agent-preset',
      config: {
        id: ASKAI_ENTERPRISE_PRESET_ID,
        name: 'MOVO 企业助手',
        description: '使用 MOVO 企业工具的普通会话',
        order: 0,
        plugins: [
          { id: 'askai-enterprise-persona', name: resolve(askaiPresetRoot, '..', '..', 'src', 'official-host', 'enterprise-preset-plugin.mjs') },
          { id: 'tool-web', name: '@deepseek-ai/dsh-tool-web', config: { fetch: false, searchTimeoutMs: 60000 } },
          { id: 'tool-skill', name: '@deepseek-ai/dsh-tool-skill' },
          { id: 'tool-ask-user', name: '@deepseek-ai/dsh-tool-ask-user' },
        ],
      },
    }] : []),
    ...(hostFeatures.subagentModelSelection
      ? [{
          id: 'subagent-model-selection-settings',
          name: '@deepseek-ai/dsh-tool-subagent/model-selection-settings',
        }]
      : []),
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
    ...(pluginWeb ? [{ id: 'workspace-controller', name: '@deepseek-ai/dsh-api-workspace-controller' }] : []),
    ...(pluginWeb ? [{
      id: 'plugin-web-server',
      name: '@deepseek-ai/dsh-host-webserver',
      config: { host: '127.0.0.1', port: 0 },
    },
    {
      id: 'plugin-web-runtime',
      name: '@deepseek-ai/dsh-web-app',
      config: { openBrowser: false, printUrl: false, surfaceContext: false, trustedHosts: [] },
    },
    { id: 'plugin-client-modules', name: '@deepseek-ai/dsh-client-modules' },
    { id: 'plugin-session-controller', name: '@deepseek-ai/dsh-api-session-controller' },
    {
      id: 'plugin-client-connection',
      name: '@deepseek-ai/dsh-client-connection',
      inject: ['webRuntime'],
      config: { trustedHosts: [] },
    }] : []),
    { id: 'plugin-inventory', name: '@deepseek-ai/dsh-host-plugin-inventory' },
  ]
}

export function buildAskaiHostOverlay({
  storageRoot,
  durableStorageRoot,
  askaiPresetRoot,
  shippedPresetRoot = askaiPresetRoot,
  declarativePresets = false,
  webSearchProvider,
  occupiedIds = new Set(),
  hostFeatures = { subagentModelSelection: false },
  pluginWeb = false,
  pluginModelName,
}) {
  const sessionRoot = resolve(storageRoot)
  const runtimeHome = resolve(storageRoot, 'dsh-home')
  const storageDomainRoot = resolve(durableStorageRoot ?? storageRoot, 'host-storage')
  const rows = hostRows({
    askaiPresetRoot,
    shippedPresetRoot,
    storageDomainRoot,
    hostFeatures,
    declarativePresets,
    pluginWeb,
  })
  return [
    ...(declarativePresets ? [{ id: 'agent-preset-registry', config: { default: ASKAI_ENTERPRISE_PRESET_ID } }] : []),
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
    ...(pluginWeb && pluginModelName ? [{
      id: 'agent-default-model',
      config: { provider: 'askai-model-gateway', model: pluginModelName },
    }] : []),
    ...(pluginWeb && pluginModelName ? [
      { id: 'llm-deepseek', disabled: true },
      { id: 'llm-deepseek-account', disabled: true },
      { id: 'llm-pi-ai', disabled: true },
    ] : []),
    { id: 'attachment-local', config: { dshHome: runtimeHome } },
    ...(webSearchProvider
      ? [{ id: 'web', config: { searchProvider: webSearchProvider } }]
      : []),
    ...planOverlayRows(rows, occupiedIds),
  ]
}
