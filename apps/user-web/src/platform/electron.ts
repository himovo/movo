import type { AgentStatus, BrowserBounds, BrowserOwner, BrowserPurpose, DshCodeSession, DshDirectoryEntry, DshExecutionEvent, DshFileDiff, DshFilePreview, DshGitBranchSnapshot, DshGitCommitResult, DshGitPushResult, DshPendingApproval, DshTaskChangeSet, DshTaskFileDiff, DshTerminalEvent, DshWorkspace, DshWorkspaceInspection, DshWorkspaceSummary, EmbeddedBrowserState, EnterpriseConnectionResult, PlatformCapabilities, SaveResult, Settings } from './types'

interface ElectronApi {
  settings: { get(): Promise<Settings>; update(next: Settings): Promise<Settings> }
  enterprise: { connect(address: string): Promise<EnterpriseConnectionResult> }
  agent: { status(): Promise<AgentStatus>; start(): Promise<AgentStatus>; stop(): Promise<AgentStatus>; restart(): Promise<AgentStatus> }
  dshWorkspace: {
    list(modelId?: string): Promise<DshWorkspace[]>
    select(modelId?: string): Promise<DshWorkspace | null>
    rename(workspaceId: string, title: string, modelId?: string): Promise<DshWorkspace>
    delete(workspaceId: string, modelId?: string): Promise<boolean>
    branches(workspaceId: string, modelId?: string): Promise<DshGitBranchSnapshot>
    switchBranch(workspaceId: string, fullRef: string, modelId?: string): Promise<DshGitBranchSnapshot>
    createBranch(workspaceId: string, name: string, sourceRef?: string, modelId?: string): Promise<DshGitBranchSnapshot>
    createCodeSession(workspaceId: string, draftId: string, title: string, modelId?: string, useWorktree?: boolean, sourceRef?: string): Promise<DshCodeSession>
  }
  dshCodeSession: {
    attach(conversationId: string): Promise<DshCodeSession | null>
    send(sessionId: string, text: string): Promise<{ accepted: boolean; messageId: string }>
    cancel(sessionId: string): Promise<{ cancelled: boolean; jobsPending: boolean }>
    subscribe(sessionId: string, after?: number): Promise<{ subscribed: boolean }>
    unsubscribe(sessionId: string): Promise<{ unsubscribed: boolean }>
    onEvent(listener: (sessionId: string, event: DshExecutionEvent) => void): () => void
    approvals(sessionId: string): Promise<DshPendingApproval[]>
    inspect(sessionId: string): Promise<DshWorkspaceInspection>
    summary(sessionId: string): Promise<DshWorkspaceSummary>
    listDirectory(sessionId: string, path?: string): Promise<DshDirectoryEntry[]>
    previewFile(sessionId: string, path: string): Promise<DshFilePreview>
    fileDiff(sessionId: string, path: string): Promise<DshFileDiff>
    commit(sessionId: string, message: string, push?: boolean, branchName?: string): Promise<DshGitCommitResult>
    push(sessionId: string, expectedCommitHash?: string): Promise<DshGitPushResult>
    latestTaskChanges(sessionId: string): Promise<DshTaskChangeSet | null>
    undoTaskChanges(sessionId: string, taskId: string): Promise<DshTaskChangeSet>
    taskFileDiff(sessionId: string, taskId: string, path: string): Promise<DshTaskFileDiff>
    createTerminal(sessionId: string, cols?: number, rows?: number): Promise<{ terminal_id: string }>
    writeTerminal(terminalId: string, data: string): Promise<{ written: boolean }>
    resizeTerminal(terminalId: string, cols: number, rows: number): Promise<{ resized: boolean }>
    closeTerminal(terminalId: string): Promise<{ closed: boolean }>
    onTerminalEvent(listener: (event: DshTerminalEvent) => void): () => void
    decideApproval(sessionId: string, approvalId: string, decision: 'approved' | 'rejected', grantScope: 'once' | 'session'): Promise<{ decided: boolean }>
  }
  browser: {
    state(): Promise<EmbeddedBrowserState>
    selectSession(sessionId: string): Promise<void>
    activateSession(sessionId: string): Promise<void>
    attachSurface(surfaceId: string, sessionId: string): Promise<void>
    showSurface(surfaceId: string): Promise<void>
    hideSurface(surfaceId: string): Promise<void>
    setSurfaceBounds(surfaceId: string, bounds: BrowserBounds): Promise<void>
    show(): Promise<void>
    hide(): Promise<void>
    setBounds(bounds: BrowserBounds): Promise<void>
    open(url: string, purpose: BrowserPurpose): Promise<void>
    history(direction: 'back' | 'forward'): Promise<void>
    reload(): Promise<void>
    newTab(url?: string): Promise<void>
    selectTab(tabId: string): Promise<void>
    closeTab(tabId: string): Promise<void>
    setOwner(owner: BrowserOwner): Promise<void>
    onState(listener: (state: EmbeddedBrowserState) => void): () => void
    onLayoutRequest(listener: () => void): () => void
  }
  resources: {
    open(url: string, purpose?: BrowserPurpose | 'external'): Promise<void>
    saveBytes(filename: string, bytes: Uint8Array): Promise<SaveResult>
  }
}

