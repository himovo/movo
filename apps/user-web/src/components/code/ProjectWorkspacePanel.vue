<script setup lang="ts">
import type { DshCodeSession } from '../../platform/types'
import DesktopToolTabBar from '../desktop/DesktopToolTabBar.vue'
import type { DesktopToolLauncherKind, DesktopToolTab } from '../desktop/desktopToolTabs'
import ProjectTerminal from './ProjectTerminal.vue'
import WorkspaceChanges from './WorkspaceChanges.vue'
import TaskChangeReview from './TaskChangeReview.vue'
import WorkspaceFileBrowser from './WorkspaceFileBrowser.vue'
import WorkspaceFilePreview from './WorkspaceFilePreview.vue'
import WorkspaceDiffPreview from './WorkspaceDiffPreview.vue'
import type { DshTaskChangeSet } from '../../platform/types'
import { useDesktopToolPanelSize } from '../../composables/desktop/useDesktopToolPanelSize'

export type ProjectPanelMode = 'changes' | 'files' | 'terminal' | 'file' | 'diff'
const props = defineProps<{ session: DshCodeSession; activeId: string; tabs: DesktopToolTab[]; availableTabs: DesktopToolLauncherKind[]; locale?: 'zh' | 'en'; running?: boolean; reviewPath?: string; reviewChanges?: DshTaskChangeSet | null; filePath?: string }>()
const emit = defineEmits<{ (event: 'close'): void; (event: 'workspace-change'): void; (event: 'select-tab', id: string): void; (event: 'close-tab', id: string): void; (event: 'open-tab', kind: DesktopToolLauncherKind): void; (event: 'open-file', path: string): void; (event: 'open-diff', path: string, changes?: DshTaskChangeSet): void }>()
const panel = useDesktopToolPanelSize()
</script>

<template>
  <aside class="project-panel" :class="{ dragging: panel.dragging.value }" :style="{ width: panel.width.value }">
    <button type="button" class="resize-handle" :aria-label="locale === 'en' ? 'Resize panel' : '调整面板宽度'" @pointerdown="panel.beginDrag" @keydown="panel.adjustByKeyboard"></button>
    <DesktopToolTabBar :tabs="tabs" :active="activeId" :available="availableTabs" :locale="locale" @select="emit('select-tab', $event)" @close="emit('close-tab', $event)" @open="emit('open-tab', $event)" @close-panel="emit('close')" />
    <div class="panel-body">
      <template v-for="tab in tabs" :key="tab.id">
        <TaskChangeReview v-if="tab.kind === 'changes' && reviewChanges" v-show="activeId === tab.id" :session-id="session.kernel_session_id" :changes="reviewChanges" :locale="locale" :requested-path="reviewPath" @open-diff="emit('open-diff', $event, reviewChanges)" />
        <WorkspaceChanges v-else-if="tab.kind === 'changes'" v-show="activeId === tab.id" :session-id="session.kernel_session_id" :locale="locale" :running="running" :requested-path="reviewPath" @committed="emit('workspace-change')" @open-diff="emit('open-diff', $event)" />
        <WorkspaceFileBrowser v-else-if="tab.kind === 'files'" v-show="activeId === tab.id" :session-id="session.kernel_session_id" :locale="locale" :requested-path="filePath" @open-file="emit('open-file', $event)" />
        <ProjectTerminal v-else-if="tab.kind === 'terminal'" v-show="activeId === tab.id" :session-id="session.kernel_session_id" />
        <WorkspaceFilePreview v-else-if="tab.kind === 'file' && tab.resource?.path" v-show="activeId === tab.id" :session-id="session.kernel_session_id" :path="tab.resource.path" :locale="locale" />
        <WorkspaceDiffPreview v-else-if="tab.kind === 'diff' && tab.resource?.path" v-show="activeId === tab.id" :session-id="session.kernel_session_id" :path="tab.resource.path" :task-changes="tab.resource.taskChanges" :locale="locale" />
      </template>
    </div>
  </aside>
</template>

<style scoped>
.project-panel{position:relative;display:flex;min-width:520px;max-width:82vw;height:100%;flex:none;flex-direction:column;border-left:1px solid #dbe3ee;background:#fbfcfe;box-shadow:-8px 0 24px #0f172a0a}.resize-handle{position:absolute;z-index:5;top:0;bottom:0;left:-4px;width:8px;border:0;background:transparent;cursor:col-resize}.resize-handle:hover{background:#3b82f633}.panel-body{min-height:0;flex:1}@media(max-width:900px){.project-panel{position:absolute;z-index:55;inset:0 0 0 auto;min-width:0;width:min(100%,720px)!important;max-width:100%;box-shadow:-12px 0 32px #0f172a26}}
</style>
