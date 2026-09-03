import type { DshExecutionEvent, DshPendingApproval } from './types'

/** Browser-only visual contract harness. It is imported exclusively in Vite DEV mode. */
export function installDesktopUiTestHarness() {
  const listeners = new Set<(sessionId: string, event: DshExecutionEvent) => void>()
  let cursor = 0
  let pending: DshPendingApproval[] = []
  const sessionId = 'dsh-code-ui-contract'
  const emit = (type: DshExecutionEvent['type'], item_kind?: DshExecutionEvent['item_kind'], item_id?: string, payload: Record<string, any> = {}) => {
    cursor += 1
    const event = { v: 3 as const, event_id: `ui-${cursor}`, id: `ui-${cursor}`, ts: Date.now(), type, item_kind, item_id, revision: cursor, stream_seq: cursor, stream_seq_end: cursor, payload }
    for (const listener of listeners) listener(sessionId, event)
  }
  const workspace = { workspace_id: 'workspace-ui', title: 'scheduled-crawler · 875166d0-7d66-4aea-8575-0c4ba9e794dc', path: '/workspace/scheduled-crawler', status: 'ok', session_ids: [], created_at: new Date().toISOString(), updated_at: new Date().toISOString(), git_branch: 'main' }
  ;(globalThis as any).__ASKAI_ELECTRON__ = {
    settings: { get: async () => ({ service_url: 'http://localhost:3000', server_configured: true, backend_url: '', agent_ws_url: '', user_id: 'ui-user', auth_token: 'ui-token', auto_start_agent: false, language: 'zh', timezone: 'Asia/Shanghai' }), update: async (value: any) => value },
    enterprise: { connect: async (address: string) => ({ settings: { service_url: address, server_configured: true }, org_name: 'MOVO', main_id: 'ui', services_ready: true }) },
    agent: { status: async () => ({ running: false, ws_url: '', user_id: '', local_control_url: '', local_control_token: '' }), start: async () => ({}), stop: async () => ({}), restart: async () => ({}) },
    updates: { state: async () => ({ phase: 'not-available', current_version: '0.1.0' }), check: async () => ({ phase: 'not-available', current_version: '0.1.0' }), download: async () => ({ phase: 'downloaded', current_version: '0.1.0', available_version: '0.1.1', progress_percent: 100 }), install: async () => ({ installing: false }), onState: () => () => {} },
    dshWorkspace: {
      list: async () => [workspace], select: async () => workspace, rename: async () => workspace, delete: async () => true,
      branches: async () => ({ current_branch: 'main', head_commit: 'a'.repeat(40), detached: false, dirty: false, branches: [{ name: 'main', full_ref: 'refs/heads/main', kind: 'local', commit: 'a'.repeat(40), current: true }] }),
      switchBranch: async () => ({ current_branch: 'main', head_commit: 'a'.repeat(40), detached: false, dirty: false, branches: [{ name: 'main', full_ref: 'refs/heads/main', kind: 'local', commit: 'a'.repeat(40), current: true }] }),
      createBranch: async (_workspace: string, name: string) => ({ current_branch: name, head_commit: 'a'.repeat(40), detached: false, dirty: false, branches: [{ name, full_ref: `refs/heads/${name}`, kind: 'local', commit: 'a'.repeat(40), current: true }] }),
      createCodeSession: async () => ({ runtime_id: 'runtime-ui', kernel_session_id: sessionId, dsh_workspace_id: workspace.workspace_id, preset_id: 'code', profile_version: 'profile-ui', model_instance_id: 'model-ui', conversation_id: '66c000000000000000000001', binding_id: 'binding-ui', source_workspace_id: workspace.workspace_id, source_ref: 'refs/heads/main', base_commit: 'a'.repeat(40), detached_head: true, execution_mode: 'worktree', worktree: true }),
    },
    dshCodeSession: {
      attach: async () => null, subscribe: async () => ({ subscribed: true }), unsubscribe: async () => ({ unsubscribed: true }),
      onEvent: (listener: any) => { listeners.add(listener); return () => listeners.delete(listener) },
      send: async () => {
        queueMicrotask(() => {
          emit('run.started', undefined, undefined, { kernel: 'dsh', source: 'desktop' })
          emit('item.completed', 'commentary', 'commentary-1', { text: '我先检查相关实现和测试，再进行修改。', source: 'model' })
          emit('item.started', 'tool', 'bash-1', { name: 'bash', display_name: 'bash', code_dispatch: true, args: { command: 'npm test' } })
          emit('item.completed', 'tool', 'bash-1', { name: 'bash', display_name: 'bash', code_dispatch: true, args: { command: 'npm test' }, result_summary: '{"exitCode":1,"stderr":"one test failed"}' })
          pending = [{ approval_id: 'approval-ui', session_id: sessionId, tool_name: 'bash', call_id: 'bash-2', reason: '该命令需要扩大当前 Workspace 权限。', created_at: Date.now() }]
          emit('item.started', 'approval', 'approval-ui', { source: 'dsh-local', approval_id: 'approval-ui', tool_name: 'bash', display_name: 'bash', status: 'pending' })
        })
        return { accepted: true, messageId: 'message-ui' }
      },
      cancel: async () => ({ cancelled: true, jobsPending: false }), approvals: async () => pending,
      decideApproval: async (_session: string, approvalId: string) => {
        pending = pending.filter(item => item.approval_id !== approvalId)
        emit('item.completed', 'approval', approvalId, { outcome: 'allowed-once', status: 'decided' })
        emit('item.started', 'tool', 'edit-1', { name: 'edit', display_name: 'edit', code_dispatch: true, args: { file_path: 'src/app.ts' } })
        emit('item.completed', 'tool', 'edit-1', { name: 'edit', display_name: 'edit', code_dispatch: true, result_summary: 'updated src/app.ts' })
        emit('item.completed', 'final_answer', 'answer-ui', { text: '修改完成，测试已经通过。', source: 'model' })
        emit('run.completed', undefined, undefined, { reason: 'stop' })
        return { decided: true }
      },
      inspect: async () => ({ generated_at: Date.now(), branch: 'codex/ui-contract', git_available: true, diff_truncated: false,
        files: [{ path: 'src', kind: 'directory', depth: 0 }, { path: 'src/app.ts', kind: 'file', depth: 1 }, { path: 'src/api/client.py', kind: 'file', depth: 2 }, { path: 'config.json', kind: 'file', depth: 0 }, { path: 'assets/logo.bin', kind: 'file', depth: 1 }],
        changes: [
          { path: 'src/app.ts', status: 'M', additions: 12, deletions: 3, binary: false },
          { path: 'src/api/client.py', status: '??', additions: 0, deletions: 0, binary: false },
          { path: 'src/components/ChangePanel.vue', status: 'A', additions: 86, deletions: 0, binary: false },
          { path: 'config.json', status: 'M', additions: 4, deletions: 2, binary: false },
          { path: 'assets/logo.bin', status: 'M', additions: null, deletions: null, binary: true },
        ],
        diff: 'diff --git a/src/app.ts b/src/app.ts\n--- a/src/app.ts\n+++ b/src/app.ts\n@@ -1 +1 @@\n-old\n+new\n'.repeat(80),
      }),
      summary: async () => ({ generated_at: Date.now(), branch: 'codex/ui-contract', git_available: true,
        changes: [
          { path: 'src/app.ts', status: 'M', additions: 12, deletions: 3, binary: false },
          { path: 'src/api/client.py', status: '??', additions: 0, deletions: 0, binary: false },
          { path: 'src/components/ChangePanel.vue', status: 'A', additions: 86, deletions: 0, binary: false },
          { path: 'config.json', status: 'M', additions: 4, deletions: 2, binary: false },
          { path: 'assets/logo.bin', status: 'M', additions: null, deletions: null, binary: true },
        ],
      }),
      listDirectory: async (_session: string, path = '') => path
        ? [{ name: 'app.ts', path: 'src/app.ts', kind: 'file', size: 120 }]
        : [{ name: 'src', path: 'src', kind: 'directory', size: null }],
      previewFile: async () => ({ path: 'src/app.ts', name: 'app.ts', kind: 'text', language: 'typescript', content: 'export const value = true\n', mime_type: 'text/plain', size: 26, truncated: false }),
      fileDiff: async () => ({ path: 'src/app.ts', diff: '@@ -1 +1 @@\n-old\n+new\n', truncated: false, binary: false }),
      commit: async () => ({ commit_hash: 'b'.repeat(40), short_hash: 'b'.repeat(8), branch: 'askai/ui-contract', message: 'Update files', changed_files: 1 }), push: async () => ({ commit_hash: 'b'.repeat(40), branch: 'askai/ui-contract', remote: 'origin', upstream: 'origin/askai/ui-contract' }), latestTaskChanges: async () => null, undoTaskChanges: async () => null, taskFileDiff: async () => ({ path: '', diff: '', binary: false }),
      createTerminal: async () => ({ terminal_id: 'terminal-ui' }), writeTerminal: async () => ({ written: true }), resizeTerminal: async () => ({ resized: true }), closeTerminal: async () => ({ closed: true }), onTerminalEvent: () => () => {},
    },
    browser: { state: async () => ({ session_id: 'default', active: false, visible: false, purpose: 'automation', owner: 'agent', url: '', title: '', loading: false, canGoBack: false, canGoForward: false, controllable: false, active_tab_id: '', tabs: [] }), selectSession: async () => {}, activateSession: async () => {}, attachSurface: async () => {}, showSurface: async () => {}, hideSurface: async () => {}, setSurfaceBounds: async () => {}, show: async () => {}, hide: async () => {}, setBounds: async () => {}, open: async () => {}, history: async () => {}, reload: async () => {}, newTab: async () => {}, selectTab: async () => {}, closeTab: async () => {}, setOwner: async () => {}, onState: () => () => {}, onLayoutRequest: () => () => {} },
    resources: { open: async () => {}, saveBytes: async () => ({ saved: false }) },
  }
}
