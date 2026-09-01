// Web implementation of the platform adapter.
// Desktop-only features are stubbed or proxied to localStorage.

import type { AgentStatus, BrowserBounds, BrowserOwner, BrowserPurpose, DshCodeSession, DshDirectoryEntry, DshExecutionEvent, DshFileDiff, DshFilePreview, DshGitCommitResult, DshGitPushResult, DshPendingApproval, DshTaskChangeSet, DshTaskFileDiff, DshTerminalEvent, DshWorkspace, DshWorkspaceInspection, DshWorkspaceSummary, EmbeddedBrowserState, EnterpriseConnectionResult, PlatformCapabilities, SaveResult, Settings } from './types'
import { detectSystemLocale } from '../composables/i18n'
import { getBrowserTimezone } from '../composables/appTimezone'

const LS_KEY = 'askai.settings'

const DEFAULTS: Settings = {
  service_url: '',
  server_configured: true,
  backend_url: '',            // empty → use the page's own origin for API calls
  agent_ws_url: '',
  user_id: '',
  auth_token: '',
  auto_start_agent: false,
  language: detectSystemLocale(),
  timezone: getBrowserTimezone(),
}

export async function connectEnterpriseServer(_address: string): Promise<EnterpriseConnectionResult> {
  throw new Error('Enterprise server binding is only available in the desktop app')
}

export const capabilities: PlatformCapabilities = {
  isDesktop: false,
  localAgentControl: false,
  localSettings: true,        // we still persist UI settings to localStorage
  embeddedBrowser: false,
  managedDownloads: false,
  localDshRuntime: false,
  localWorkspacePicker: false,
  codeExecution: false,
  codeInspector: false,
  workspaceFiles: false,
  workspaceChanges: false,
  projectTerminal: false,
}

export async function getSettings(): Promise<Settings> {
  try {
    const raw = localStorage.getItem(LS_KEY)
    if (!raw) return { ...DEFAULTS }
    return { ...DEFAULTS, ...JSON.parse(raw) }
  } catch { return { ...DEFAULTS } }
}

export async function updateSettings(next: Settings): Promise<Settings> {
  localStorage.setItem(LS_KEY, JSON.stringify(next))
  return next
}

// There is no local agent on the Web — always report "not running".
export async function getAgentStatus(): Promise<AgentStatus> {
  return { running: false, ws_url: '', user_id: '', local_control_url: '', local_control_token: '' }
}

