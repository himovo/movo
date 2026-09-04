<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import ElectronBrowserSurface from './ElectronBrowserSurface.vue'
import BrowserMiniView from './BrowserMiniView.vue'
import DesktopToolTabBar from '../desktop/DesktopToolTabBar.vue'
import type { DesktopToolLauncherKind, DesktopToolTab, DesktopToolTabKind } from '../desktop/desktopToolTabs'
import { capabilities } from '../../platform'
import { useDesktopToolPanelSize } from '../../composables/desktop/useDesktopToolPanelSize'
import { useEmbeddedBrowserState } from '../../composables/browser/embeddedBrowserState'
import { t } from '../../composables/i18n'

const props = defineProps<{
  active: boolean
  open: boolean
  sessionId?: string
  userId?: string
  mainId?: string
  enabled?: boolean
  tabs?: DesktopToolTab[]
  activeTool?: string | null
  activeKind?: DesktopToolTabKind | null
  availableTools?: DesktopToolLauncherKind[]
  locale?: 'zh' | 'en'
}>()
const emit = defineEmits<{
  (event: 'update:open', value: boolean): void
  (event: 'select-tab', id: string): void
  (event: 'close-tab', id: string): void
  (event: 'open-tab', kind: DesktopToolLauncherKind): void
}>()
const panel = useDesktopToolPanelSize()
const embeddedState = useEmbeddedBrowserState()
const sessionMatches = computed(() => Boolean(
  props.sessionId
  && embeddedState.value.session_id === props.sessionId,
))
const useElectron = computed(() => capabilities.embeddedBrowser
  && props.active
  && embeddedState.value.active
  && sessionMatches.value)
const hasPreview = computed(() => useElectron.value)
const panelOpen = computed(() => props.enabled !== false && props.active && props.open && props.activeKind === 'browser' && hasPreview.value)
const dismissedSession = ref('')
const miniVisible = computed(() => Boolean(
  useElectron.value
  && !panelOpen.value
  && props.sessionId
  && dismissedSession.value !== props.sessionId
  && embeddedState.value.url
  && embeddedState.value.url !== 'about:blank',
))

watch(() => props.sessionId, (sessionId, previous) => {
  if (sessionId !== previous) dismissedSession.value = ''
})
watch(useElectron, (active, previous) => {
  if (active && previous === false) dismissedSession.value = ''
})

function expandBrowser() {
  emit('open-tab', 'browser')
}

function closeMiniView() {
  dismissedSession.value = props.sessionId || ''
}

</script>

<template>
  <div class="browser-workspace" :class="{ dragging: panel.dragging.value }">
    <div class="chat-pane"><slot /></div>
    <BrowserMiniView
      v-if="miniVisible && sessionId"
      :session-id="sessionId"
      :active="miniVisible"
      :title="embeddedState.title"
      :url="embeddedState.url"
      :loading="embeddedState.loading"
      :owner="embeddedState.owner"
      :locale="locale"
      @expand="expandBrowser"
      @close="closeMiniView"
    />
    <template v-if="panelOpen">
      <div
        class="split-handle"
        role="separator"
        :aria-label="t('调整对话和浏览器宽度')"
        aria-orientation="vertical"
        tabindex="0"
        @pointerdown="panel.beginDrag"
        @keydown="panel.adjustByKeyboard"
      ><span></span></div>
      <aside class="browser-pane" :style="{ width: panel.width.value }">
        <DesktopToolTabBar
          :tabs="tabs || []"
          :active="activeTool"
          :available="availableTools || []"
          :locale="locale"
          @select="emit('select-tab', $event)"
          @close="emit('close-tab', $event)"
          @open="emit('open-tab', $event)"
          @close-panel="emit('update:open', false)"
        />
        <ElectronBrowserSurface
          :session-id="sessionId"
          :user-id="userId"
          :main-id="mainId"
          :show-panel-close="false"
        />
      </aside>
    </template>
  </div>
</template>

<style scoped>
.browser-workspace { position: relative; display: flex; width: 100%; height: 100%; min-width: 0; overflow: hidden; background: white; }
.browser-workspace.dragging { user-select: none; cursor: col-resize; }
.chat-pane, .browser-pane { height: 100%; min-width: 0; }
.chat-pane { flex:1; }
.browser-pane { display:flex; max-width:82vw; flex:none; flex-direction:column; border-left: 1px solid #cbd5e1; background: #0f172a; }
.browser-pane :deep(.electron-browser) { min-height:0; flex:1; }
.split-handle { position: relative; z-index: 20; width: 7px; flex: 0 0 7px; cursor: col-resize; background: #f8fafc; outline: none; }
.split-handle span { position: absolute; top: 50%; left: 2px; width: 3px; height: 36px; transform: translateY(-50%); border-radius: 2px; background: #cbd5e1; }
.split-handle:hover span, .split-handle:focus-visible span { background: #2563eb; }
@media (max-width: 900px) {
  .browser-workspace { display: block; }
  .chat-pane { width: 100% !important; }
  .split-handle { display: none; }
  .browser-pane { position: absolute; inset: 0; z-index: 30; width: 100% !important; }
}
</style>
