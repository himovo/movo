<script setup lang="ts">
import FolderOpenOutline from '@vicons/ionicons5/es/FolderOpenOutline'
import GitCompareOutline from '@vicons/ionicons5/es/GitCompareOutline'
import TerminalOutline from '@vicons/ionicons5/es/TerminalOutline'
import BrowserTestButton from '../browser/BrowserTestButton.vue'
import DesktopUpdateIndicator from './DesktopUpdateIndicator.vue'
import WorkspaceContextPicker from '../code/WorkspaceContextPicker.vue'
import BranchContextPicker from '../code/BranchContextPicker.vue'
import type { DshWorkspace } from '../../platform/types'
import type { DesktopToolTabKind } from './desktopToolTabs'

defineProps<{
  title: string
  chatActions?: boolean
  sessionId?: string
  workspace?: DshWorkspace | null
  showWorkspaceContext?: boolean
  workspaceBranch?: string
  workspaceSourceRef?: string
  workspaceDetached?: boolean
  codeSessionActive?: boolean
  workspaceBusy?: boolean
  worktree?: boolean
  locale?: 'zh' | 'en'
  activeTool?: DesktopToolTabKind | null
  gitAvailable?: boolean
  changeCount?: number
  filesAvailable?: boolean
  terminalAvailable?: boolean
  codeAvailable?: boolean
  browserAvailable?: boolean
}>()

const emit = defineEmits<{
  (event: 'choose-workspace'): void
  (event: 'clear-workspace'): void
  (event: 'worktree', enabled: boolean): void
  (event: 'source-ref', fullRef: string): void
  (event: 'branch-updated', branch: string): void
  (event: 'open-browser'): void
  (event: 'toggle-code-panel', mode: 'changes' | 'files' | 'terminal'): void
}>()
</script>

<template>
  <header class="desktop-window-chrome" aria-label="Desktop window header">
    <div class="desktop-window-chrome__sidebar">
      <span class="desktop-window-chrome__brand">
        <img src="/movo-logo.png" alt="" />
        <span>MOVO</span>
      </span>
    </div>
    <div class="desktop-window-chrome__content">
      <div class="desktop-window-chrome__context">
        <div
          v-if="chatActions && codeAvailable && showWorkspaceContext"
          class="desktop-window-chrome__workspace-control"
        >
          <WorkspaceContextPicker
            compact
            :workspace="workspace || null"
            :locked="codeSessionActive"
            :busy="workspaceBusy"
            :worktree="worktree"
            :locale="locale"
            @choose="emit('choose-workspace')"
            @clear="emit('clear-workspace')"
            @worktree="(enabled) => emit('worktree', enabled)"
          />
        </div>
        <div
          v-if="chatActions && codeAvailable && showWorkspaceContext && workspace"
          class="desktop-window-chrome__branch-control"
        >
          <BranchContextPicker
            compact
            :workspace="workspace"
            :locked="codeSessionActive"
            :busy="workspaceBusy"
            :worktree="worktree"
            :detached="workspaceDetached"
            :branch="workspaceBranch"
            :source-ref="workspaceSourceRef"
            :locale="locale"
            @source-ref="(fullRef) => emit('source-ref', fullRef)"
            @branch-updated="(branch) => emit('branch-updated', branch)"
          />
        </div>
        <span class="desktop-window-chrome__title" :title="title">{{ title }}</span>
      </div>
      <div class="desktop-window-chrome__actions">
        <DesktopUpdateIndicator />
        <template v-if="chatActions">
          <button
            v-if="codeAvailable && codeSessionActive && gitAvailable"
            type="button"
            class="desktop-window-chrome__icon-button"
            :class="{ active: activeTool === 'changes' }"
            :aria-label="locale === 'en' ? 'Open changes' : '打开变更'"
            :title="locale === 'en' ? 'Changes' : '变更'"
            @click="emit('toggle-code-panel', 'changes')"
          >
            <GitCompareOutline /><span v-if="changeCount" class="desktop-window-chrome__badge">{{ changeCount > 99 ? '99+' : changeCount }}</span>
          </button>
          <button
            v-if="codeAvailable && codeSessionActive && filesAvailable"
            type="button"
            class="desktop-window-chrome__icon-button"
            :class="{ active: activeTool === 'files' }"
            :aria-label="locale === 'en' ? 'Open files' : '打开文件'"
            :title="locale === 'en' ? 'Files' : '文件'"
            @click="emit('toggle-code-panel', 'files')"
          ><FolderOpenOutline /></button>
          <button
            v-if="codeAvailable && codeSessionActive && terminalAvailable"
            type="button"
            class="desktop-window-chrome__icon-button"
            :class="{ active: activeTool === 'terminal' }"
            :aria-label="locale === 'en' ? 'Open terminal' : '打开终端'"
            :title="locale === 'en' ? 'Terminal' : '终端'"
            @click="emit('toggle-code-panel', 'terminal')"
          >
            <TerminalOutline />
          </button>
          <BrowserTestButton v-if="browserAvailable && sessionId" icon-only :active="activeTool === 'browser'" :session-id="sessionId" @open="emit('open-browser')" />
        </template>
      </div>
    </div>
  </header>