function api(): ElectronApi {
  const value = (globalThis as any).__ASKAI_ELECTRON__ as ElectronApi | undefined
  if (!value) throw new Error('Electron desktop bridge is unavailable')
  return value
}

export const capabilities: PlatformCapabilities = {
  isDesktop: true,
  localAgentControl: true,
  localSettings: true,
  embeddedBrowser: true,
  managedDownloads: true,
  localDshRuntime: true,
  localWorkspacePicker: true,
  codeExecution: true,
  codeInspector: true,
  workspaceFiles: true,
  workspaceChanges: true,
  projectTerminal: true,
}

export const getSettings = () => api().settings.get()
export const updateSettings = (next: Settings) => api().settings.update(next)
export const connectEnterpriseServer = (address: string) => api().enterprise.connect(address)
export const getAgentStatus = () => api().agent.status()
export const startAgent = () => api().agent.start()
export const stopAgent = () => api().agent.stop()
export const restartAgent = () => api().agent.restart()
export const listDshWorkspaces = (modelId?: string) => api().dshWorkspace.list(modelId)
export const selectDshWorkspace = (modelId?: string) => api().dshWorkspace.select(modelId)
export const renameDshWorkspace = (workspaceId: string, title: string, modelId?: string) =>
  api().dshWorkspace.rename(workspaceId, title, modelId)
export const deleteDshWorkspace = (workspaceId: string, modelId?: string) => api().dshWorkspace.delete(workspaceId, modelId)
export const listDshWorkspaceBranches = (workspaceId: string, modelId?: string) => api().dshWorkspace.branches(workspaceId, modelId)
export const switchDshWorkspaceBranch = (workspaceId: string, fullRef: string, modelId?: string) => api().dshWorkspace.switchBranch(workspaceId, fullRef, modelId)
export const createDshWorkspaceBranch = (workspaceId: string, name: string, sourceRef = 'HEAD', modelId?: string) => api().dshWorkspace.createBranch(workspaceId, name, sourceRef, modelId)
export const createDshCodeSession = (workspaceId: string, draftId: string, title: string, modelId?: string, useWorktree?: boolean, sourceRef?: string) =>
  api().dshWorkspace.createCodeSession(workspaceId, draftId, title, modelId, useWorktree, sourceRef)
