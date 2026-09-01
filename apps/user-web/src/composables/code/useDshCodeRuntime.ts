import { computed, onBeforeUnmount, reactive } from 'vue'
import {
  capabilities,
  attachDshCodeConversation,
  cancelDshCodeTurn,
  createDshCodeSession,
  decideDshCodeApproval,
  getLatestDshTaskChanges,
  listDshCodeApprovals,
  listDshWorkspaces,
  onDshCodeEvent,
  selectDshWorkspace,
  sendDshCodeTurn,
  subscribeDshCodeEvents,
  unsubscribeDshCodeEvents,
} from '../../platform'
import type { DshCodeSession, DshExecutionEvent, DshPendingApproval, DshWorkspace } from '../../platform/types'
import type { ExternalTurnHandle } from '../useChatRuntimeStore'
import { getLocale } from '../i18n'
import { codeRuntimeErrorMessage } from './codeRuntimeErrors'

export type CodePaneState = {
  draftId: string
  workspace: DshWorkspace | null
  session: DshCodeSession | null
  worktree: boolean
  sourceRef: string
  busy: boolean
  error: string
  cursor: number
  events: DshExecutionEvent[]
  approvals: DshPendingApproval[]
  approvalBusy: Record<string, boolean>
}

type ChatRuntimeBoundary = {
  beginExternalTurn(key: string, text: string, sessionId: string): ExternalTurnHandle
}

function draftState(): CodePaneState {
  return reactive({
    draftId: crypto.randomUUID(), workspace: null, session: null, worktree: false, sourceRef: '',
    busy: false, error: '', cursor: -1, events: [], approvals: [], approvalBusy: {},
  })
}

function terminal(event: DshExecutionEvent): boolean {
  return event.type === 'run.completed' || event.type === 'run.failed' || event.type === 'run.cancelled'
}

