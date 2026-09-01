<script setup lang="ts">
import { ref, watch } from 'vue'
import type { DshCodeSession } from '../../platform/types'
import DesktopToolTabBar from '../desktop/DesktopToolTabBar.vue'
import type { DesktopToolTab, DesktopToolTabKind } from '../desktop/desktopToolTabs'
import ProjectTerminal from './ProjectTerminal.vue'
import WorkspaceChanges from './WorkspaceChanges.vue'
import TaskChangeReview from './TaskChangeReview.vue'
import WorkspaceFileBrowser from './WorkspaceFileBrowser.vue'
import type { DshTaskChangeSet } from '../../platform/types'
import { useDesktopToolPanelSize } from '../../composables/desktop/useDesktopToolPanelSize'

export type ProjectPanelMode = 'changes' | 'files' | 'terminal'
const props = defineProps<{ session: DshCodeSession; mode: ProjectPanelMode; tabs: DesktopToolTab[]; availableTabs: DesktopToolTabKind[]; locale?: 'zh' | 'en'; running?: boolean; reviewPath?: string; reviewChanges?: DshTaskChangeSet | null; filePath?: string }>()
const emit = defineEmits<{ (event: 'close'): void; (event: 'workspace-change'): void; (event: 'select-tab', kind: DesktopToolTabKind): void; (event: 'close-tab', kind: DesktopToolTabKind): void; (event: 'open-tab', kind: DesktopToolTabKind): void }>()
const panel = useDesktopToolPanelSize()
const openedModes = ref(new Set<ProjectPanelMode>([props.mode]))
watch(() => props.mode, mode => {
  openedModes.value = new Set([...openedModes.value, mode])
})
</script>

<template>
  <aside class="project-panel" :class="{ dragging: panel.dragging.value }" :style="{ width: panel.width.value }">
    <button type="button" class="resize-handle" :aria-label="locale === 'en' ? 'Resize panel' : '调整面板宽度'" @pointerdown="panel.beginDrag" @keydown="panel.adjustByKeyboard"></button>
    <DesktopToolTabBar :tabs="tabs" :active="mode" :available="availableTabs" :locale="locale" @select="emit('select-tab', $event)" @close="emit('close-tab', $event)" @open="emit('open-tab', $event)" @close-panel="emit('close')" />
    <div class="panel-body">
      <TaskChangeReview v-if="openedModes.has('changes') && mode === 'changes' && reviewChanges" :session-id="session.kernel_session_id" :changes="reviewChanges" :locale="locale" :requested-path="reviewPath" />
      <WorkspaceChanges v-else-if="openedModes.has('changes')" v-show="mode === 'changes'" :session-id="session.kernel_session_id" :locale="locale" :running="running" :requested-path="reviewPath" @committed="emit('workspace-change')" />
      <WorkspaceFileBrowser v-if="openedModes.has('files')" v-show="mode === 'files'" :session-id="session.kernel_session_id" :locale="locale" :requested-path="filePath" />
      <ProjectTerminal v-if="openedModes.has('terminal')" v-show="mode === 'terminal'" :session-id="session.kernel_session_id" />
    </div>
  </aside>
</template>

<style scoped>
.project-panel{position:relative;display:flex;min-width:520px;max-width:82vw;height:100%;flex:none;flex-direction:column;border-left:1px solid #dbe3ee;background:#fbfcfe;box-shadow:-8px 0 24px #0f172a0a}.resize-handle{position:absolute;z-index:5;top:0;bottom:0;left:-4px;width:8px;border:0;background:transparent;cursor:col-resize}.resize-handle:hover{background:#3b82f633}.panel-body{min-height:0;flex:1}@media(max-width:900px){.project-panel{position:absolute;z-index:55;inset:0 0 0 auto;min-width:0;width:min(100%,720px)!important;max-width:100%;box-shadow:-12px 0 32px #0f172a26}}
</style>
