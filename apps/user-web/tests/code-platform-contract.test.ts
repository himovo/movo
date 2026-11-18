import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { workspaceContextMessages } from '../src/locales/workspaceContextMessages'
import { branchContextMessages } from '../src/locales/codeWorkspaceMessages'

Object.defineProperty(globalThis, 'navigator', {
  configurable: true,
  value: { language: 'zh-CN', languages: ['zh-CN'] },
})
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
assert.match(codeRuntimeErrorMessage(new Error('session is already owned by an active write handle'), 'en'), /being restored/)
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

// A selected or inherited Workspace is still a draft choice. The new-session
// context exposes project, direct editing (the default), worktree creation,
// current branch, a selectable starting ref, and a copyable path. Once locked,
// draft mode and branch controls are hidden.
const workspacePicker = readFileSync('src/components/code/WorkspaceContextPicker.vue', 'utf8')
const branchPicker = readFileSync('src/components/code/BranchContextPicker.vue', 'utf8')
const draftContext = readFileSync('src/components/code/CodeDraftContextBar.vue', 'utf8')
assert.match(workspacePicker, /copy\('workspaceContext\.editLocally'\)/)
assert.match(workspacePicker, /copy\('workspaceContext\.newWorktree'\)/)
assert.match(workspacePicker, /copy\('workspaceContext\.copyProjectPath'\)/)
assert.equal(workspaceContextMessages['workspaceContext.editLocally'].zh, '本地修改')
assert.equal(workspaceContextMessages['workspaceContext.editLocally'].en, 'Edit locally')
assert.equal(workspaceContextMessages['workspaceContext.newWorktree'].zh, '新建本地工作树')
assert.equal(workspaceContextMessages['workspaceContext.newWorktree'].en, 'New local worktree')
assert.equal(workspaceContextMessages['workspaceContext.copyProjectPath'].zh, '复制项目地址')
assert.equal(workspaceContextMessages['workspaceContext.copyProjectPath'].en, 'Copy project path')
assert.match(workspacePicker, /v-if="!locked" class="mode-options"/)
assert.match(workspacePicker, /copy\('workspaceContext\.newWorktreeHint'\)/)
assert.match(workspaceContextMessages['workspaceContext.newWorktreeHint'].zh, /暂不创建新分支/)
assert.match(workspaceContextMessages['workspaceContext.newWorktreeHint'].en, /no branch is created yet/)
assert.match(workspacePicker, /max-height: calc\(50vh - 24px\)/)
assert.doesNotMatch(workspacePicker, /<GitBranchSelector/)
assert.match(branchPicker, /<GitBranchSelector/)
assert.match(branchPicker, /branchContextMessages\.noBranch\[props\.locale\]\(sourceLabel\.value\)/)
assert.equal(branchContextMessages.noBranch.zh('main'), '基于 main · 未建分支')
assert.equal(branchContextMessages.noBranch.en('main'), 'Based on main · no branch')
assert.match(draftContext, /<WorkspaceContextPicker/)
assert.match(draftContext, /<BranchContextPicker/)

const codeRuntime = readFileSync('src/composables/code/useDshCodeRuntime.ts', 'utf8')
assert.match(codeRuntime, /workspace: null, session: null, worktree: false, sourceRef: ''/)
assert.match(codeRuntime, /session\.source_workspace_id/)
assert.match(codeRuntime, /state\.sourceRef \|\| 'HEAD'/)
assert.match(codeRuntime, /stopping: false/)
assert.match(codeRuntime, /result\.runtime_recovered/)
assert.match(codeRuntime, /await unsubscribeDshCodeEvents/)
assert.match(codeRuntime, /await ensureSubscribed\(entry\)/)

