import { join, resolve } from 'node:path'
import { chmod, mkdir } from 'node:fs/promises'
import { createHash } from 'node:crypto'
import { createUserMessage } from '@deepseek-ai/dsh-llm'
import { SessionId } from '@deepseek-ai/dsh-session'
import { scopeOf } from '@deepseek-ai/dsh-scope'
import { assembleContextFor } from '@deepseek-ai/dsh-agent'
import { setApprovalPolicy } from '@deepseek-ai/dsh-user-approval'

import * as DeterministicModelPlugin from './deterministic-model-plugin.mjs'
import { AskaiModelGatewayAdapter } from './askai-model-gateway-plugin.mjs'
import { EventJournal } from './event-journal.mjs'
import { NativePluginRegistry } from './native-plugin-registry.mjs'
import { ManagedPluginBridge } from './managed-plugin-bridge.mjs'
import { AskaiToolBridge } from './askai-tool-bridge-plugin.mjs'
import { AskaiWebSearchProvider } from './askai-web-search-provider.mjs'
import { hasConfiguredWebSearch } from './web-search-availability.mjs'
import { RuntimeTemporalContext } from './runtime-temporal-context.mjs'
import { RuntimeTurnContext } from './runtime-turn-context.mjs'
import { OfficialDshHostComposition } from './official-host/composition.mjs'
import { globalPluginCapabilities, sessionPluginCapabilities } from './official-host/plugin-capability-snapshot.mjs'
import { compatibleSessionEvents } from './official-host/event-compat.mjs'
import { LiveAssistantStream } from './official-host/live-assistant-stream.mjs'
import { ASKAI_ENTERPRISE_PRESET_ID } from './official-host/overlay.mjs'
import { currentPermissionPreset, normalizePersistedPreset } from './official-host/api-compat.mjs'
import { OfficialSessionComposer, enterpriseToolNames } from './official-host/session-composer.mjs'
import {
  inheritedEventCount,
  liveSessionEvents,
  sessionCreationLineage,
} from './official-host/session-state.mjs'
import { capabilityToolContracts, modelToolContracts } from './official-host/tool-contract-inventory.mjs'
import { DshWorkspaceService } from './workspace-service.mjs'
import { cancelSessionWork } from './session-cancellation.mjs'
import { DesktopApprovalBroker } from './desktop-approval-broker.mjs'
import { CodeApprovalReviewer } from './code-approval-reviewer.mjs'
import { UserQuestionBroker } from './user-question-broker.mjs'
import { codePermissionPolicy } from './code-permission-policy.mjs'
import { registerAskaiSkillProvider } from './askai-skill-provider.mjs'
import { invokeSelectedSkill, resolveSkillTurnContext } from './skill-turn-selection.mjs'
import { SkillInvocationTracker } from './skill-invocation-tracker.mjs'
import { registerSkillResourceTool } from './skill-resource-tool.mjs'
import { validConversationSpaceKey } from './personal-space.mjs'
import { resolvePluginCommand, requireCurrentCommand } from './plugin-command-selection.mjs'
import { NativePluginWeb } from './native-plugin-web.mjs'
import { migrateLegacyHostStorage } from './plugin-user-home.mjs'

export class KernelRuntime {
  #ctx
  #handles = new Map()
  #journal = new EventJournal()
  #liveAssistantStream = new LiveAssistantStream(this.#journal)
  #plugins
  #managedPlugins
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
  #userQuestions
  #skillProviderDispose
  #skillProvider
  #skillResourceToolDispose
  #skillInvocations
  #nativePluginWeb

  constructor({ runtimeId, isolationKey, profileVersion, storageRoot, modelProfile }) {
    this.runtimeId = runtimeId
    this.isolationKey = isolationKey
    this.profileVersion = profileVersion
    this.modelProfile = modelProfile === undefined ? undefined : Object.freeze(structuredClone(modelProfile))
    this.#skillInvocations = new SkillInvocationTracker(this.modelProfile?.skillProfile)
    const storageKey = createHash('sha256').update(isolationKey).digest('hex')
    this.storageRoot = resolve(storageRoot, storageKey)
  }

