import { resolve } from 'node:path'
import { mkdir } from 'node:fs/promises'
import { createHash } from 'node:crypto'
import { createUserMessage } from '@deepseek-ai/dsh-llm'
import { SessionId } from '@deepseek-ai/dsh-session'
import { scopeOf } from '@deepseek-ai/dsh-scope'
import { assembleContextFor } from '@deepseek-ai/dsh-agent'

import * as DeterministicModelPlugin from './deterministic-model-plugin.mjs'
import { AskaiModelGatewayAdapter } from './askai-model-gateway-plugin.mjs'
import { EventJournal } from './event-journal.mjs'
import { NativePluginRegistry } from './native-plugin-registry.mjs'
import { AskaiToolBridge } from './askai-tool-bridge-plugin.mjs'
import { AskaiWebSearchProvider } from './askai-web-search-provider.mjs'
import { RuntimeTemporalContext } from './runtime-temporal-context.mjs'
import { RuntimeTurnContext } from './runtime-turn-context.mjs'
import { OfficialDshHostComposition } from './official-host/composition.mjs'
import { ASKAI_ENTERPRISE_PRESET_ID } from './official-host/overlay.mjs'
import { currentPermissionPreset } from './official-host/api-compat.mjs'
import { OfficialSessionComposer, enterpriseToolNames } from './official-host/session-composer.mjs'
import { capabilityToolContracts, modelToolContracts } from './official-host/tool-contract-inventory.mjs'
import { DshWorkspaceService } from './workspace-service.mjs'
import { cancelSessionWork } from './session-cancellation.mjs'
import { DesktopApprovalBroker } from './desktop-approval-broker.mjs'
import { registerAskaiSkillProvider } from './askai-skill-provider.mjs'
import { invokeSelectedSkill, resolveSkillTurnContext } from './skill-turn-selection.mjs'

export class KernelRuntime {
  #ctx
  #handles = new Map()
  #journal = new EventJournal()
  #plugins
  #modelAdapter
  #modelAdapterDispose
  #toolBridge
  #webSearchProvider
  #webSearchDispose
  #temporalContext = new RuntimeTemporalContext()
  #turnContext = new RuntimeTurnContext()
  #composition
  #sessionComposer
  #workspaces
  #desktopApprovals
  #skillProviderDispose

  constructor({ runtimeId, isolationKey, profileVersion, storageRoot, modelProfile }) {
    this.runtimeId = runtimeId
    this.isolationKey = isolationKey
    this.profileVersion = profileVersion
    this.modelProfile = modelProfile === undefined ? undefined : Object.freeze(structuredClone(modelProfile))
    const storageKey = createHash('sha256').update(isolationKey).digest('hex')
    this.storageRoot = resolve(storageRoot, storageKey)
  }

