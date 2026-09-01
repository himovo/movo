// Shared types for the platform adapter layer.

export interface AgentStatus {
  running: boolean
  ws_url: string
  user_id: string
  local_control_url: string
  local_control_token: string
}

export interface Settings {
  service_url: string
  server_configured: boolean
  backend_url: string
  agent_ws_url: string
  user_id: string
  auth_token: string
  auto_start_agent: boolean
  language: 'zh' | 'en'
  timezone: string
}

export interface EnterpriseConnectionResult {
  settings: Settings
  org_name: string
  main_id: string
  services_ready: boolean
}

export interface PlatformCapabilities {
  /** True inside the Electron desktop shell. */
  isDesktop: boolean
  /** Local agent can be started / stopped from the UI. */
  localAgentControl: boolean
  /** Settings (backendUrl, auth) are persisted by the shell. */
  localSettings: boolean
  /** The shell can host a real Chromium page beside the Vue UI. */
  embeddedBrowser: boolean
  /** The shell provides native save dialogs for generated files. */
  managedDownloads: boolean
  /** A secured DSH Runtime Host is owned by the desktop main process. */
  localDshRuntime: boolean
  /** Native directory selection and DSH Workspace registration are available. */
  localWorkspacePicker: boolean
  /** The platform may execute the official DSH code preset. */
  codeExecution: boolean
  /** The platform can render local deterministic Code inspection state. */
  codeInspector: boolean
  /** The platform can browse and preview files from the bound Code Workspace. */
  workspaceFiles: boolean
  /** The platform can inspect Git changes for the bound Code Workspace. */
  workspaceChanges: boolean
  /** The platform can host a real interactive project terminal. */
  projectTerminal: boolean
}

export interface DshWorkspace {
  workspace_id: string
  title: string
  path: string
  status: 'ok' | 'missing-dir'
  session_ids: string[]
  created_at: string
  updated_at: string
  /** Best-effort Git branch detected from the local project directory. */
  git_branch?: string
}

export interface DshGitBranchRef {
  name: string
  full_ref: string
  kind: 'local' | 'remote'
  commit: string
  current: boolean
}

export interface DshGitBranchSnapshot {
  current_branch: string
  head_commit: string
  detached: boolean
  dirty: boolean
  branches: DshGitBranchRef[]
}

export interface DshCodeSession {
  runtime_id: string
  kernel_session_id: string
  dsh_workspace_id: string
  preset_id: 'code'
  profile_version: string
  model_instance_id: string
  conversation_id: string
  binding_id: string
  source_workspace_id: string
  git_branch?: string
  source_ref?: string
  base_commit?: string
  detached_head?: boolean
  execution_mode?: 'local' | 'worktree'
  worktree: boolean
}

export interface DshExecutionEvent {
  v: 3
  event_id: string
  id: string
  ts: number
  type: 'run.started' | 'run.completed' | 'run.failed' | 'run.cancelled'
    | 'item.started' | 'item.updated' | 'item.delta' | 'item.completed' | 'item.failed'
  item_kind?: 'commentary' | 'final_answer' | 'tool' | 'approval' | 'activity' | 'error'
  item_id?: string
  revision: number
  stream_seq: number
  stream_seq_end: number
  payload: Record<string, any>
}

export interface DshPendingApproval {
  approval_id: string
  session_id: string
  tool_name: string
  call_id: string
  reason: string
  created_at: number
}

export interface DshWorkspaceInspection {
  generated_at: number
  branch: string
  files: Array<{ path: string; kind: 'file' | 'directory'; depth: number }>
  changes: Array<{ path: string; status: string; additions: number | null; deletions: number | null; binary: boolean }>
  diff: string
  diff_truncated: boolean
  git_available: boolean
}

export interface DshWorkspaceSummary {
  generated_at: number
  branch: string
  changes: Array<{ path: string; status: string; additions: number | null; deletions: number | null; binary: boolean }>
  git_available: boolean
  head_commit: string
  upstream: string
  ahead: number | null
  behind: number | null
  remote_names: string[]
}

export interface DshGitPushResult {
  commit_hash: string
  branch: string
  remote: string
  upstream: string
}

export interface DshGitCommitResult {
  commit_hash: string
  short_hash: string
  branch: string
  message: string
  changed_files: number
  push?: DshGitPushResult
  push_error?: string
}

export interface DshTaskFileChange {
  path: string
  status: string
  additions: number | null
  deletions: number | null
  binary: boolean
}

export interface DshTaskChangeSet {
  task_id: string
  session_id: string
  created_at: number
  files: DshTaskFileChange[]
  additions: number
  deletions: number
  undo_available: boolean
  undone: boolean
}

export interface DshTaskFileDiff { path: string; diff: string; binary: boolean }

export interface DshDirectoryEntry { name: string; path: string; kind: 'file' | 'directory'; size: number | null }
export interface DshFilePreview {
  path: string; name: string; kind: 'text' | 'image' | 'binary'; language: string
  content: string; mime_type: string; size: number; truncated: boolean
}
export interface DshFileDiff { path: string; diff: string; truncated: boolean; binary: boolean }
export interface DshTerminalEvent {
  terminal_id: string; session_id: string; type: 'data' | 'exit'; data?: string; exit_code?: number
}

export type BrowserPurpose = 'automation' | 'internal' | 'preview'
export type BrowserOwner = 'agent' | 'human'

export interface BrowserBounds { x: number; y: number; width: number; height: number }
export interface BrowserTabState { id: string; url: string; title: string; loading: boolean }
export interface EmbeddedBrowserState {
  session_id: string
  active: boolean
  visible: boolean
  purpose: BrowserPurpose
  owner: BrowserOwner
  url: string
  title: string
  loading: boolean
  canGoBack: boolean
  canGoForward: boolean
  controllable: boolean
  active_tab_id: string
  tabs: BrowserTabState[]
}

export interface SaveResult { saved: boolean; path?: string }