export async function startAgent(): Promise<AgentStatus> {
  throw new Error('local agent is only available in the desktop app')
}
export async function stopAgent(): Promise<AgentStatus> {
  throw new Error('local agent is only available in the desktop app')
}
export async function restartAgent(): Promise<AgentStatus> {
  throw new Error('local agent is only available in the desktop app')
}
export async function listDshWorkspaces(_modelId?: string): Promise<DshWorkspace[]> { return [] }
export async function selectDshWorkspace(_modelId?: string): Promise<DshWorkspace | null> { throw new Error('local Workspace selection is only available in the desktop app') }
export async function renameDshWorkspace(_workspaceId: string, _title: string, _modelId?: string): Promise<DshWorkspace> { throw new Error('local Workspaces are only available in the desktop app') }
export async function deleteDshWorkspace(_workspaceId: string, _modelId?: string): Promise<boolean> { throw new Error('local Workspaces are only available in the desktop app') }
export async function listDshWorkspaceBranches(_workspaceId: string, _modelId?: string): Promise<import('./types').DshGitBranchSnapshot> { throw new Error('local Git branches are only available in the desktop app') }
export async function switchDshWorkspaceBranch(_workspaceId: string, _fullRef: string, _modelId?: string): Promise<import('./types').DshGitBranchSnapshot> { throw new Error('local Git branches are only available in the desktop app') }
export async function createDshWorkspaceBranch(_workspaceId: string, _name: string, _sourceRef = 'HEAD', _modelId?: string): Promise<import('./types').DshGitBranchSnapshot> { throw new Error('local Git branches are only available in the desktop app') }
export async function createDshCodeSession(_workspaceId: string, _draftId: string, _title: string, _modelId?: string, _useWorktree?: boolean, _sourceRef?: string): Promise<DshCodeSession> { throw new Error('local Code execution is only available in the desktop app') }
export async function sendDshCodeTurn(_sessionId: string, _text: string): Promise<{ accepted: boolean; messageId: string }> { throw new Error('local Code execution is only available in the desktop app') }
export async function attachDshCodeConversation(_conversationId: string): Promise<DshCodeSession | null> { return null }
export async function cancelDshCodeTurn(_sessionId: string): Promise<{ cancelled: boolean; jobsPending: boolean }> { throw new Error('local Code execution is only available in the desktop app') }
export async function subscribeDshCodeEvents(_sessionId: string, _after?: number): Promise<{ subscribed: boolean }> { throw new Error('local Code execution is only available in the desktop app') }
export async function unsubscribeDshCodeEvents(_sessionId: string) { return { unsubscribed: true } }
export function onDshCodeEvent(_listener: (sessionId: string, event: DshExecutionEvent) => void) { return () => {} }
export async function listDshCodeApprovals(_sessionId: string): Promise<DshPendingApproval[]> { return [] }
export async function inspectDshCodeWorkspace(_sessionId: string): Promise<DshWorkspaceInspection> { throw new Error('local Code inspection is only available in the desktop app') }
export async function getDshWorkspaceSummary(_sessionId: string): Promise<DshWorkspaceSummary> { throw new Error('local Code inspection is only available in the desktop app') }
export async function listDshWorkspaceDirectory(_sessionId: string, _path = ''): Promise<DshDirectoryEntry[]> { throw new Error('local Code files are only available in the desktop app') }
export async function previewDshWorkspaceFile(_sessionId: string, _path: string): Promise<DshFilePreview> { throw new Error('local Code files are only available in the desktop app') }
export async function getDshWorkspaceFileDiff(_sessionId: string, _path: string): Promise<DshFileDiff> { throw new Error('local Code changes are only available in the desktop app') }
export async function commitDshWorkspaceChanges(_sessionId: string, _message: string, _push = false, _branchName?: string): Promise<DshGitCommitResult> { throw new Error('local Git commit is only available in the desktop app') }
export async function pushDshWorkspaceChanges(_sessionId: string, _expectedCommitHash?: string): Promise<DshGitPushResult> { throw new Error('local Git push is only available in the desktop app') }
export async function getLatestDshTaskChanges(_sessionId: string): Promise<DshTaskChangeSet | null> { return null }
export async function undoDshTaskChanges(_sessionId: string, _taskId: string): Promise<DshTaskChangeSet> { throw new Error('local Code task undo is only available in the desktop app') }
export async function getDshTaskFileDiff(_sessionId: string, _taskId: string, _path: string): Promise<DshTaskFileDiff> { throw new Error('local Code task review is only available in the desktop app') }
export async function createDshProjectTerminal(_sessionId: string, _cols?: number, _rows?: number): Promise<{ terminal_id: string }> { throw new Error('local Code terminal is only available in the desktop app') }
export async function writeDshProjectTerminal(_terminalId: string, _data: string): Promise<{ written: boolean }> { throw new Error('local Code terminal is only available in the desktop app') }
export async function resizeDshProjectTerminal(_terminalId: string, _cols: number, _rows: number): Promise<{ resized: boolean }> { throw new Error('local Code terminal is only available in the desktop app') }
export async function closeDshProjectTerminal(_terminalId: string) { return { closed: true } }
export function onDshProjectTerminalEvent(_listener: (event: DshTerminalEvent) => void) { return () => {} }
export async function decideDshCodeApproval(_sessionId: string, _approvalId: string, _decision: 'approved' | 'rejected', _grantScope: 'once' | 'session'): Promise<{ decided: boolean }> { throw new Error('local Code approvals are only available in the desktop app') }

const EMPTY_BROWSER: EmbeddedBrowserState = {
  session_id: 'default',
  active: false, visible: false, purpose: 'automation', owner: 'agent', url: '', title: '',
  loading: false, canGoBack: false, canGoForward: false, controllable: false,
  active_tab_id: '', tabs: [],
}
export async function getEmbeddedBrowserState() { return { ...EMPTY_BROWSER } }
export async function selectEmbeddedBrowserSession(_sessionId: string) {}
export async function activateEmbeddedBrowserSession(_sessionId: string) {}
export async function attachEmbeddedBrowserSurface(_surfaceId: string, _sessionId: string) {}
export async function showEmbeddedBrowserSurface(_surfaceId: string) {}
export async function hideEmbeddedBrowserSurface(_surfaceId: string) {}
export async function setEmbeddedBrowserSurfaceBounds(_surfaceId: string, _bounds: BrowserBounds) {}
export async function showEmbeddedBrowser() {}
export async function hideEmbeddedBrowser() {}
export async function setEmbeddedBrowserBounds(_bounds: BrowserBounds) {}
export async function openEmbeddedBrowser(_url: string, _purpose: BrowserPurpose) {}
export async function navigateEmbeddedBrowserHistory(_direction: 'back' | 'forward') {}
export async function reloadEmbeddedBrowser() {}
export async function createEmbeddedBrowserTab(_url?: string) {}
export async function selectEmbeddedBrowserTab(_tabId: string) {}
export async function closeEmbeddedBrowserTab(_tabId: string) {}
export async function setEmbeddedBrowserOwner(_owner: BrowserOwner) {}
export function onEmbeddedBrowserState(_listener: (state: EmbeddedBrowserState) => void) { return () => {} }
export function onEmbeddedBrowserLayoutRequest(_listener: () => void) { return () => {} }

export async function openResource(url: string, _purpose?: BrowserPurpose | 'external') {
  window.open(url, '_blank', 'noopener,noreferrer')
}

export async function saveBytes(filename: string, bytes: Uint8Array): Promise<SaveResult> {
  const blob = new Blob([bytes as BlobPart])
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = filename
  document.body.appendChild(anchor)
  anchor.click()
  anchor.remove()
  URL.revokeObjectURL(url)
  return { saved: true }
}
