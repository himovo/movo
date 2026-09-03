import assert from 'node:assert/strict'
import { createExecutionStoreV3 } from '../src/features/execution-v3/stores/executionStore'
import { ensureMessageExecutionV3 } from '../src/features/execution-v3/stores/messageExecution'
import type { ExecutionEventV3 } from '../src/features/execution-v3/domain/protocol'
import { isRef, reactive } from 'vue'
import { useAuthoritativeMessages } from '../src/components/chat/useAuthoritativeMessages'
import { refreshAfterRun } from '../src/composables/chatRuntimeRefresh'
import { activityOutcome, activityStateMessageKey, hasActiveRunningLeaf, runningContainerIds } from '../src/features/execution-v3/domain/activityPresentation'
import { collapseRepeatedToolCalls, toolCallDetail, toolCallSummary, toolCapabilityKeys } from '../src/features/execution-v3/domain/repeatedToolCalls'
import { elapsedRunMs, formatRunDuration } from '../src/features/execution-v3/domain/runTiming'
import { applyAssistantContentEvent } from '../src/features/execution-v3/domain/assistantContent'
import { decideToolApproval, listPendingToolApprovals } from '../src/api/toolApprovals'
import {
  browserInterventionTransition,
  normalizeBrowserIntervention,
} from '../src/composables/browser/browserInterventionProjection'
import { renderAssistantMarkdown, workspaceFileReference } from '../src/utils/assistantMarkdown'
import { resolveArtifactKind } from '../src/features/execution-v3/domain/artifactKind'

let sequence = 0
function event(overrides: Partial<ExecutionEventV3>): ExecutionEventV3 {
  sequence += 1
  return {
    v: 3,
    event_id: `event_${sequence}`,
    id: `event_${sequence}`,
    ts: sequence,
    type: 'item.started',
    revision: 1,
    payload: {},
    ...overrides,
  }
}

{
  const items = [
    { id: 'streamed-note', kind: 'final_answer', payload: { text: '先检查项目结构。', provisional: true } },
    { id: 'note', kind: 'commentary', payload: { text: '先检查项目结构。' } },
    { id: 'run-code-1', kind: 'tool', payload: { name: 'run_code', callId: 'run-code-1' } },
    { id: 'bash-1', kind: 'tool', payload: { name: 'bash', code_dispatch: true, parent_call_id: 'run-code-1', root_call_id: 'run-code-1', args: { command: 'ls', description: '查看根目录' } } },
    { id: 'run-code-2', kind: 'tool', payload: { name: 'run_code', callId: 'run-code-2' } },
    { id: 'read-1', kind: 'tool', payload: { name: 'read', code_dispatch: true, parent_call_id: 'run-code-2', root_call_id: 'run-code-2', args: { path: 'README.md', token: 'hidden' } } },
    { id: 'next-note', kind: 'commentary', payload: { text: '继续确认关键模块。' } },
  ].map((item) => ({ ...item, revision: 1, startedAt: 0, updatedAt: 0, status: 'completed' })) as any
  const timeline = collapseRepeatedToolCalls(items)
  assert.deepEqual(timeline.map((entry) => entry.type), ['item', 'tool-group', 'item'])
  assert.equal(timeline[0].type === 'item' && timeline[0].item.id, 'note')
  assert.equal(timeline[1].type === 'tool-group' && timeline[1].items.length, 2)
  assert.equal(timeline[1].type === 'tool-group' && timeline[1].statusItems.length, 4)
  assert.deepEqual(timeline[1].type === 'tool-group' && timeline[1].items.map(item => item.id), ['bash-1', 'read-1'])
  assert.equal(toolCallSummary(items[3]), '查看根目录')
  assert.equal(toolCallSummary(items[5]), 'README.md')
  assert.equal(toolCallDetail(items[5]), 'README.md')
  const persistedStringArgs = {
    ...items[5], id: 'read-string', payload: { name: 'read', args: '{"file_path":"src/HomeHero.vue"}' },
  } as any
  assert.equal(toolCallSummary(persistedStringArgs), 'HomeHero.vue')
  const hiddenCommand = {
    ...items[3], id: 'bash-secret', payload: {
      name: 'bash', args: { command: 'curl -H "Authorization: secret" internal.example', description: '检查页面样式' },
    },
  } as any
  assert.equal(toolCallSummary(hiddenCommand), '检查页面样式')
  assert.doesNotMatch(toolCallDetail(hiddenCommand), /secret|curl|internal\.example/)
  const translatedDocument = {
    ...items[5],
    payload: {
      name: 'document_transform',
      args: {
        artifact: {
          object_path: 'tenant/2026/08/26/%E4%BC%81%E4%B8%9A%E9%83%A8%E7%BD%B2%E6%8C%87%E5%8D%97.docx',
          signed_url: 'https://storage.example/private?token=secret',
        },
        target_language: '韩文',
      },
    },
  } as any
  assert.equal(toolCallDetail(translatedDocument), '企业部署指南.docx · target_language: 韩文')
  assert.doesNotMatch(toolCallDetail(translatedDocument), /object_path|signed_url|storage\.example/)
  assert.deepEqual(toolCapabilityKeys([
    { ...items[3], payload: { name: 'read' } },
    { ...items[3], id: 'edit-1', payload: { name: 'apply_patch' } },
    { ...items[3], id: 'bash-2', payload: { name: 'bash' } },
    { ...items[3], id: 'read-2', payload: { name: 'read_file' } },
  ] as any), [
    'execution.v3.activity.read_files',
    'execution.v3.activity.edit_files',
    'execution.v3.activity.run_commands',
  ])
  assert.deepEqual(toolCapabilityKeys([
    { ...items[3], payload: { name: 'todo_write', args: { todos: [{ content: 'private plan' }] } } },
  ] as any), ['execution.v3.activity.update_plan'])
}

