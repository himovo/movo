import assert from 'node:assert/strict'
import { mkdtemp, readFile, readdir, rm } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import test from 'node:test'

import { KernelRuntime } from '../src/kernel-runtime.mjs'
import { ASKAI_DSH_KERNEL_VERSION } from '../src/host-protocol.mjs'
import { OfficialDshHostComposition } from '../src/official-host/composition.mjs'
import {
  ASKAI_DSH_HOST_OVERLAY_VERSION,
  ASKAI_ENTERPRISE_PRESET_ID,
  buildAskaiHostOverlay,
} from '../src/official-host/overlay.mjs'
import { DSH_CODE_PRESET_ID, resolveNativePreset } from '../src/official-host/api-compat.mjs'
import { extractOfficialPresetIsolation } from '../src/official-host/preset-isolation.mjs'
import {
  collectInsertedEntryIds,
  planOverlayRows,
} from '../src/official-host/overlay-planner.mjs'
import { readPluginInventory } from '../src/official-host/inventory-compat.mjs'

const REQUIRED_HOST_MODULES = new Set([
  '@deepseek-ai/dsh-session',
  '@deepseek-ai/dsh-session-persistence-jsonl',
  '@deepseek-ai/dsh-sandbox-local',
  '@deepseek-ai/dsh-sandbox-policy',
  '@deepseek-ai/dsh-user-approval',
  '@deepseek-ai/dsh-tools',
  '@deepseek-ai/dsh-agent-presets',
  '@deepseek-ai/dsh-code-runtime-worker-thread',
  '@deepseek-ai/dsh-workspace',
  '@deepseek-ai/dsh-host-plugin-inventory',
])

const REQUIRED_CODE_CAPABILITIES = new Set([
  'read',
  'write',
  'edit',
  'glob',
  'grep',
  'bash',
  'job_list',
  'job_output',
  'job_kill',
  'skill',
  'todo_write',
  'subagent',
])

test('official Web patch remains the source of truth for preset isolation', () => {
  const extracted = extractOfficialPresetIsolation([
    { insert: [{ id: 'unrelated-host-row' }] },
    { id: 'tool-bash', disabled: true },
    { id: 'tool-fs', disabled: true },
    { id: 'tool-skill', disabled: true },
    { id: 'compaction-basic', disabled: true },
    { id: 'tool-subagent', disabled: true },
    { id: 'agent-instructions', disabled: true },
    { id: 'tool-web', disabled: true },
    { insert: [{ id: 'agent-presets' }] },
    { id: 'unrelated-client-row', disabled: true },
  ])
  assert.deepEqual(extracted.disabledIds, [
    'tool-bash',
    'tool-fs',
    'tool-skill',
    'compaction-basic',
    'tool-subagent',
    'agent-instructions',
    'tool-web',
  ])
})

test('ASKAI overlay configures official rows and inserts only missing rows', () => {
  const occupied = collectInsertedEntryIds([
    { insert: [{ id: 'storage' }, { id: 'storage-json' }] },
    { id: 'unrelated', disabled: true },
  ])
  const patches = planOverlayRows([
    { id: 'storage', name: 'official-storage' },
    { id: 'storage-json', name: 'official-json', config: { root: '/askai' } },
    { id: 'workspace', name: 'askai-workspace' },
  ], occupied)
  assert.deepEqual(patches, [
    { id: 'storage-json', config: { root: '/askai' } },
    { insert: [{ id: 'workspace', name: 'askai-workspace' }] },
  ])
})

test('ASKAI overlay mounts alpha-only host features only when the installed package exports them', () => {
  const base = {
    storageRoot: '/tmp/askai-overlay',
    askaiPresetRoot: '/tmp/askai-presets',
  }
  const withoutFeature = buildAskaiHostOverlay(base)
  const withFeature = buildAskaiHostOverlay({
    ...base,
    hostFeatures: { subagentModelSelection: true },
  })
  const insertedNames = patches => patches
    .flatMap(patch => patch.insert ?? [])
    .map(row => row.name)
  assert.equal(insertedNames(withoutFeature).includes(
    '@deepseek-ai/dsh-tool-subagent/model-selection-settings',
  ), false)
  assert.equal(insertedNames(withFeature).includes(
    '@deepseek-ai/dsh-tool-subagent/model-selection-settings',
  ), true)
})

