import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'

;(globalThis as any).navigator = { language: 'zh-CN', languages: ['zh-CN'] }
;(globalThis as any).localStorage = {
  getItem: () => null, setItem: () => undefined, removeItem: () => undefined,
}
;(globalThis as any).window = { open: () => { throw new Error('Web Code contract must not open a local execution surface') } }

const web = await import('../src/platform/web')
const { codeRuntimeErrorMessage } = await import('../src/composables/code/codeRuntimeErrors')
const { buildWorkspaceChangeTree } = await import('../src/components/code/changeTree')
const { changeStatusPresentation, fileTypePresentation } = await import('../src/components/code/changePresentation')
const { parseUnifiedDiff } = await import('../src/components/code/unifiedDiff')
const { syntaxLanguage } = await import('../src/components/code/codeSyntax')
const { agentCapabilityAllowed, tenantAdminAllowed } = await import('../src/composables/useEnterpriseAccessPolicy')
const { formatQuotaUsagePercent, formatTokenAmount, quotaUsagePercent } = await import('../src/utils/tokenNumberFormat')

assert.deepEqual({
  localDshRuntime: web.capabilities.localDshRuntime,
  localWorkspacePicker: web.capabilities.localWorkspacePicker,
  codeExecution: web.capabilities.codeExecution,
  codeInspector: web.capabilities.codeInspector,
}, {
  localDshRuntime: false,
  localWorkspacePicker: false,
  codeExecution: false,
  codeInspector: false,
})
assert.deepEqual(await web.listDshWorkspaces(), [])
assert.equal(await web.attachDshCodeConversation('conversation-a'), null)
assert.deepEqual(await web.listDshCodeApprovals('session-a'), [])
await assert.rejects(web.sendDshCodeTurn('session-a', 'touch a file'), /only available in the desktop app/)
await assert.rejects(web.inspectDshCodeWorkspace('session-a'), /only available in the desktop app/)
await assert.rejects(web.listDshWorkspaceDirectory('session-a'), /only available in the desktop app/)
await assert.rejects(web.createDshProjectTerminal('session-a'), /only available in the desktop app/)
await assert.rejects(web.selectDshWorkspace(), /only available in the desktop app/)
await assert.rejects(web.listDshWorkspaceBranches('workspace-a'), /only available in the desktop app/)
await assert.rejects(web.switchDshWorkspaceBranch('workspace-a', 'refs\/heads\/main'), /only available in the desktop app/)

assert.match(codeRuntimeErrorMessage(new Error('Code Session belongs to another desktop device'), 'zh'), /另一台桌面设备/)
assert.match(codeRuntimeErrorMessage(new Error('Code Session Workspace is unavailable or missing'), 'zh'), /项目目录已丢失/)
assert.match(codeRuntimeErrorMessage(new Error('Runtime Profile changed'), 'en'), /incompatible/)
const changeTree = buildWorkspaceChangeTree([
  { path: 'src/app.ts', status: 'M', additions: 2, deletions: 1, binary: false },
  { path: 'src/api/client.ts', status: 'A', additions: 8, deletions: 0, binary: false },
])
assert.equal(changeTree[0]?.name, 'src')
assert.equal(changeTree[0]?.children.find(item => item.name === 'api')?.children[0]?.path, 'src/api/client.ts')
assert.deepEqual(changeStatusPresentation('??', 'zh'), { label: 'U', description: '尚未被 Git 跟踪的新文件', tone: 'added' })
assert.equal(changeStatusPresentation('M', 'zh').label, 'M')
assert.equal(changeStatusPresentation('UU', 'zh').label, 'C')
assert.equal(fileTypePresentation('src/app.ts').label, 'TS')
assert.equal(fileTypePresentation('server/task.py').label, 'PY')
assert.equal(fileTypePresentation('package.json').label, '{}')
assert.equal(fileTypePresentation('src/App.vue').name, 'Vue')
assert.equal(syntaxLanguage('src/app.ts'), 'typescript')
assert.equal(syntaxLanguage('server/task.py'), 'python')
const employeeProfile = {
  agentPolicy: {
    capabilities: { content_generation: true, image_generation: false, code_generation: false, browser_automation: false, internal_knowledge: true },
    toolAccessMode: 'selected', toolIds: ['crm'], skillAccessMode: 'all', skillIds: [], roleIds: ['employee'], roleNames: ['普通员工'],
  },
}
assert.equal(agentCapabilityAllowed(employeeProfile as any, 'code_generation'), false)
assert.equal(tenantAdminAllowed({ mainId: 'org-1', orgName: '企业', userId: 'u1', displayName: '员工', username: 'employee', canAccessAdmin: false }), false)
assert.equal(tenantAdminAllowed({ mainId: 'personal-1', orgName: '个人空间', spaceType: 'personal', userId: 'u2', displayName: '个人用户', username: 'owner', canAccessAdmin: true }), false)
assert.equal(tenantAdminAllowed({ mainId: 'org-1', orgName: '企业', spaceType: 'enterprise', userId: 'u3', displayName: '管理员', username: 'admin', canAccessAdmin: true }), true)
assert.equal(formatTokenAmount(9_959_230_000, 'zh'), '99.59 亿')
assert.equal(formatTokenAmount(10_000_000_000, 'zh'), '100 亿')
assert.equal(formatTokenAmount(9_959_230_000, 'en'), '9.96 B')
assert.equal(formatQuotaUsagePercent(40_770_000, 10_000_000_000), '0.41')
assert.equal(quotaUsagePercent(40_770_000, 10_000_000_000), 0.4077)
const diffLines = parseUnifiedDiff('@@ -10,2 +20,2 @@\n unchanged\n-old\n+new')
assert.deepEqual(diffLines.map(line => [line.oldLine, line.newLine, line.kind]), [
  [null, null, 'hunk'], [10, 20, 'context'], [11, null, 'delete'], [null, 21, 'add'],
])