</template>

<style scoped>
.desktop-window-chrome {
  position: absolute;
  inset: 0 0 auto 0;
  z-index: 40;
  display: grid;
  grid-template-columns: 260px minmax(0, 1fr);
  height: 48px;
  color: #475569;
  -webkit-app-region: drag;
  user-select: none;
}

.desktop-window-chrome__sidebar,
.desktop-window-chrome__content {
  display: flex;
  min-width: 0;
  align-items: center;
  border-bottom: 1px solid #e5e7eb;
}

.desktop-window-chrome__sidebar {
  border-right: 1px solid #e5e7eb;
  background: #f8fafc;
  padding: 0 14px 0 86px;
}

.desktop-window-chrome__content {
  justify-content: space-between;
  background: rgba(255, 255, 255, 0.96);
  padding: 0 14px 0 12px;
}

.desktop-window-chrome__context,
.desktop-window-chrome__actions {
  display:flex;
  min-width:0;
  align-items:center;
}

.desktop-window-chrome__context {
  flex: 1;
  align-self: stretch;
  gap: 7px;
  -webkit-app-region: drag;
}

.desktop-window-chrome__workspace-control,
.desktop-window-chrome__branch-control,
.desktop-window-chrome__actions {
  -webkit-app-region: no-drag;
}

.desktop-window-chrome__workspace-control,
.desktop-window-chrome__branch-control { flex: none; }
.desktop-window-chrome__actions { flex:none; gap:4px; margin-left:auto; }

.desktop-window-chrome__brand {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  overflow: hidden;
  color: #334155;
  font-size: 13px;
  font-weight: 700;
  letter-spacing: 0.04em;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.desktop-window-chrome__brand img {
  display: block;
  width: 25px;
  height: 21px;
  object-fit: contain;
}

.desktop-window-chrome__title {
  flex: 1;
  overflow: hidden;
  color: #334155;
  font-size: 13px;
  font-weight: 600;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.desktop-window-chrome__icon-button { position:relative; display:grid; width:36px; height:36px; place-items:center; border:0; border-radius:9px; background:transparent; color:#475569; cursor:pointer; transition:background-color 160ms ease,color 160ms ease; }
.desktop-window-chrome__icon-button:hover:not(:disabled) { background:#f1f5f9; color:#2563eb; }
.desktop-window-chrome__icon-button.active { background:#eaf2ff; color:#2563eb; }
.desktop-window-chrome__icon-button:focus-visible { outline:2px solid #bfdbfe; outline-offset:1px; }
.desktop-window-chrome__icon-button:disabled { cursor:default; opacity:.35; }
.desktop-window-chrome__icon-button svg { width:18px; height:18px; }
.desktop-window-chrome__badge { position:absolute; top:1px; right:1px; min-width:14px; height:14px; border:1px solid #fff; border-radius:7px; background:#2563eb; padding:0 3px; color:#fff; font-size:8px; line-height:12px; }

:global(html.theme-dark) .desktop-window-chrome__sidebar {
  border-color: #334155;
  background: #0b1220;
}

:global(html.theme-dark) .desktop-window-chrome__content {
  border-color: #334155;
  background: rgba(17, 24, 39, 0.96);
}

:global(html.theme-dark) .desktop-window-chrome__brand,
:global(html.theme-dark) .desktop-window-chrome__title {
  color: #e2e8f0;
}

:global(html.theme-dark) .desktop-window-chrome__icon-button { color:#94a3b8; }
:global(html.theme-dark) .desktop-window-chrome__icon-button:hover:not(:disabled) { background:#1e293b; color:#93c5fd; }

@media (max-width: 1100px) {
  .desktop-window-chrome {
    grid-template-columns: 220px minmax(0, 1fr);
  }
}
</style>
