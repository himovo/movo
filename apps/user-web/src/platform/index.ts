// Platform adapter: one API surface; picks Electron or web at runtime.

import type { AgentStatus, BrowserBounds, BrowserOwner, BrowserPreviewFrame, BrowserPurpose, DesktopUpdateState, DshCodeSession, DshDirectoryEntry, DshExecutionEvent, DshFileDiff, DshFilePreview, DshGitBranchSnapshot, DshGitCommitResult, DshGitPushResult, DshPendingApproval, DshTaskChangeSet, DshTaskFileDiff, DshTerminalEvent, DshWorkspace, DshWorkspaceInspection, DshWorkspaceSummary, EmbeddedBrowserState, EnterpriseConnectionResult, PlatformCapabilities, SaveResult, Settings } from './types'
import * as web from './web'

if (import.meta.env.DEV && new URLSearchParams(globalThis.location?.search || '').has('desktop-ui-contract')) {
  const { installDesktopUiTestHarness } = await import('./desktopUiTestHarness')
  installDesktopUiTestHarness()
}

let impl: typeof web = web

function runningInElectron(): boolean {
  return typeof (globalThis as any)?.__ASKAI_ELECTRON__ !== 'undefined'
}

// Dynamically load the desktop implementation in Electron.
// Top-level await keeps consumers synchronous after module init.
if (runningInElectron()) {
  try {
    impl = (await import('./electron')) as unknown as typeof web
  } catch (err) {
    console.warn('[platform] Electron impl failed to load; falling back to web', err)
  }
}