// A suggested recent Workspace is still a draft choice. The new-session
// context exposes project, direct editing (the default), worktree creation,
// current branch, a selectable starting ref, and a copyable path. Once locked,
// draft mode and branch controls are hidden.
const workspacePicker = readFileSync('src/components/code/WorkspaceContextPicker.vue', 'utf8')
const branchPicker = readFileSync('src/components/code/BranchContextPicker.vue', 'utf8')
const draftContext = readFileSync('src/components/code/CodeDraftContextBar.vue', 'utf8')
assert.match(workspacePicker, /'本地修改'/)
assert.match(workspacePicker, /'新建本地工作树'/)
assert.match(workspacePicker, /'复制项目地址'/)
assert.match(workspacePicker, /v-if="!locked" class="mode-options"/)
assert.match(workspacePicker, /暂不创建新分支/)
assert.match(workspacePicker, /max-height: calc\(50vh - 24px\)/)
assert.doesNotMatch(workspacePicker, /<GitBranchSelector/)
assert.match(branchPicker, /<GitBranchSelector/)
assert.match(branchPicker, /基于 \$\{sourceLabel\.value\} · 未建分支/)
assert.match(draftContext, /<WorkspaceContextPicker/)
assert.match(draftContext, /<BranchContextPicker/)

const codeRuntime = readFileSync('src/composables/code/useDshCodeRuntime.ts', 'utf8')
assert.match(codeRuntime, /workspace: null, session: null, worktree: false, sourceRef: ''/)
assert.match(codeRuntime, /session\.source_workspace_id/)
assert.match(codeRuntime, /state\.sourceRef \|\| 'HEAD'/)

// Empty sessions keep Code context above the composer; once messages exist,
// App moves the same component into the window toolbar.
const desktopChrome = readFileSync('src/components/desktop/DesktopWindowChrome.vue', 'utf8')
const chatComposer = readFileSync('src/components/chat/ChatComposer.vue', 'utf8')
const chatWindow = readFileSync('src/components/ChatWindow.vue', 'utf8')
const assistantMarkdown = readFileSync('src/components/chat/AssistantMarkdown.vue', 'utf8')
const appShell = readFileSync('src/App.vue', 'utf8')
const billingModal = readFileSync('src/components/BillingModal.vue', 'utf8')
assert.match(desktopChrome, /<WorkspaceContextPicker/)
assert.match(desktopChrome, /<BranchContextPicker/)
assert.match(desktopChrome, /chatActions && codeAvailable && showWorkspaceContext/)
assert.match(desktopChrome, /<BrowserTestButton v-if="browserAvailable && sessionId" icon-only/)
assert.match(desktopChrome, /codeAvailable && codeSessionActive && gitAvailable/)
assert.match(desktopChrome, /<GitCompareOutline/)
assert.match(desktopChrome, /<FolderOpenOutline/)
assert.match(desktopChrome, /<TerminalOutline/)
assert.match(chatComposer, /class="composer-footer/)
assert.match(chatComposer, /absolute bottom-9 left-0/)
assert.match(chatWindow, /text-\[14px\] text-gray-900 leading-6/)
assert.match(assistantMarkdown, /compact: true/)
assert.match(assistantMarkdown, /\.assistant-markdown-compact :deep\(h2\) \{ font-size: 1\.12em;/)
assert.match(chatWindow, /<ProjectWorkspacePanel/)
assert.match(chatWindow, /allowCode && isNewSessionView && capabilities\.localWorkspacePicker/)
assert.match(chatWindow, /<CodeDraftContextBar/)
assert.doesNotMatch(chatWindow, /<CodeInspector/)
assert.doesNotMatch(chatWindow, /<BrowserTestButton/)
assert.match(appShell, /:agent-policy="userProfile\?\.agentPolicy"/)
assert.match(appShell, /useEnterpriseAccessPolicy\(userProfile\)/)
assert.match(appShell, /const supportsLocalCodeProjects = capabilities\.localDshRuntime && capabilities\.localWorkspacePicker/)
assert.match(appShell, /!supportsLocalCodeProjects \|\| !session\.code_project\?\.workspace_id/)
assert.match(appShell, /canUseCode && supportsLocalCodeProjects && projectHistoryGroups\.length/)
assert.match(appShell, /v-if="canAccessAdmin\(tenant\)"/)
assert.match(appShell, /:can-access-admin="isEnterpriseSpace && userProfile\?\.canAccessAdmin === true"/)
assert.match(billingModal, /v-if="billingData && canAccessAdmin"/)
assert.match(chatWindow, /:allow-knowledge="allowKnowledge"/)
assert.match(chatWindow, /:allow-skills="allowSkills"/)

console.log('Web/desktop Code capability boundary contract passed')