test('plugin inventory compatibility flattens native preset compositions', async () => {
  const inventory = await readPluginInventory({
    async list() {
      return {
        entries: [{ entryId: 'root', moduleName: 'root-module', enabled: true, fiberPhase: 'active' }],
        agentPresets: [{
          id: 'standard',
          rows: [{ entryId: 'tool-fs', moduleName: 'fs-module', enabled: true, fiberPhase: null }],
        }],
      }
    },
  })
  assert.deepEqual(inventory.entries.map(row => row.moduleName), ['root-module', 'fs-module'])
})

async function withTempRoot(run) {
  const root = await mkdtemp(join(tmpdir(), 'askai-dsh-official-host-'))
  try {
    return await run(root)
  } finally {
    await rm(root, { recursive: true, force: true })
  }
}

function kernel(root, isolationKey = 'tenant:profile') {
  return new KernelRuntime({
    runtimeId: `runtime-${isolationKey}`,
    isolationKey,
    profileVersion: 'profile-v1',
    storageRoot: root,
  })
}

function enterpriseCodeKernel(root) {
  const descriptor = {
    name: 'askai_mcp_lookup',
    version: 'tool-enterprise-lookup-v1',
    source_type: 'mcp',
    external_tool_id: 'enterprise-lookup',
    mcp_tool_name: 'lookup',
    description: 'Look up governed enterprise data',
    input_schema: { type: 'object', properties: { query: { type: 'string' } }, required: ['query'] },
    output_schema: {},
    output_validation: 'none',
    risk_level: 'read',
    approval_required: false,
    required_scopes: ['tools:read'],
    timeout_ms: 15000,
  }
  return new KernelRuntime({
    runtimeId: 'runtime-enterprise-code',
    isolationKey: 'tenant:enterprise-code',
    profileVersion: 'profile-enterprise-code',
    storageRoot: root,
    modelProfile: {
      profileVersion: 'profile-enterprise-code',
      modelInstanceId: 'managed-model-a',
      modelName: 'managed-model',
      displayName: 'Managed Model',
      gatewayUrl: 'http://127.0.0.1:9/model',
      accessToken: 'EPHEMERAL_MODEL_TOKEN_MUST_NOT_PERSIST',
      toolProfile: {
        gatewayUrl: 'http://127.0.0.1:9/tools',
        accessToken: 'EPHEMERAL_TOOL_TOKEN_MUST_NOT_PERSIST',
        tools: [descriptor],
        nativeReplacements: [],
      },
    },
  })
}

async function persistedText(root) {
  const paths = await readdir(root, { recursive: true, withFileTypes: true })
  const files = paths.filter(item => item.isFile() && item.name.endsWith('.jsonl'))
  return (await Promise.all(files.map(item => readFile(`${item.parentPath}/${item.name}`, 'utf8')))).join('\n')
}

test('official Host boots the pinned Base, Workspace, inventory, and shipped presets', async () => {
  await withTempRoot(async root => {
    const host = new OfficialDshHostComposition({ storageRoot: root })
    try {
      const ctx = await host.start()
      const inventory = host.inventory()
      assert.equal(inventory.overlayVersion, ASKAI_DSH_HOST_OVERLAY_VERSION)
      assert.equal(inventory.dshVersion, ASKAI_DSH_KERNEL_VERSION)
      assert.ok(inventory.presetIsolationRows.includes('agent-instructions'))
      const active = new Set(inventory.entries
        .filter(entry => entry.enabled && entry.fiberPhase === 'active')
        .map(entry => entry.moduleName))
      for (const moduleName of REQUIRED_HOST_MODULES) assert.ok(active.has(moduleName), moduleName)
      assert.equal(active.has('@deepseek-ai/dsh-session-title-first-prompt-llm'), false)

      const presets = ctx.get('agentPresets')
      assert.ok(presets)
      const roster = await presets.list()
      for (const id of [ASKAI_ENTERPRISE_PRESET_ID]) {
        const preset = roster.find(item => item.id === id)
        assert.ok(preset, id)
        assert.equal(preset.broken, undefined)
      }
      const shippedCode = await resolveNativePreset(presets, DSH_CODE_PRESET_ID)
      assert.ok(shippedCode.path.startsWith(host.installation.shippedPresetRoot))

      const workspaceDir = join(root, 'workspace')
      await import('node:fs/promises').then(({ mkdir }) => mkdir(workspaceDir))
      const workspace = await ctx.workspaceRegistry.create(workspaceDir, 'Step 2 workspace')
      assert.equal(ctx.workspaceRegistry.list()[0].id, workspace.id)
    } finally {
      await host.dispose()
    }
  })
})