export const sendDshCodeTurn = (sessionId: string, text: string) => api().dshCodeSession.send(sessionId, text)
export const attachDshCodeConversation = (conversationId: string) => api().dshCodeSession.attach(conversationId)
export const cancelDshCodeTurn = (sessionId: string) => api().dshCodeSession.cancel(sessionId)
export const subscribeDshCodeEvents = (sessionId: string, after?: number) => api().dshCodeSession.subscribe(sessionId, after)
export const unsubscribeDshCodeEvents = (sessionId: string) => api().dshCodeSession.unsubscribe(sessionId)
export const onDshCodeEvent = (listener: (sessionId: string, event: DshExecutionEvent) => void) => api().dshCodeSession.onEvent(listener)
export const listDshCodeApprovals = (sessionId: string) => api().dshCodeSession.approvals(sessionId)
export const inspectDshCodeWorkspace = (sessionId: string) => api().dshCodeSession.inspect(sessionId)
export const getDshWorkspaceSummary = (sessionId: string) => api().dshCodeSession.summary(sessionId)
export const listDshWorkspaceDirectory = (sessionId: string, path = '') => api().dshCodeSession.listDirectory(sessionId, path)
export const previewDshWorkspaceFile = (sessionId: string, path: string) => api().dshCodeSession.previewFile(sessionId, path)
export const getDshWorkspaceFileDiff = (sessionId: string, path: string) => api().dshCodeSession.fileDiff(sessionId, path)
export const commitDshWorkspaceChanges = (sessionId: string, message: string, push = false, branchName?: string) => api().dshCodeSession.commit(sessionId, message, push, branchName)
export const pushDshWorkspaceChanges = (sessionId: string, expectedCommitHash?: string) => api().dshCodeSession.push(sessionId, expectedCommitHash)
export const getLatestDshTaskChanges = (sessionId: string) => api().dshCodeSession.latestTaskChanges(sessionId)
export const undoDshTaskChanges = (sessionId: string, taskId: string) => api().dshCodeSession.undoTaskChanges(sessionId, taskId)
export const getDshTaskFileDiff = (sessionId: string, taskId: string, path: string) => api().dshCodeSession.taskFileDiff(sessionId, taskId, path)
export const createDshProjectTerminal = (sessionId: string, cols?: number, rows?: number) => api().dshCodeSession.createTerminal(sessionId, cols, rows)
export const writeDshProjectTerminal = (terminalId: string, data: string) => api().dshCodeSession.writeTerminal(terminalId, data)
export const resizeDshProjectTerminal = (terminalId: string, cols: number, rows: number) => api().dshCodeSession.resizeTerminal(terminalId, cols, rows)
export const closeDshProjectTerminal = (terminalId: string) => api().dshCodeSession.closeTerminal(terminalId)
export const onDshProjectTerminalEvent = (listener: (event: DshTerminalEvent) => void) => api().dshCodeSession.onTerminalEvent(listener)
export const decideDshCodeApproval = (sessionId: string, approvalId: string, decision: 'approved' | 'rejected', grantScope: 'once' | 'session') =>
  api().dshCodeSession.decideApproval(sessionId, approvalId, decision, grantScope)
export const getEmbeddedBrowserState = () => api().browser.state()
export const selectEmbeddedBrowserSession = (sessionId: string) => api().browser.selectSession(sessionId)
export const activateEmbeddedBrowserSession = (sessionId: string) => api().browser.activateSession(sessionId)
export const attachEmbeddedBrowserSurface = (surfaceId: string, sessionId: string) => api().browser.attachSurface(surfaceId, sessionId)
export const showEmbeddedBrowserSurface = (surfaceId: string) => api().browser.showSurface(surfaceId)
export const hideEmbeddedBrowserSurface = (surfaceId: string) => api().browser.hideSurface(surfaceId)
export const setEmbeddedBrowserSurfaceBounds = (surfaceId: string, bounds: BrowserBounds) =>
  api().browser.setSurfaceBounds(surfaceId, bounds)
export const showEmbeddedBrowser = () => api().browser.show()
export const hideEmbeddedBrowser = () => api().browser.hide()
export const setEmbeddedBrowserBounds = (bounds: BrowserBounds) => api().browser.setBounds(bounds)
export const openEmbeddedBrowser = (url: string, purpose: BrowserPurpose) => api().browser.open(url, purpose)
export const navigateEmbeddedBrowserHistory = (direction: 'back' | 'forward') => api().browser.history(direction)
export const reloadEmbeddedBrowser = () => api().browser.reload()
export const createEmbeddedBrowserTab = (url?: string) => api().browser.newTab(url)
export const selectEmbeddedBrowserTab = (tabId: string) => api().browser.selectTab(tabId)
export const closeEmbeddedBrowserTab = (tabId: string) => api().browser.closeTab(tabId)
export const setEmbeddedBrowserOwner = (owner: BrowserOwner) => api().browser.setOwner(owner)
export const onEmbeddedBrowserState = (listener: (state: EmbeddedBrowserState) => void) => api().browser.onState(listener)
export const onEmbeddedBrowserLayoutRequest = (listener: () => void) => api().browser.onLayoutRequest(listener)
export const openResource = (url: string, purpose?: BrowserPurpose | 'external') => api().resources.open(url, purpose)
export const saveBytes = (filename: string, bytes: Uint8Array) => api().resources.saveBytes(filename, bytes)