// Empty sessions keep Code context above the composer; once messages exist,
// App moves the same component into the window toolbar.
const desktopChrome = readFileSync('src/components/desktop/DesktopWindowChrome.vue', 'utf8')
const desktopPrimaryNavigation = readFileSync('src/components/desktop/DesktopPrimaryNavigation.vue', 'utf8')
const loginModal = readFileSync('src/components/LoginModal.vue', 'utf8')
const chatComposer = readFileSync('src/components/chat/ChatComposer.vue', 'utf8')
const composerAttachmentMenu = readFileSync('src/components/chat/ComposerAttachmentMenu.vue', 'utf8')
const chatWindow = readFileSync('src/components/ChatWindow.vue', 'utf8')
const assistantMessageBody = readFileSync('src/components/chat/AssistantMessageBody.vue', 'utf8')
const assistantMarkdown = readFileSync('src/components/chat/AssistantMarkdown.vue', 'utf8')
const appShell = readFileSync('src/App.vue', 'utf8')
const appSidebarContent = readFileSync('src/components/AppSidebarContent.vue', 'utf8')
const appSidebarBindings = readFileSync('src/composables/useAppSidebarBindings.ts', 'utf8')
const appDesktopNavigation = readFileSync('src/components/desktop/AppDesktopNavigation.vue', 'utf8')
const accountDialogs = readFileSync('src/components/AppAccountDialogs.vue', 'utf8')
const appChatPane = readFileSync('src/components/AppChatPane.vue', 'utf8')
const appChatPanes = readFileSync('src/components/AppChatPanes.vue', 'utf8')
const accountMenu = readFileSync('src/components/AccountMenu.vue', 'utf8')
const sessionHistorySidebar = readFileSync('src/components/SessionHistorySidebar.vue', 'utf8')
const sidebarHistory = readFileSync('src/composables/useSidebarHistory.ts', 'utf8')
const communityProduct = readFileSync('src/product/community.ts', 'utf8')
assert.match(desktopChrome, /<WorkspaceContextPicker/)
assert.match(desktopChrome, /<BranchContextPicker/)
assert.match(desktopChrome, /chatActions && codeAvailable && showWorkspaceContext/)
assert.match(desktopChrome, /<BrowserTestButton v-if="browserAvailable && sessionId" icon-only/)
assert.match(desktopChrome, /codeAvailable && codeSessionActive && gitAvailable/)
assert.match(desktopChrome, /<GitCompareOutline/)
assert.match(desktopChrome, /<FolderOpenOutline/)
assert.match(desktopChrome, /<TerminalOutline/)
assert.match(desktopChrome, /--desktop-navigation-width/)
assert.match(desktopChrome, /compact-navigation:not\(\.desktop-window-chrome--windows\)/)
assert.match(desktopChrome, /--windows\.desktop-window-chrome--compact-navigation \.desktop-window-chrome__brand \{/)
assert.match(desktopChrome, /windowsTitleBar && \(navigationWidth \|\| 260\) <= 64 \? 'MOVO' : ''/)
assert.match(desktopChrome, /:global\(html\.theme-dark \.desktop-window-chrome__content\)/)
assert.match(desktopPrimaryNavigation, /'home' \| 'scheduled' \| 'skills' \| 'plugins' \| 'tools' \| 'knowledge'/)
assert.match(desktopPrimaryNavigation, /:aria-current=/)
assert.match(desktopPrimaryNavigation, /@click="emit\('navigate', item\.id\)"/)
assert.match(desktopPrimaryNavigation, /:data-tooltip=/)
assert.match(desktopPrimaryNavigation, /html\.platform-desktop\.theme-dark/)
assert.match(desktopPrimaryNavigation, /width: 52px/)
assert.doesNotMatch(desktopPrimaryNavigation, /desktop-primary-nav__label/)
assert.match(desktopPrimaryNavigation, /desktop-primary-nav__account/)
assert.match(desktopPrimaryNavigation, /--desktop-nav-avatar-border/)
assert.match(appShell, /@account="toggleUserMenu"/)
assert.match(appShell, /<AppSidebarContent/)
assert.match(appSidebarContent, /<AccountMenu/)
assert.match(accountMenu, /<Teleport to="body">/)
assert.match(loginModal, /login-modal-backdrop/)
assert.match(loginModal, /html\.platform-desktop\.theme-dark \.login-modal-panel/)
assert.match(chatComposer, /class="composer-footer/)
assert.match(chatComposer, /<ComposerAttachmentMenu/)
assert.match(composerAttachmentMenu, /absolute bottom-9 left-0/)
assert.match(chatWindow, /<AssistantMessageBody/)
assert.match(assistantMessageBody, /v-if="message.content"/)
assert.match(assistantMarkdown, /compact: true/)
assert.match(assistantMarkdown, /\.assistant-markdown-compact :deep\(\.assistant-markdown-tree > h2\) \{ font-size: 1\.26em;/)
assert.match(chatWindow, /<ProjectWorkspacePanel/)
assert.match(chatWindow, /allowCode && isNewSessionView && capabilities\.localWorkspacePicker/)
assert.match(chatWindow, /<CodeDraftContextBar/)
assert.doesNotMatch(chatWindow, /<CodeInspector/)
assert.doesNotMatch(chatWindow, /<BrowserTestButton/)
assert.match(appShell, /:agent-policy="userProfile\?\.agentPolicy"/)
assert.match(appShell, /<AppDesktopNavigation\s+v-if="capabilities\.isDesktop"/)
assert.match(appDesktopNavigation, /<DesktopPrimaryNavigation/)
assert.match(appSidebarContent, /v-show="bindings\.visible"/)
assert.match(appSidebarBindings, /!capabilities\.isDesktop \|\| desktopSecondaryNavigationVisible\.value/)
assert.match(appSidebarBindings, /!capabilities\.isDesktop && \(canUseSkills\.value \|\| canUseTools\.value\)/)
assert.match(appShell, /:code-state-for="codeRuntime\.stateFor"/)
assert.match(appChatPanes, /:code-state="codeStateFor\(pane\.key\)"/)
assert.match(appChatPane, /pane\.stopping \|\| codeState\.stopping/)
assert.match(appShell, /useSidebarHistory\(\{/)
assert.match(sidebarHistory, /const visibleProjectHistory = computed\(\(\) => projectHistoryVisibility\(/)
assert.match(appShell, /useEnterpriseAccessPolicy\(userProfile\)/)
assert.match(appShell, /const supportsLocalCodeProjects = capabilities\.localDshRuntime && capabilities\.localWorkspacePicker/)
assert.match(sidebarHistory, /visibleProjectHistory\.value\.ordinary/)
assert.match(sidebarHistory, /visibleProjectHistory\.value\.unavailableIds\.has\(sessionId\)/)
assert.match(sessionHistorySidebar, /v-for="group in projectHistoryGroups"/)
assert.match(accountMenu, /v-if="canAccessAdmin\(tenant\)"/)
assert.match(appShell, /:can-access-billing-admin="isEnterpriseSpace && userProfile\?\.canAccessAdmin === true"/)
assert.match(accountDialogs, /:can-access-admin="canAccessBillingAdmin"/)
assert.doesNotMatch(communityProduct, /billingModal/)
assert.match(chatWindow, /:allow-knowledge="allowKnowledge"/)
assert.match(chatWindow, /:allow-skills="allowSkills"/)

console.log('Web/desktop Code capability boundary contract passed')