  async start() {
    await mkdir(this.storageRoot, { recursive: true })
    this.#composition = new OfficialDshHostComposition({
      storageRoot: this.storageRoot,
      webSearchProvider: this.modelProfile?.toolProfile === undefined ? undefined : 'askai-enterprise',
    })
    const ctx = await this.#composition.start()
    this.#ctx = ctx
    this.#temporalContext.install(ctx)
    this.#turnContext.install(ctx)
    this.#skillProviderDispose = registerAskaiSkillProvider(ctx, this.modelProfile?.skillProfile)
    if (this.modelProfile?.toolProfile !== undefined) {
      this.#webSearchProvider = new AskaiWebSearchProvider(ctx, {
        ...this.modelProfile.toolProfile,
        profileVersion: this.profileVersion,
      })
      this.#webSearchDispose = ctx.web.registerSearchProvider(this.#webSearchProvider)
    }
    this.#desktopApprovals = new DesktopApprovalBroker(ctx, {
      excludedTools: enterpriseToolNames(this.modelProfile),
    })
    if (this.modelProfile === undefined) await ctx.plugin(DeterministicModelPlugin)
    else {
      this.#modelAdapter = new AskaiModelGatewayAdapter(this.modelProfile)
      this.#modelAdapterDispose = ctx.llm.registerAdapter(['askai-model-gateway'], this.#modelAdapter)
    }
    if (this.modelProfile?.toolProfile !== undefined) {
      this.#toolBridge = new AskaiToolBridge(ctx, {
        ...this.modelProfile.toolProfile,
        profileVersion: this.profileVersion,
      })
    }
    this.#sessionComposer = new OfficialSessionComposer(ctx, {
      agentOptions: this.#agentOptions(),
      enterpriseTools: enterpriseToolNames(this.modelProfile),
    })
    this.#workspaces = new DshWorkspaceService(ctx.workspaceRegistry)

    ctx.on('session/event', (session, event) => {
      this.#journal.append(session.id, event.type, event.data, event.seq)
    }, { global: true })
    ctx.on('agent/status', ({ agent, status }) => {
      this.#journal.append(agent.id, 'agent/status', { status })
    }, { global: true })
    this.#plugins = new NativePluginRegistry(ctx, {
      composed: specifier => this.#composition.inventory().entries
        .some(entry => entry.enabled && entry.moduleName === specifier),
    })
  }

  async createSession({
    sessionId, cwd, workspaceId, presetId = ASKAI_ENTERPRISE_PRESET_ID,
    permissionPreset, seed, parentSessionId,
  }) {
    this.#assertStarted()
    if (this.#handles.has(sessionId)) throw new Error(`session already live: ${sessionId}`)
    if (cwd !== undefined && workspaceId !== undefined) throw new Error('session cannot specify both cwd and workspaceId')
    const workspace = workspaceId === undefined
      ? undefined
      : (await this.#workspaces.get(workspaceId, { requireAvailable: true })).workspace
    const composition = await this.#sessionComposer.prepare(presetId)
    const handle = await this.#ctx.agents.create({
      sessionId: SessionId(sessionId),
      meta: {
        ...(workspace === undefined && cwd === undefined ? {} : { cwd: workspace?.path ?? resolve(cwd) }),
        agentPreset: composition.presetId,
        ...(parentSessionId === undefined ? {} : {
          parentSession: SessionId(parentSessionId),
          seedLength: seed.length,
        }),
      },
      ...(seed === undefined ? {} : { seed }),
      agentOptions: this.#agentOptions(),
      setup: composition.setup,
    })
    this.#handles.set(sessionId, handle)
    try {
      if (permissionPreset !== undefined) this.#ctx.permissionPresets.set(handle.agent.session, permissionPreset)
      if (workspace !== undefined) await this.#workspaces.attachSession(workspace.id, sessionId)
      return await this.describeSession(handle.agent)
    } catch (error) {
      this.#handles.delete(sessionId)
      await handle.dispose()
      throw error
    }
  }

  async exportCompletedSeed(sessionId) {
    const agent = this.#requireAgent(sessionId)
    await agent.whenIdle()
    return structuredClone(agent.session.events)
  }

  async resumeSession(sessionId) {
    this.#assertStarted()
    const live = this.#handles.get(sessionId)
    if (live !== undefined) return await this.describeSession(live.agent)
    const identity = await this.#sessionComposer.persistedIdentity(sessionId)
    const composition = await this.#sessionComposer.prepare(identity.presetId)
    const handle = await this.#ctx.agents.resume({
      resumeSessionId: SessionId(sessionId),
      agentOptions: this.#agentOptions(),
      setup: composition.setup,
    })
    this.#handles.set(sessionId, handle)
    this.#journal.resetFromSession(handle.agent.session)
    this.#journal.append(sessionId, 'agent/status', { status: handle.agent.status })
    return await this.describeSession(handle.agent)
  }

  send({ sessionId, mode, content, temporalContext, turnContext }) {
    const agent = this.#requireAgent(sessionId)
    if (temporalContext === undefined || temporalContext === null) {
      throw new TypeError('temporalContext is required for every MOVO turn')
    }
    this.#temporalContext.update(sessionId, temporalContext)
    const resolvedTurnContext = resolveSkillTurnContext(this.modelProfile, turnContext)
    this.#turnContext.update(sessionId, resolvedTurnContext.context)
    const message = createUserMessage({
      content: content.map((block, index) => {
        if (block.type !== 'text') throw new Error(`this Runtime Profile only accepts text content: ${block.type}`)
        const text = String(block.data?.text ?? '')
        return { type: 'text', text: index === 0 ? invokeSelectedSkill(resolvedTurnContext.skillName, text) : text }
      }),
      source: { kind: 'user' },
    })
    if (mode === 'steer') agent.steer(message)
    else agent.followup(message)
    return { accepted: true, messageId: message.id }
  }

  async cancel(sessionId, cause) {
    const agent = this.#requireAgent(sessionId)
    return await cancelSessionWork(this.#ctx, agent, cause)
  }

  pendingApprovals(sessionId) {
    this.#requireAgent(sessionId)
    return this.#desktopApprovals.list(sessionId)
  }

  decideApproval(sessionId, approvalId, outcome, grantScope) {
    this.#requireAgent(sessionId)
    return this.#desktopApprovals.decide(sessionId, approvalId, outcome, grantScope)
  }

  events(sessionId, afterCursor) {
    this.#requireAgent(sessionId)
    return this.#journal.replay(sessionId, afterCursor)
  }

  subscribeEvents(sessionId, afterCursor, subscriber) {
    this.#requireAgent(sessionId)
    return this.#journal.subscribe(sessionId, afterCursor, subscriber)
  }

  refreshModelCredential(credential) {
    if (this.#modelAdapter === undefined) throw new Error('runtime does not use MOVO Model Gateway')
    this.#modelAdapter.updateCredential(credential)
    return { refreshed: true }
  }

  refreshToolCredential(credential) {
    if (this.#toolBridge === undefined) throw new Error('runtime does not use MOVO Tool Gateway')
    this.#toolBridge.updateCredential(credential.accessToken)
    this.#webSearchProvider?.updateCredential(credential.accessToken)
    return { refreshed: true }
  }

  async describeSession(agent) {
    const assembly = await this.#ctx.systemPrompt.assemble(assembleContextFor(agent))
    const workspace = await this.#workspaces.resolveSessionWorkspace(agent.session)
    return {
      sessionId: agent.id,
      status: agent.status,
      profileVersion: this.profileVersion,
      model: { provider: agent.options.provider, model: agent.options.model },
      presetId: agent.session.header.agentPreset,
      seedLength: agent.session.header.seedLength ?? 0,
      workspaceId: workspace === undefined ? null : String(workspace.id),
      permissionPreset: currentPermissionPreset(
        this.#ctx.permissionPresets,
        agent.session,
        this.#composition.installation.version,
      ),
      modelTools: assembly.tools.map(tool => tool.name),
      capabilityTools: this.#ctx.tools.schemas(scopeOf(agent.ctx)).map(tool => tool.name),
    }
  }

  async listWorkspaces() { return await this.#workspaces.list() }
  async createWorkspace(input) { return await this.#workspaces.create(input) }
  async renameWorkspace(workspaceId, input) { return await this.#workspaces.rename(workspaceId, input.title) }
  async deleteWorkspace(workspaceId) { return await this.#workspaces.delete(workspaceId) }

  async describeLiveSession(sessionId) {
    return await this.describeSession(this.#requireAgent(sessionId))
  }

  async upgradeContractInventory(sessionId) {
    const agent = this.#requireAgent(sessionId)
    const assembly = await this.#ctx.systemPrompt.assemble(assembleContextFor(agent))
    return {
      modelTools: modelToolContracts(assembly.tools),
      capabilityTools: capabilityToolContracts(this.#ctx.tools.schemas(scopeOf(agent.ctx))),
    }
  }

  async disposeSession(sessionId) {
    const handle = this.#handles.get(sessionId)
    if (handle === undefined) return { disposed: false }
    this.#handles.delete(sessionId)
    this.#temporalContext.remove(sessionId)
    this.#turnContext.remove(sessionId)
    this.#desktopApprovals.clearSession(sessionId)
    await handle.agent.whenIdle()
    await handle.dispose()
    this.#journal.remove(sessionId)
    return { disposed: true }
  }

  async loadPlugin(specifier) {
    return this.#plugins.load(specifier)
  }

  async probePlugin(specifier) {
    return this.#plugins.probe(specifier)
  }

  async unloadPlugin(specifier) {
    return this.#plugins.unload(specifier)
  }

  pluginInventory() {
    return {
      official: this.#composition.inventory(),
      dynamic: this.#plugins.list(),
    }
  }

  async dispose() {
    for (const [sessionId, handle] of [...this.#handles.entries()]) {
      this.#handles.delete(sessionId)
      handle.agent.cancel({ kind: 'disposed' })
      await handle.dispose()
    }
    this.#modelAdapterDispose?.()
    this.#desktopApprovals?.dispose()
    this.#toolBridge?.dispose()
    this.#webSearchDispose?.()
    this.#skillProviderDispose?.()
    this.#temporalContext.dispose()
    this.#turnContext.dispose()
    await this.#composition?.dispose()
    this.#ctx = undefined
  }

  #assertStarted() {
    if (this.#ctx === undefined) throw new Error('runtime is not started')
  }

  #agentOptions() {
    if (this.modelProfile === undefined) {
      return { provider: 'askai-deterministic', model: 'deterministic-v1' }
    }
    return {
      provider: 'askai-model-gateway',
      model: this.modelProfile.modelName,
      maxTokens: this.modelProfile.maxOutputTokens || undefined,
    }
  }

  #requireAgent(sessionId) {
    this.#assertStarted()
    const handle = this.#handles.get(sessionId)
    if (handle === undefined) throw new Error(`session is not live: ${sessionId}`)
    return handle.agent
  }
}