  async start() {
    await mkdir(this.storageRoot, { recursive: true })
    const durableStorageRoot = process.env.MOVO_DSH_PLUGIN_CHILD === '1' &&
      this.modelProfile?.subjectUserId ? process.env.HOME : undefined
    if (durableStorageRoot) await migrateLegacyHostStorage(durableStorageRoot, this.storageRoot)
    this.#composition = new OfficialDshHostComposition({
      storageRoot: this.storageRoot,
      durableStorageRoot,
      webSearchProvider: hasConfiguredWebSearch(this.modelProfile) ? 'askai-enterprise' : undefined,
      plugins: this.modelProfile?.plugins,
      pluginModelName: this.modelProfile?.modelName,
    })
    const ctx = await this.#composition.start()
    if (this.#composition.unavailablePlugins.length > 0) {
      console.warn('MOVO Runtime omitted incompatible DSH plugins:', this.#composition.unavailablePlugins)
      this.modelProfile = Object.freeze({
        ...this.modelProfile,
        plugins: this.#composition.availablePlugins,
      })
    }
    this.#ctx = ctx
    this.#nativePluginWeb = new NativePluginWeb(ctx, this.modelProfile?.plugins)
    this.#managedPlugins = new ManagedPluginBridge(ctx)
    this.#temporalContext.install(ctx)
    this.#turnContext.install(ctx, { visionEnabled: this.modelProfile?.visionEnabled === true })
    const skillProviderRegistration = registerAskaiSkillProvider(
      ctx, this.modelProfile?.skillProfile, {
        storageRoot: this.storageRoot,
        bundleGatewayUrl: this.modelProfile?.bundleGatewayUrl,
        accessToken: this.modelProfile?.accessToken,
      },
    )
    this.#skillProvider = skillProviderRegistration?.provider
    this.#skillProviderDispose = skillProviderRegistration?.dispose
    this.#skillResourceToolDispose = skillProviderRegistration === undefined
      ? undefined
      : registerSkillResourceTool(ctx, {
          provider: skillProviderRegistration.provider,
          invocations: this.#skillInvocations,
        })
    if (hasConfiguredWebSearch(this.modelProfile)) {
      this.#webSearchProvider = new AskaiWebSearchProvider(ctx, {
        ...this.modelProfile.toolProfile,
        profileVersion: this.profileVersion,
      })
      this.#webSearchDispose = ctx.web.registerSearchProvider(this.#webSearchProvider)
    }
    if (this.modelProfile === undefined) await ctx.plugin(DeterministicModelPlugin)
    else {
      this.#modelAdapter = new AskaiModelGatewayAdapter(this.modelProfile, ctx.get('attachments'))
      this.#modelAdapterDispose = ctx.llm.registerAdapter(['askai-model-gateway'], this.#modelAdapter)
    }
    this.#desktopApprovals = new DesktopApprovalBroker(ctx, {
      excludedTools: enterpriseToolNames(this.modelProfile),
      automaticReviewer: new CodeApprovalReviewer(this.#modelAdapter, this.modelProfile),
    })
    this.#userQuestions = new UserQuestionBroker(ctx)
    if (this.modelProfile?.toolProfile !== undefined) {
      this.#toolBridge = new AskaiToolBridge(ctx, {
        ...this.modelProfile.toolProfile,
        profileVersion: this.profileVersion,
      }, { skillInvocations: this.#skillInvocations })
    }
    this.#sessionComposer = new OfficialSessionComposer(ctx, {
      agentOptions: this.#agentOptions(),
      enterpriseTools: enterpriseToolNames(this.modelProfile),
      plugins: this.modelProfile?.plugins,
    })
    this.#workspaces = new DshWorkspaceService(ctx.workspaceRegistry)

    ctx.on('agent/assistant-stream', ({ agent, frame }) => {
      this.#liveAssistantStream.observeFrame(agent.id, frame)
    }, { global: true })
    ctx.on('session/event', (session, event) => {
      this.#liveAssistantStream.observeSessionEvent(session, event)
      const selection = this.#skillInvocations.observe(session.id, event)
      if (selection !== undefined) this.#journal.append(session.id, 'skill/selected', selection)
    }, { global: true })
    ctx.on('agent/status', ({ agent, status }) => {
      this.#journal.append(agent.id, 'agent/status', { status })
    }, { global: true })
    this.#plugins = new NativePluginRegistry(ctx, {
      composed: specifier => this.#composition.inventory().entries
        .some(entry => entry.enabled && entry.moduleName === specifier),
    })
  }

  async proxyPluginUi(pluginId, path, request, response) {
    this.#assertStarted()
    await this.#nativePluginWeb.proxy(pluginId, path, request, response)
  }

  async proxyPluginUiUpgrade(pluginId, request, socket, head) {
    this.#assertStarted()
    await this.#nativePluginWeb.proxyUpgrade(pluginId, request, socket, head)
  }

  async createSession({
    sessionId, cwd, workspaceId, personalConversationKey, presetId = ASKAI_ENTERPRISE_PRESET_ID,
    permissionPreset, approvalReviewer, approvalPolicy, seed, parentSessionId,
  }) {
    this.#assertStarted()
    if (this.#handles.has(sessionId)) throw new Error(`session already live: ${sessionId}`)
    if (cwd !== undefined && workspaceId !== undefined) throw new Error('session cannot specify both cwd and workspaceId')
    if (personalConversationKey && process.env.MOVO_PERSONAL_SPACE_ROOT && workspaceId === undefined) {
      if (!validConversationSpaceKey(personalConversationKey)) throw new Error('invalid personal conversation key')
      cwd = join(process.env.MOVO_PERSONAL_SPACE_ROOT, 'conversations', personalConversationKey)
      await mkdir(cwd, { recursive: true })
      await chmod(cwd, 0o777)
    }
    const workspace = workspaceId === undefined
      ? undefined
      : (await this.#workspaces.get(workspaceId, { requireAvailable: true })).workspace
    const composition = await this.#sessionComposer.prepare(presetId, {
      hasWorkspace: workspace !== undefined || cwd !== undefined,
    })
    const lineage = sessionCreationLineage(seed, parentSessionId)
    const handle = await this.#ctx.agents.create({
      sessionId: SessionId(sessionId),
      meta: {
        ...(workspace === undefined && cwd === undefined ? {} : { cwd: workspace?.path ?? resolve(cwd) }),
        agentPreset: composition.presetId,
        ...lineage.meta,
      },
      ...lineage.options,
      agentOptions: this.#agentOptions(),
      setup: composition.setup,
    })
    this.#handles.set(sessionId, handle)
    try {
      if (presetId === 'code') {
        const policy = codePermissionPolicy({ permissionPreset, approvalReviewer, approvalPolicy })
        this.#ctx.permissionPresets.set(handle.agent.session, policy.permissionPreset)
        setApprovalPolicy(handle.agent.session, policy.approvalPolicy)
        this.#desktopApprovals.setReviewer(sessionId, policy.approvalReviewer)
      } else if (permissionPreset !== undefined) this.#ctx.permissionPresets.set(handle.agent.session, permissionPreset)
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
    return structuredClone(liveSessionEvents(agent.session))
  }

  async resumeSession(sessionId, cursorFloor = 0) {
    this.#assertStarted()
    if (!Number.isSafeInteger(cursorFloor) || cursorFloor < 0) throw new TypeError('invalid cursor floor')
    const live = this.#handles.get(sessionId)
    if (live !== undefined) {
      this.#journal.ensureCursorFloor(sessionId, cursorFloor)
      return await this.describeSession(live.agent)
    }
    const persisted = await this.#sessionComposer.persistedIdentity(sessionId)
    const composition = await this.#sessionComposer.prepare(persisted.presetId, {
      hasWorkspace: Boolean(persisted.cwd),
    })
    const handle = await this.#ctx.agents.resume({
      resumeSessionId: SessionId(sessionId),
      agentOptions: this.#agentOptions(),
      setup: composition.setup,
    })
    this.#handles.set(sessionId, handle)
    this.#journal.resetFromEvents(
      sessionId,
      persisted.events.flatMap(event => compatibleSessionEvents(event)),
    )
    this.#journal.ensureCursorFloor(sessionId, cursorFloor)
    this.#journal.append(sessionId, 'agent/status', { status: handle.agent.status })
    return await this.describeSession(handle.agent)
  }

  async send({ sessionId, mode, content, temporalContext, turnContext, permissionPreset, approvalReviewer, approvalPolicy }) {
    const agent = this.#requireAgent(sessionId)
    if (agent.session?.header?.agentPreset === 'code' && (permissionPreset !== undefined || approvalReviewer !== undefined || approvalPolicy !== undefined)) {
      const policy = codePermissionPolicy({ permissionPreset, approvalReviewer, approvalPolicy })
      this.#ctx.permissionPresets.set(agent.session, policy.permissionPreset)
      this.#ctx.approval.setPolicy(agent, policy.approvalPolicy)
      this.#desktopApprovals.setReviewer(sessionId, policy.approvalReviewer)
    }
    if (temporalContext === undefined || temporalContext === null) {
      throw new TypeError('temporalContext is required for every MOVO turn')
    }
    this.#temporalContext.update(sessionId, temporalContext)
    const resolvedTurnContext = resolveSkillTurnContext(this.modelProfile, turnContext)
    if (resolvedTurnContext.selectedSkill?.sourceScope === 'plugin') {
      const selected = resolvedTurnContext.selectedSkill
      const current = (await this.#ctx.skills.list({
        scope: scopeOf(agent.ctx),
        ...(agent.session.header.cwd ? { cwd: agent.session.header.cwd } : {}),
      })).find(item => item.name === resolvedTurnContext.skillName)
      if (!current || current.invocation?.userInvocable !== true ||
          current.provider !== selected.provider || current.source !== selected.source) {
        throw new Error('selected plugin Skill is not provided by the authorized plugin in this Session')
      }
    }
    this.#turnContext.update(sessionId, resolvedTurnContext.context)
    this.#modelAdapter?.setKnowledgeMode(sessionId, resolvedTurnContext.context?.knowledge_qa_enabled === true)
    const promptParts = content.map((block, index) => {
      if (block.type === 'text') {
        const text = String(block.data?.text ?? '')
        return { type: 'text', text: index === 0 ? invokeSelectedSkill(resolvedTurnContext.skillName, text) : text }
      }
      if (block.type === 'image') return {
        type: 'image', mediaType: String(block.data?.mediaType ?? ''),
        data: String(block.data?.data ?? ''), name: String(block.data?.name ?? ''),
      }
      throw new Error(`this Runtime Profile does not accept ${block.type} content`)
    })
    const admitted = promptParts.some(block => block.type === 'image')
      ? await this.#ctx.get('attachments').admitPromptContent(promptParts)
      : promptParts
    this.#skillInvocations.expectManual(sessionId, resolvedTurnContext.skillName)
    const message = createUserMessage({
      content: admitted,
      source: { kind: 'user' },
    })
    try {
      if (mode === 'steer') agent.steer(message)
      else agent.followup(message)
    } catch (error) {
      this.#skillInvocations.clear(sessionId)
      throw error
    }
    return { accepted: true, messageId: message.id }
  }

  async executePluginCommand(sessionId, selectedId, line) {
    const agent = this.#requireAgent(sessionId)
    const selected = resolvePluginCommand(this.modelProfile, selectedId, line)
    const commands = this.#ctx.get('commands')
    if (!commands) throw new Error('DSH command registry is unavailable')
    requireCurrentCommand(commands, agent, selected)
    await agent.whenIdle()
    const execution = await commands.execute(agent, line, [], AbortSignal.timeout(120_000))
    if (!execution) throw new Error('selected plugin command did not resolve in this Session')
    let idleTimer
    try {
      await Promise.race([
        agent.whenIdle(),
        new Promise((_, reject) => {
          idleTimer = setTimeout(() => reject(new Error('selected plugin command did not become idle')), 120_000)
          idleTimer.unref?.()
        }),
      ])
    } finally {
      clearTimeout(idleTimer)
    }
    return { commandId: execution.commandId, result: execution.result }
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

  pendingQuestions(sessionId) {
    this.#requireAgent(sessionId)
    return this.#userQuestions.list(sessionId)
  }

  answerQuestion(sessionId, questionId, answers) {
    this.#requireAgent(sessionId)
    return this.#userQuestions.answer(sessionId, questionId, answers)
  }

  events(sessionId, afterCursor) {
    this.#requireAgent(sessionId)
    return this.#journal.replay(sessionId, afterCursor)
  }

  headCursor(sessionId) {
    this.#requireAgent(sessionId)
    return this.#journal.head(sessionId)
  }

  subscribeEvents(sessionId, afterCursor, subscriber) {
    this.#requireAgent(sessionId)
    return this.#journal.subscribe(sessionId, afterCursor, subscriber)
  }

  refreshModelCredential(credential) {
    if (this.#modelAdapter === undefined) throw new Error('runtime does not use MOVO Model Gateway')
    this.#modelAdapter.updateCredential(credential)
    this.#skillProvider?.materializer?.updateCredential(credential.accessToken)
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
      presetId: normalizePersistedPreset(agent.session.header.agentPreset),
      seedLength: inheritedEventCount(agent.session),
      workspaceId: workspace === undefined ? null : String(workspace.id),
      permissionPreset: currentPermissionPreset(this.#ctx.permissionPresets, agent.session),
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
    this.#modelAdapter?.clearKnowledgeMode(sessionId)
    this.#desktopApprovals.clearSession(sessionId)
    this.#userQuestions.clearSession(sessionId)
    await handle.agent.whenIdle()
    await handle.dispose()
    this.#liveAssistantStream.remove(sessionId)
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

  async managedPluginList() {
    return {
      ...(await this.#managedPlugins.list()),
      dshVersion: this.#composition.inventory().dshVersion,
      globalTools: this.#ctx.tools.schemas().map(tool => tool.name),
      ...(await globalPluginCapabilities(this.#ctx)),
    }
  }

  async managedSessionCapabilities(sessionId) {
    return await sessionPluginCapabilities(this.#ctx, this.#requireAgent(sessionId))
  }
  managedPluginInspect(spec, registry) { return this.#managedPlugins.inspect(spec, registry) }
  managedPluginManifest(name) { return this.#managedPlugins.manifest(name) }
  managedPluginInstall(spec, options) { return this.#managedPlugins.install(spec, options) }
  managedPluginEnable(name, enabled) { return this.#managedPlugins.enable(name, enabled) }
  managedPluginRemove(name) { return this.#managedPlugins.remove(name) }

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
      this.#liveAssistantStream.remove(sessionId)
    }
    this.#modelAdapterDispose?.()
    this.#desktopApprovals?.dispose()
    this.#userQuestions?.dispose()
    this.#toolBridge?.dispose()
    this.#webSearchDispose?.()
    this.#skillResourceToolDispose?.()
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