export const capabilities: PlatformCapabilities = impl.capabilities
export const getSettings: () => Promise<Settings> = impl.getSettings
export const updateSettings: (next: Settings) => Promise<Settings> = impl.updateSettings
export const connectEnterpriseServer: (address: string) => Promise<EnterpriseConnectionResult> = impl.connectEnterpriseServer
export const getAgentStatus: () => Promise<AgentStatus> = impl.getAgentStatus
export const startAgent: () => Promise<AgentStatus> = impl.startAgent
export const stopAgent: () => Promise<AgentStatus> = impl.stopAgent
export const restartAgent: () => Promise<AgentStatus> = impl.restartAgent
export const getDesktopUpdateState: () => Promise<DesktopUpdateState> = impl.getDesktopUpdateState
export const checkDesktopUpdate: () => Promise<DesktopUpdateState> = impl.checkDesktopUpdate
export const downloadDesktopUpdate: () => Promise<DesktopUpdateState> = impl.downloadDesktopUpdate
export const installDesktopUpdate: () => Promise<{ installing: boolean }> = impl.installDesktopUpdate
export const onDesktopUpdateState: (listener: (state: DesktopUpdateState) => void) => () => void = impl.onDesktopUpdateState
export const listDshWorkspaces: (modelId?: string) => Promise<DshWorkspace[]> = impl.listDshWorkspaces
export const selectDshWorkspace: (modelId?: string) => Promise<DshWorkspace | null> = impl.selectDshWorkspace
export const renameDshWorkspace: (workspaceId: string, title: string, modelId?: string) => Promise<DshWorkspace> = impl.renameDshWorkspace
export const deleteDshWorkspace: (workspaceId: string, modelId?: string) => Promise<boolean> = impl.deleteDshWorkspace
export const listDshWorkspaceBranches: (workspaceId: string, modelId?: string) => Promise<DshGitBranchSnapshot> = impl.listDshWorkspaceBranches
export const switchDshWorkspaceBranch: (workspaceId: string, fullRef: string, modelId?: string) => Promise<DshGitBranchSnapshot> = impl.switchDshWorkspaceBranch
export const createDshWorkspaceBranch: (workspaceId: string, name: string, sourceRef?: string, modelId?: string) => Promise<DshGitBranchSnapshot> = impl.createDshWorkspaceBranch
export const createDshCodeSession: (workspaceId: string, draftId: string, title: string, modelId?: string, useWorktree?: boolean, sourceRef?: string) => Promise<DshCodeSession> = impl.createDshCodeSession
export const sendDshCodeTurn: (sessionId: string, text: string) => Promise<{ accepted: boolean; messageId: string }> = impl.sendDshCodeTurn
export const attachDshCodeConversation: (conversationId: string) => Promise<DshCodeSession | null> = impl.attachDshCodeConversation
export const cancelDshCodeTurn: (sessionId: string) => Promise<{ cancelled: boolean; jobsPending: boolean }> = impl.cancelDshCodeTurn
export const subscribeDshCodeEvents: (sessionId: string, after?: number) => Promise<{ subscribed: boolean }> = impl.subscribeDshCodeEvents
export const unsubscribeDshCodeEvents: (sessionId: string) => Promise<{ unsubscribed: boolean }> = impl.unsubscribeDshCodeEvents
export const onDshCodeEvent: (listener: (sessionId: string, event: DshExecutionEvent) => void) => () => void = impl.onDshCodeEvent
export const listDshCodeApprovals: (sessionId: string) => Promise<DshPendingApproval[]> = impl.listDshCodeApprovals
export const inspectDshCodeWorkspace: (sessionId: string) => Promise<DshWorkspaceInspection> = impl.inspectDshCodeWorkspace
export const getDshWorkspaceSummary: (sessionId: string) => Promise<DshWorkspaceSummary> = impl.getDshWorkspaceSummary
export const listDshWorkspaceDirectory: (sessionId: string, path?: string) => Promise<DshDirectoryEntry[]> = impl.listDshWorkspaceDirectory
export const previewDshWorkspaceFile: (sessionId: string, path: string) => Promise<DshFilePreview> = impl.previewDshWorkspaceFile
export const getDshWorkspaceFileDiff: (sessionId: string, path: string) => Promise<DshFileDiff> = impl.getDshWorkspaceFileDiff
export const commitDshWorkspaceChanges: (sessionId: string, message: string, push?: boolean, branchName?: string) => Promise<DshGitCommitResult> = impl.commitDshWorkspaceChanges
export const pushDshWorkspaceChanges: (sessionId: string, expectedCommitHash?: string) => Promise<DshGitPushResult> = impl.pushDshWorkspaceChanges
export const getLatestDshTaskChanges: (sessionId: string) => Promise<DshTaskChangeSet | null> = impl.getLatestDshTaskChanges
export const undoDshTaskChanges: (sessionId: string, taskId: string) => Promise<DshTaskChangeSet> = impl.undoDshTaskChanges
export const getDshTaskFileDiff: (sessionId: string, taskId: string, path: string) => Promise<DshTaskFileDiff> = impl.getDshTaskFileDiff
export const createDshProjectTerminal: (sessionId: string, cols?: number, rows?: number) => Promise<{ terminal_id: string }> = impl.createDshProjectTerminal
export const writeDshProjectTerminal: (terminalId: string, data: string) => Promise<{ written: boolean }> = impl.writeDshProjectTerminal
export const resizeDshProjectTerminal: (terminalId: string, cols: number, rows: number) => Promise<{ resized: boolean }> = impl.resizeDshProjectTerminal
export const closeDshProjectTerminal: (terminalId: string) => Promise<{ closed: boolean }> = impl.closeDshProjectTerminal
export const onDshProjectTerminalEvent: (listener: (event: DshTerminalEvent) => void) => () => void = impl.onDshProjectTerminalEvent
export const decideDshCodeApproval: (sessionId: string, approvalId: string, decision: 'approved' | 'rejected', grantScope: 'once' | 'session') => Promise<{ decided: boolean }> = impl.decideDshCodeApproval
export const getEmbeddedBrowserState: () => Promise<EmbeddedBrowserState> = impl.getEmbeddedBrowserState
export const captureEmbeddedBrowserPreview: (sessionId: string) => Promise<BrowserPreviewFrame | null> = impl.captureEmbeddedBrowserPreview
export const selectEmbeddedBrowserSession: (sessionId: string) => Promise<void> = impl.selectEmbeddedBrowserSession
export const activateEmbeddedBrowserSession: (sessionId: string) => Promise<void> = impl.activateEmbeddedBrowserSession
export const attachEmbeddedBrowserSurface: (surfaceId: string, sessionId: string) => Promise<void> = impl.attachEmbeddedBrowserSurface
export const showEmbeddedBrowserSurface: (surfaceId: string) => Promise<void> = impl.showEmbeddedBrowserSurface
export const hideEmbeddedBrowserSurface: (surfaceId: string) => Promise<void> = impl.hideEmbeddedBrowserSurface
export const setEmbeddedBrowserSurfaceBounds: (surfaceId: string, bounds: BrowserBounds) => Promise<void> = impl.setEmbeddedBrowserSurfaceBounds
export const showEmbeddedBrowser: () => Promise<void> = impl.showEmbeddedBrowser
export const hideEmbeddedBrowser: () => Promise<void> = impl.hideEmbeddedBrowser
export const setEmbeddedBrowserBounds: (bounds: BrowserBounds) => Promise<void> = impl.setEmbeddedBrowserBounds
export const openEmbeddedBrowser: (url: string, purpose: BrowserPurpose) => Promise<void> = impl.openEmbeddedBrowser
export const navigateEmbeddedBrowserHistory: (direction: 'back' | 'forward') => Promise<void> = impl.navigateEmbeddedBrowserHistory
export const reloadEmbeddedBrowser: () => Promise<void> = impl.reloadEmbeddedBrowser
export const createEmbeddedBrowserTab: (url?: string) => Promise<void> = impl.createEmbeddedBrowserTab
export const selectEmbeddedBrowserTab: (tabId: string) => Promise<void> = impl.selectEmbeddedBrowserTab
export const closeEmbeddedBrowserTab: (tabId: string) => Promise<void> = impl.closeEmbeddedBrowserTab
export const setEmbeddedBrowserOwner: (owner: BrowserOwner) => Promise<void> = impl.setEmbeddedBrowserOwner
export const onEmbeddedBrowserState: (listener: (state: EmbeddedBrowserState) => void) => () => void = impl.onEmbeddedBrowserState
export const onEmbeddedBrowserLayoutRequest: (listener: () => void) => () => void = impl.onEmbeddedBrowserLayoutRequest
export const openResource: (url: string, purpose?: BrowserPurpose | 'external') => Promise<void> = impl.openResource
export const saveBytes: (filename: string, bytes: Uint8Array) => Promise<SaveResult> = impl.saveBytes

export type { AgentStatus, BrowserBounds, BrowserOwner, BrowserPreviewFrame, BrowserPurpose, DesktopUpdatePhase, DesktopUpdateState, DshCodeSession, DshDirectoryEntry, DshExecutionEvent, DshFileDiff, DshFilePreview, DshGitBranchRef, DshGitBranchSnapshot, DshGitCommitResult, DshGitPushResult, DshPendingApproval, DshTaskChangeSet, DshTaskFileDiff, DshTerminalEvent, DshWorkspace, DshWorkspaceInspection, DshWorkspaceSummary, EmbeddedBrowserState, EnterpriseConnectionResult, PlatformCapabilities, SaveResult, Settings } from './types'