/** Owns desktop-only Code task state while delegating all execution to DSH. */
export function useDshCodeRuntime(chat: ChatRuntimeBoundary) {
  const panes = reactive(new Map<string, CodePaneState>())
  const turns = new Map<string, ExternalTurnHandle>()
  const subscribed = new Set<string>()

  const eventDispose = capabilities.codeExecution
    ? onDshCodeEvent((sessionId, event) => {
        const entry = [...panes.values()].find(item => item.session?.kernel_session_id === sessionId)
        if (!entry || event.stream_seq <= entry.cursor) return
        entry.cursor = event.stream_seq
        entry.events.push(event)
        if (entry.events.length > 10_000) entry.events.splice(0, entry.events.length - 10_000)
        turns.get(sessionId)?.apply(event)
        if (event.item_kind === 'approval') void refreshApprovals(entry)
        if (terminal(event)) {
          const turn = turns.get(sessionId)
          turn?.finish()
          turns.delete(sessionId)
          entry.busy = false
          void refreshApprovals(entry)
          if (turn) void getLatestDshTaskChanges(sessionId).then(changes => {
            if (changes?.files.length) turn.setCodeChanges(changes)
          }).catch(error => { console.warn('[code] failed to summarize task changes', error) })
        }
      })
    : () => {}

  function stateFor(key: string): CodePaneState {
    let state = panes.get(key)
    if (!state) {
      state = draftState()
      panes.set(key, state)
    }
    return state
  }

  function recommendRecent(state: CodePaneState, authorized: readonly DshWorkspace[]) {
    const recent = [...authorized]
      .filter(item => item.status === 'ok')
      .sort((a, b) => Date.parse(b.updated_at) - Date.parse(a.updated_at))[0]
    if (!state.workspace && !state.session && recent) {
      state.workspace = recent
      state.sourceRef = recent.git_branch ? `refs/heads/${recent.git_branch}` : 'HEAD'
    }
  }

  function recommend(key: string, authorized: readonly DshWorkspace[] = []) {
    const state = stateFor(key)
    if (capabilities.localWorkspacePicker) recommendRecent(state, authorized)
  }

  async function choose(key: string, modelId?: string) {
    const state = stateFor(key)
    if (state.session) throw new Error('a started Code task cannot switch Workspace')
    state.busy = true
    state.error = ''
    try {
      const selected = await selectDshWorkspace(modelId)
      if (selected) {
        state.workspace = selected
        state.sourceRef = selected.git_branch ? `refs/heads/${selected.git_branch}` : 'HEAD'
      }
      return selected
    } catch (error) {
      state.error = codeRuntimeErrorMessage(error, getLocale())
      throw error
    } finally { state.busy = false }
  }

  async function attach(key: string, conversationId: string) {
    if (!capabilities.codeExecution) return null
    const state = stateFor(key)
    state.error = ''
    try {
      const session = await attachDshCodeConversation(conversationId)
      if (!session) return null
      state.session = session
      state.worktree = session.worktree
      state.sourceRef = session.source_ref || (session.git_branch ? `refs/heads/${session.git_branch}` : 'HEAD')
      const workspaces = await listDshWorkspaces(session.model_instance_id)
      // A worktree Workspace is an internal execution detail. The UI always
      // presents the source project the user selected.
      state.workspace = workspaces.find(item => item.workspace_id === session.source_workspace_id) || null
      await ensureSubscribed(state)
      await refreshApprovals(state)
      return session
    } catch (error) {
      state.error = codeRuntimeErrorMessage(error, getLocale())
      return null
    }
  }

  function clear(key: string) {
    const state = stateFor(key)
    if (state.session) throw new Error('a started Code task cannot clear its Workspace')
    state.workspace = null
    state.sourceRef = ''
    state.error = ''
  }

  function setWorktree(key: string, enabled: boolean) {
    const state = stateFor(key)
    if (state.session) throw new Error('a started Code task cannot change isolation')
    state.worktree = enabled
  }

  function setSourceRef(key: string, sourceRef: string) {
    const state = stateFor(key)
    if (state.session) throw new Error('a started Code task cannot change its starting branch')
    state.sourceRef = sourceRef || 'HEAD'
  }

  function setWorkspaceBranch(key: string, branch: string) {
    const state = stateFor(key)
    if (!state.workspace) return
    state.workspace = { ...state.workspace, git_branch: branch || undefined }
    state.sourceRef = branch ? `refs/heads/${branch}` : 'HEAD'
  }

  function setDraftProject(key: string, workspace: DshWorkspace, worktree: boolean) {
    const state = stateFor(key)
    if (state.session) throw new Error('a started Code task cannot switch Workspace')
    state.workspace = workspace
    state.worktree = worktree
    state.sourceRef = workspace.git_branch ? `refs/heads/${workspace.git_branch}` : 'HEAD'
  }

  function transferDraft(fromKey: string, toKey: string) {
    const source = stateFor(fromKey)
    if (source.session) throw new Error('a started Code task cannot be transferred')
    const target = stateFor(toKey)
    target.workspace = source.workspace
    target.worktree = source.worktree
    target.sourceRef = source.sourceRef
    source.workspace = null
    source.sourceRef = ''
    source.error = ''
    return target
  }

  async function ensureSubscribed(state: CodePaneState) {
    const sessionId = state.session?.kernel_session_id
    if (!sessionId || subscribed.has(sessionId)) return
    await subscribeDshCodeEvents(sessionId, state.cursor)
    subscribed.add(sessionId)
  }

  async function refreshApprovals(state: CodePaneState) {
    const sessionId = state.session?.kernel_session_id
    if (!sessionId) return
    try { state.approvals = await listDshCodeApprovals(sessionId) }
    catch (error) { state.error = codeRuntimeErrorMessage(error, getLocale()) }
  }

  async function send(key: string, text: string, modelId?: string) {
    const state = stateFor(key)
    const workspace = state.workspace
    if (!workspace) return false
    if (!capabilities.codeExecution) throw new Error('local Code execution is unavailable')
    if (state.busy) throw new Error('Code task is already running')
    state.busy = true
    state.error = ''
    try {
      if (!state.session) {
        state.session = await createDshCodeSession(
          workspace.workspace_id, state.draftId, text.trim().slice(0, 120) || 'Code task', modelId, state.worktree,
          state.sourceRef || 'HEAD',
        )
      }
      const sessionId = state.session.kernel_session_id
      const conversationId = state.session.conversation_id
      if (!conversationId) throw new Error('desktop Code Session was not committed to MOVO history')
      await ensureSubscribed(state)
      turns.set(sessionId, chat.beginExternalTurn(key, text, conversationId))
      await sendDshCodeTurn(sessionId, text)
      await refreshApprovals(state)
      return true
    } catch (error) {
      state.error = codeRuntimeErrorMessage(error, getLocale())
      turns.get(state.session?.kernel_session_id || '')?.finish()
      turns.delete(state.session?.kernel_session_id || '')
      state.busy = false
      throw error
    }
  }

  async function stop(key: string) {
    const state = stateFor(key)
    const sessionId = state.session?.kernel_session_id
    if (!sessionId) return false
    await cancelDshCodeTurn(sessionId)
    return true
  }

  async function decide(
    key: string, approvalId: string, decision: 'approved' | 'rejected', scope: 'once' | 'session',
  ) {
    const state = stateFor(key)
    const sessionId = state.session?.kernel_session_id
    if (!sessionId) throw new Error('Code Session is unavailable')
    state.approvalBusy[approvalId] = true
    state.error = ''
    try {
      await decideDshCodeApproval(sessionId, approvalId, decision, scope)
      await refreshApprovals(state)
    } catch (error) {
      state.error = codeRuntimeErrorMessage(error, getLocale())
      throw error
    } finally { delete state.approvalBusy[approvalId] }
  }

  function needsAssistance(sessionId: string) {
    return [...panes.values()].some(state => state.session?.conversation_id === sessionId && state.approvals.length > 0)
  }

  const activeSessions = computed(() => [...panes.values()].filter(state => state.session))

  function reset() {
    for (const sessionId of subscribed) void unsubscribeDshCodeEvents(sessionId)
    subscribed.clear()
    turns.clear()
    panes.clear()
  }

  onBeforeUnmount(() => {
    eventDispose()
    for (const sessionId of subscribed) void unsubscribeDshCodeEvents(sessionId)
  })

  return { stateFor, recommend, attach, choose, clear, setWorktree, setSourceRef, setWorkspaceBranch, setDraftProject, transferDraft, send, stop, decide, needsAssistance, activeSessions, reset }
}