test('ordinary and code sessions use isolated official preset capability surfaces', async () => {
  await withTempRoot(async root => {
    const runtime = kernel(root)
    try {
      await runtime.start()
      const ordinary = await runtime.createSession({ sessionId: 'ordinary' })
      assert.equal(ordinary.presetId, ASKAI_ENTERPRISE_PRESET_ID)
      assert.deepEqual(ordinary.modelTools, [])
      assert.deepEqual(ordinary.capabilityTools, [])

      const code = await runtime.createSession({
        sessionId: 'code',
        presetId: DSH_CODE_PRESET_ID,
        cwd: root,
      })
      assert.equal(code.presetId, DSH_CODE_PRESET_ID)
      const modelTools = new Set(code.modelTools)
      for (const name of REQUIRED_CODE_CAPABILITIES) assert.ok(modelTools.has(name), name)
      assert.equal(modelTools.has('run_code'), false)
      const capabilities = new Set(code.capabilityTools)
      for (const name of REQUIRED_CODE_CAPABILITIES) assert.ok(capabilities.has(name), name)
      assert.equal(capabilities.has('code_task'), false)
      assert.equal(capabilities.has('coding.local_task'), false)

      const inventory = runtime.pluginInventory().official.entries
      const mountedModules = new Set(inventory.filter(entry => entry.enabled).map(entry => entry.moduleName))
      for (const moduleName of [
        '@deepseek-ai/dsh-tool-fs',
        '@deepseek-ai/dsh-tool-fs-search',
        '@deepseek-ai/dsh-tool-bash',
        '@deepseek-ai/dsh-tool-jobs',
        '@deepseek-ai/dsh-skill-filesystem',
        '@deepseek-ai/dsh-agent-tool-presentation',
      ]) assert.ok(mountedModules.has(moduleName), moduleName)

      assert.deepEqual((await runtime.describeLiveSession('ordinary')).capabilityTools, [])
    } finally {
      await runtime.dispose()
    }
  })
})

test('a persisted code session resumes with its original preset and cwd composition', async () => {
  await withTempRoot(async root => {
    const first = kernel(root, 'tenant:persisted')
    await first.start()
    const created = await first.createSession({
      sessionId: 'persisted-code',
      presetId: DSH_CODE_PRESET_ID,
      cwd: root,
    })
    assert.equal(created.presetId, DSH_CODE_PRESET_ID)
    await first.dispose()

    const second = kernel(root, 'tenant:persisted')
    try {
      await second.start()
      const resumed = await second.resumeSession('persisted-code')
      assert.equal(resumed.presetId, DSH_CODE_PRESET_ID)
      assert.ok(resumed.modelTools.includes('bash'))
      assert.equal(resumed.modelTools.includes('run_code'), false)
      assert.ok(resumed.capabilityTools.includes('bash'))
      assert.equal(resumed.capabilityTools.includes('code_task'), false)
    } finally {
      await second.dispose()
    }
  })
})

test('official Code composition coexists with managed model and enterprise tools without persisting credentials', async () => {
  await withTempRoot(async root => {
    const runtime = enterpriseCodeKernel(root)
    try {
      await runtime.start()
      const code = await runtime.createSession({ sessionId: 'enterprise-code', presetId: DSH_CODE_PRESET_ID, cwd: root })
      assert.ok(code.modelTools.includes('bash'))
      assert.equal(code.modelTools.includes('run_code'), false)
      const capabilities = new Set(code.capabilityTools)
      for (const name of ['askai_mcp_lookup', 'web_search', 'read', 'write', 'bash']) {
        assert.ok(capabilities.has(name), name)
      }
      assert.equal(capabilities.has('code_task'), false)
    } finally {
      await runtime.dispose()
    }
    const persisted = await persistedText(root)
    assert.doesNotMatch(persisted, /EPHEMERAL_(MODEL|TOOL)_TOKEN_MUST_NOT_PERSIST/)
  })
})