{
  assert.equal(resolveArtifactKind({ kind: 'document', filename: '翻译结果.docx' }), 'docx')
  assert.equal(resolveArtifactKind({ kind: 'document', object_path: 'files/report.PDF' }), 'pdf')
  assert.equal(resolveArtifactKind({ kind: 'document', content_type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' }), 'xlsx')
  assert.equal(resolveArtifactKind({ kind: 'html', filename: '交付物.docx' }), 'docx')
  assert.equal(resolveArtifactKind({ kind: 'document' }), 'generic')
  assert.equal(resolveArtifactKind({
    type: 'presentation_preview_bundle',
    filename: 'presentation_preview_v5_MOVO.html',
    object_path: 'files/presentation_preview_v5_MOVO.html',
  }), 'presentation_preview_bundle')
  assert.equal(resolveArtifactKind({
    kind: 'presentation_preview_bundle',
    content_type: 'text/html',
  }), 'presentation_preview_bundle')
}

{
  const store = createExecutionStoreV3()
  store.applyEvent(event({
    type: 'item.started', item_kind: 'tool', item_id: 'run-code', revision: 1,
    payload: { name: 'run_code', display_name: 'run_code', args: { code: '...' } },
  }))
  store.applyEvent(event({
    type: 'item.completed', item_kind: 'tool', item_id: 'run-code', revision: 2,
    payload: { status: 'succeeded', ok: true },
  }))
  assert.equal(store.state.items['run-code'].payload.name, 'run_code')
  assert.deepEqual(store.state.items['run-code'].payload.args, { code: '...' })
}

{
  const store = createExecutionStoreV3()
  store.loadHistory([
    event({
      type: 'item.delta', item_kind: 'final_answer', item_id: 'legacy-stream-id', revision: 1,
      payload: { text: '我先检查项目结构。', provisional: true },
    }),
    event({
      type: 'item.completed', item_kind: 'commentary', item_id: 'legacy-message-uuid', revision: 2,
      payload: { text: '我先检查项目结构。', provisional: false },
    }),
  ])
  const timeline = collapseRepeatedToolCalls(store.visibleItems.value)
  assert.equal(timeline.length, 1)
  assert.equal(timeline[0].type === 'item' && timeline[0].item.id, 'legacy-message-uuid')
}

{
  const streamed = '## 发票摘要\n\n**价税合计**：216.40 元'
  const provisionalHtml = renderAssistantMarkdown(streamed)
const completedHtml = renderAssistantMarkdown(streamed)
  assert.equal(provisionalHtml, completedHtml)
  assert.match(provisionalHtml, /<h2[^>]*>发票摘要<\/h2>/)
  assert.match(provisionalHtml, /<strong[^>]*>价税合计<\/strong>/)
  assert.equal(provisionalHtml.includes('## 发票摘要'), false)
  assert.equal(provisionalHtml.includes('**价税合计**'), false)
}

{
  const code = renderAssistantMarkdown('```text\nconst answer = 42\n```')
  assert.match(code, /class="assistant-code-block /)
  assert.match(code, /class="assistant-code-content /)
  assert.doesNotMatch(code, /bg-gray-900|bg-gray-800|text-gray-200/)
}

{
  assert.equal(workspaceFileReference('src/api_client.py'), 'src/api_client.py')
  assert.equal(workspaceFileReference('README.md:42'), 'README.md')
  assert.equal(workspaceFileReference('base_url'), null)
  assert.equal(workspaceFileReference('{upload_url}/collection/article'), null)
  const references = renderAssistantMarkdown('`src/api_client.py` and `base_url`', { workspaceFileReferences: true })
  assert.match(references, /class="assistant-inline-code assistant-file-reference"/)
  assert.match(references, /data-workspace-file="src\/api_client.py"/)
  assert.match(references, /<code class="assistant-inline-code">base_url<\/code>/)
  assert.doesNotMatch(references, /text-pink-600/)
}

{
  const sources = renderAssistantMarkdown(
    '主要证据来源：[DeepSeek Harness 官方页](https://deepseek.com/harness/en)、[GitHub 仓库](https://github.com/deepseek-ai/deepseek-harness)',
  )
  assert.match(sources, /<a href="https:\/\/deepseek\.com\/harness\/en"/)
  assert.match(sources, /target="_blank"/)
  assert.match(sources, /rel="noopener noreferrer nofollow"/)
  assert.doesNotMatch(sources, /\[DeepSeek Harness 官方页\]\(/)

  const unsafe = renderAssistantMarkdown('[危险链接](javascript:alert(1))')
  assert.doesNotMatch(unsafe, /<a href=/)
  assert.match(unsafe, /javascript:alert/)
}

{
  const beforeSeparator = renderAssistantMarkdown('| 项目 | 金额 |')
  const afterSeparator = renderAssistantMarkdown('| 项目 | 金额 |\n| --- | --- |\n| 餐费 | 216.40 |')
  assert.match(beforeSeparator, /<table/)
  assert.match(afterSeparator, /<table/)
  assert.match(afterSeparator, /<th/)
}

{
  assert.equal(elapsedRunMs(1_000, 66_000, 99_000), 65_000)
  assert.equal(formatRunDuration(65_000, 'zh'), '1分5秒')
  assert.equal(formatRunDuration(3_665_000, 'en'), '1h 1m 5s')
}

{
  const payload = { detail: { outcome: 'inconclusive', error_type: 'ValidationError' } }
  assert.equal(activityOutcome(payload), 'inconclusive')
  assert.equal(activityStateMessageKey('completed', activityOutcome(payload)), 'execution.v3.quality_inconclusive')
  assert.equal(
    activityStateMessageKey('completed', 'inconclusive', { detail: { error_type: 'TimeoutError' } }),
    'execution.v3.quality_timeout',
  )
  assert.equal(activityStateMessageKey('failed', ''), 'ui.failed')
}

{
  const message = { content: '' }
  const store = createExecutionStoreV3()
  const delta = event({
    type: 'item.delta', item_kind: 'final_answer', item_id: 'step_2', revision: 10,
    payload: { text: '搜索失败，我缩短名称重试', provisional: true },
  })
  store.applyEvent(delta)
  applyAssistantContentEvent(message, delta)
  assert.equal(message.content, '')
  assert.equal(store.visibleItems.value[0].id, 'step_2')
  assert.equal(store.visibleItems.value[0].kind, 'final_answer')
  assert.equal(store.visibleItems.value[0].payload.text, '搜索失败，我缩短名称重试')
  const commentary = event({
    type: 'item.completed', item_kind: 'commentary', item_id: 'step_2', revision: 11,
    payload: { text: '搜索失败，我缩短名称重试', retract_provisional: true },
  })
  store.applyEvent(commentary)
  applyAssistantContentEvent(message, commentary)
  assert.equal(message.content, '')
  assert.equal(store.state.items.step_2.kind, 'commentary')
  assert.equal(store.state.items.step_2.status, 'completed')
  assert.equal(store.visibleItems.value[0].id, 'step_2')
  assert.equal(store.visibleItems.value[0].kind, 'commentary')
  const finalDelta = event({
    type: 'item.delta', item_kind: 'final_answer', item_id: 'step_3', revision: 12,
    payload: { text: '最终答案', provisional: true },
  })
  store.applyEvent(finalDelta)
  applyAssistantContentEvent(message, finalDelta)
  assert.equal(message.content, '')
  assert.equal(store.visibleItems.value.at(-1)?.id, 'step_3')
  const finalCompleted = event({
    type: 'item.completed', item_kind: 'final_answer', item_id: 'step_3', revision: 13,
    payload: { text: '最终答案', provisional: false },
  })
  store.applyEvent(finalCompleted)
  applyAssistantContentEvent(message, finalCompleted)
  assert.equal(message.content, '最终答案')
  assert.equal(store.visibleItems.value.some((item) => item.id === 'step_3'), false)
}

{
  const store = createExecutionStoreV3()
  store.applyEvent(event({ type: 'item.started', item_kind: 'activity', item_id: 'research', payload: { label: '研究资料' } }))
  store.applyEvent(event({ type: 'item.started', item_kind: 'activity', item_id: 'review', parent_item_id: 'research', payload: { label: '筛选候选资料' } }))
  assert.deepEqual([...runningContainerIds(store.visibleItems.value)], ['research'])
  store.applyEvent(event({ type: 'item.completed', item_kind: 'activity', item_id: 'review', parent_item_id: 'research', revision: 2, payload: { label: '筛选候选资料' } }))
  assert.deepEqual([...runningContainerIds(store.visibleItems.value)], ['research'])
  assert.equal(hasActiveRunningLeaf(store.visibleItems.value), false)
  store.applyEvent(event({ type: 'item.started', item_kind: 'tool', item_id: 'browser_click', parent_item_id: 'research', payload: { name: 'browser_click' } }))
  assert.equal(hasActiveRunningLeaf(store.visibleItems.value), true)
}

{
  const nested = event({
    type: 'item.completed', item_kind: 'tool', item_id: 'browser_tool',
    payload: {
      browser_intervention: {
        suspension_id: 'susp-1', run_id: 'run-1', node_id: 'node-1',
        browser_session_id: 'browser-1', resumable: true, reason: 'manual step',
      },
    },
  })
  const nestedTransition = browserInterventionTransition(nested)
  assert.equal(nestedTransition.kind, 'activated')
  if (nestedTransition.kind === 'activated') {
    assert.equal(nestedTransition.intervention.category, 'browser')
    assert.equal(nestedTransition.intervention.suspension_id, 'susp-1')
  }
  assert.equal(normalizeBrowserIntervention(nested.payload.browser_intervention)?.resumable, true)

  const canonical = browserInterventionTransition(event({
    type: 'item.started', item_kind: 'browser_handoff', item_id: 'handoff',
    payload: { suspension_id: 'susp-2', category: 'browser' },
  }))
  assert.equal(canonical.kind, 'activated')
  assert.equal(browserInterventionTransition(event({
    type: 'item.completed', item_kind: 'browser_handoff', item_id: 'handoff',
    payload: { suspension_id: 'susp-2', cleared: true },
  })).kind, 'cleared')
}

{
  const originalFetch = globalThis.fetch
  let request: { url: string; init?: RequestInit } | null = null
  globalThis.fetch = (async (url: string | URL | Request, init?: RequestInit) => {
    request = { url: String(url), init }
    return new Response(JSON.stringify({ code: 0 }), { status: 200, headers: { 'content-type': 'application/json' } })
  }) as typeof fetch
  await decideToolApproval('call/1', 'approved', 'token-a')
  assert.equal(request?.url, '/askai-api/api/dsh/tool-approvals/call%2F1/decision')
  assert.equal(request?.init?.method, 'POST')
  assert.equal((request?.init?.headers as Record<string, string>).Authorization, 'Bearer token-a')
  assert.deepEqual(JSON.parse(String(request?.init?.body)), { decision: 'approved', grantScope: 'once' })
  await decideToolApproval('call/2', 'approved', 'token-a', 'session')
  assert.deepEqual(JSON.parse(String(request?.init?.body)), { decision: 'approved', grantScope: 'session' })
  await listPendingToolApprovals('token-a', 'conversation/1')
  assert.equal(request?.url, '/askai-api/api/dsh/tool-approvals?conversation_id=conversation%2F1')
  globalThis.fetch = originalFetch
}

{
  const message = {
    execution_events: [
      event({ type: 'run.started', ts: 10_000 }),
      event({
        type: 'item.completed', item_kind: 'commentary', item_id: 'history_commentary',
        payload: { text: '历史过程仍可回放' },
      }),
      event({ type: 'run.completed', ts: 75_000 }),
    ],
    documents: [{ type: 'docx', object_path: 'reports/token.docx', filename: 'token.docx' }],
    evidence_bundles: [{ id: 'bundle_1', sources: [], confirmed_facts: [], open_questions: [] }],
  }
  const store = ensureMessageExecutionV3(message)
  assert.equal(store.state.items.history_commentary.payload.text, '历史过程仍可回放')
  assert.equal(store.state.artifacts.length, 1)
  assert.equal(store.state.evidenceBundles.length, 1)
  assert.equal(store.state.runStartedAt, 10_000)
  assert.equal(store.state.runEndedAt, 75_000)
  assert.equal(formatRunDuration(elapsedRunMs(store.state.runStartedAt, store.state.runEndedAt, Date.now()), 'zh'), '1分5秒')
  assert.equal(ensureMessageExecutionV3(message), store)
}

{
  const wrapped = reactive({ store: createExecutionStoreV3() })
  assert.equal(isRef(wrapped.store.visibleItems), true)
  wrapped.store.applyEvent(event({
    type: 'item.completed', item_kind: 'commentary', item_id: 'reactive_history',
    payload: { message: 'history remains renderable' },
  }))
  assert.equal(wrapped.store.visibleItems.value.length, 1)
}

{
  const parent = reactive<{ messages: Array<{ content: string }> }>({ messages: [] })
  const messages = useAuthoritativeMessages(() => parent.messages)
  parent.messages.push({ content: 'visible immediately' })
  assert.equal(messages.value.length, 1)
  assert.equal(messages.value[0].content, 'visible immediately')
  parent.messages = [{ content: 'replacement remains authoritative' }]
  assert.equal(messages.value[0].content, 'replacement remains authoritative')
}

{
  const called: string[] = []
  await refreshAfterRun({
    onQuotaRefresh: async () => { called.push('quota'); throw new Error('quota unavailable') },
    onSessionUpdated: async (sessionId) => { called.push(sessionId) },
  }, 'session_1')
  assert.deepEqual(called.sort(), ['quota', 'session_1'])
}

{
  const store = createExecutionStoreV3()
  store.applyEvent(event({ type: 'run.started', ts: 1_000 }))
  store.applyEvent(event({ type: 'item.started', item_kind: 'final_answer', item_id: 'final', revision: 1 }))
  store.applyEvent(event({ type: 'item.delta', item_kind: 'final_answer', item_id: 'final', revision: 2, payload: { text: 'hello ' } }))
  store.applyEvent(event({ type: 'item.delta', item_kind: 'final_answer', item_id: 'final', revision: 3, payload: { text: 'world' } }))
  assert.equal(store.state.items.final.payload.text, 'hello world')
  assert.equal(store.state.finalAnswerComplete, false)
  store.applyEvent(event({ type: 'item.completed', item_kind: 'final_answer', item_id: 'final', revision: 4, payload: { text: 'hello world' } }))
  assert.equal(store.state.finalAnswerComplete, true)
  store.applyEvent(event({ type: 'item.updated', item_kind: 'final_answer', item_id: 'final', revision: 2, payload: { text: 'stale' } }))
  assert.equal(store.state.items.final.payload.text, 'hello world')
}

{
  const store = createExecutionStoreV3()
  store.applyEvent(event({ type: 'item.started', item_kind: 'activity', item_id: 'search_1', payload: { category: 'search', label: '查询资料' } }))
  assert.equal(store.state.items.search_1.status, 'running')
  store.applyEvent(event({ type: 'item.completed', item_kind: 'activity', item_id: 'search_1', revision: 2, payload: { category: 'search', label: '查询资料' } }))
  assert.equal(store.state.items.search_1.status, 'completed')
}

{
  const store = createExecutionStoreV3()
  const first = event({ type: 'item.started', item_kind: 'tool', item_id: 'tool_1', payload: { name: 'search' } })
  store.applyEvent(first)
  store.applyEvent(first)
  store.applyEvent(event({ type: 'item.started', item_kind: 'tool', item_id: 'tool_2', payload: { name: 'search' } }))
  store.applyEvent(event({ type: 'item.completed', item_kind: 'tool', item_id: 'tool_2', revision: 2, payload: { name: 'search' } }))
  assert.equal(store.state.order.length, 2)
  assert.equal(store.state.items.tool_1.status, 'running')
  assert.equal(store.state.items.tool_2.status, 'completed')
}

{
  const store = createExecutionStoreV3()
  store.applyEvent(event({ type: 'run.started', ts: 1_000 }))
  store.applyEvent(event({ type: 'item.started', item_kind: 'commentary', item_id: 'planning', payload: { kind: 'planning' } }))
  store.applyEvent(event({ type: 'run.completed', ts: 66_000 }))
  assert.equal(store.state.items.planning.status, 'completed')
  assert.equal(store.state.runStartedAt, 1_000)
  assert.equal(store.state.runEndedAt, 66_000)
  assert.equal(elapsedRunMs(store.state.runStartedAt, store.state.runEndedAt, 99_000), 65_000)
}

{
  const store = createExecutionStoreV3()
  store.applyEvent(event({ type: 'run.started' }))
  store.applyEvent(event({ type: 'item.started', item_kind: 'tool', item_id: 'still_open', payload: { name: 'browser' } }))
  store.applyEvent(event({ type: 'run.completed' }))
  assert.equal(store.state.items.still_open.status, 'completed')
}

{
  const store = createExecutionStoreV3()
  store.applyEvent(event({ type: 'item.started', item_kind: 'browser_handoff', item_id: 'browser_handoff', revision: 2, payload: { reason: 'manual action' } }))
  store.applyEvent(event({ type: 'item.completed', item_kind: 'browser_handoff', item_id: 'browser_handoff', revision: 1, payload: { cleared: true } }))
  assert.equal(store.state.intervention, null)
  assert.equal(store.state.items.browser_handoff.status, 'completed')
}

{
  const store = createExecutionStoreV3()
  store.loadHistory([
    event({ type: 'run.started' }),
    event({ type: 'item.started', item_kind: 'tool', item_id: 'orphan', payload: { name: 'browser' } }),
  ])
  assert.equal(store.state.runStatus, 'failed')
  assert.equal(store.state.items.orphan.status, 'abandoned')
}

{
  const store = createExecutionStoreV3()
  store.applyEvent(event({ type: 'item.completed', item_kind: 'artifact', item_id: 'artifact_1', payload: { kind: 'pdf', url: '/report.pdf' } }))
  store.applyEvent(event({ type: 'item.completed', item_kind: 'evidence', item_id: 'evidence_1', payload: { summary: 'verified', sources: [], confirmed_facts: [], open_questions: [] } }))
  assert.equal(store.state.artifacts.length, 1)
  assert.equal(store.state.evidenceBundles.length, 1)
}

console.log('execution-v3 store tests passed')
