<script setup lang="ts">
import { computed, ref } from 'vue'
import AddOutline from '@vicons/ionicons5/es/AddOutline'
import CloseOutline from '@vicons/ionicons5/es/CloseOutline'
import FolderOpenOutline from '@vicons/ionicons5/es/FolderOpenOutline'
import GitCompareOutline from '@vicons/ionicons5/es/GitCompareOutline'
import GlobeOutline from '@vicons/ionicons5/es/GlobeOutline'
import TerminalOutline from '@vicons/ionicons5/es/TerminalOutline'
import DocumentTextOutline from '@vicons/ionicons5/es/DocumentTextOutline'
import type { DesktopToolLauncherKind, DesktopToolTab } from './desktopToolTabs'

const props = defineProps<{
  tabs: DesktopToolTab[]
  active?: string | null
  available: DesktopToolLauncherKind[]
  locale?: 'zh' | 'en'
}>()
const emit = defineEmits<{
  (event: 'select', id: string): void
  (event: 'close', id: string): void
  (event: 'open', kind: DesktopToolLauncherKind): void
  (event: 'close-panel'): void
}>()
const menuOpen = ref(false)
const labels: Record<DesktopToolLauncherKind, { zh: string; en: string }> = {
  browser: { zh: '浏览器', en: 'Browser' },
  changes: { zh: '变更', en: 'Changes' },
  files: { zh: '文件', en: 'Files' },
  terminal: { zh: '终端', en: 'Terminal' },
}
const choices = computed(() => props.available.filter(kind => kind === 'terminal' || !props.tabs.some(tab => tab.kind === kind)))
function label(kind: DesktopToolLauncherKind): string { return labels[kind][props.locale === 'en' ? 'en' : 'zh'] }
function open(kind: DesktopToolLauncherKind): void { menuOpen.value = false; emit('open', kind) }
function navigate(event: KeyboardEvent, index: number): void {
  if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key) || !props.tabs.length) return
  event.preventDefault()
  const target = event.key === 'Home' ? 0 : event.key === 'End' ? props.tabs.length - 1 : (index + (event.key === 'ArrowLeft' ? -1 : 1) + props.tabs.length) % props.tabs.length
  emit('select', props.tabs[target].id)
}
</script>

<template>
  <header class="tool-tab-bar">
    <div class="tool-tab-scroll" role="tablist" :aria-label="locale === 'en' ? 'Workspace tools' : '工作区工具'">
      <div v-for="(tab, index) in tabs" :key="tab.id" class="tool-tab" :class="{ active: active === tab.id }" @auxclick.middle.prevent="emit('close', tab.id)">
        <button type="button" role="tab" class="tool-tab-select" :aria-selected="active === tab.id" :tabindex="active === tab.id ? 0 : -1" @click="emit('select', tab.id)" @keydown="navigate($event, index)">
          <GlobeOutline v-if="tab.kind === 'browser'" />
          <GitCompareOutline v-else-if="tab.kind === 'changes'" />
          <FolderOpenOutline v-else-if="tab.kind === 'files'" />
          <TerminalOutline v-else-if="tab.kind === 'terminal'" />
          <GitCompareOutline v-else-if="tab.kind === 'diff'" />
          <DocumentTextOutline v-else />
          <span :title="tab.resource?.path || tab.title">{{ tab.title }}</span>
        </button>
        <button type="button" class="tab-close" :aria-label="`${locale === 'en' ? 'Close' : '关闭'} ${tab.title}`" @click="emit('close', tab.id)"><CloseOutline /></button>
      </div>
    </div>
    <div class="tool-tab-actions">
      <div v-if="choices.length" class="new-tab-wrap">
        <button type="button" class="new-tab" :aria-label="locale === 'en' ? 'New tool tab' : '新建工具标签页'" :title="locale === 'en' ? 'New tab' : '新建标签页'" @click="menuOpen = !menuOpen"><AddOutline /></button>
        <div v-if="menuOpen" class="new-tab-menu">
          <button v-for="kind in choices" :key="kind" type="button" @click="open(kind)">{{ label(kind) }}</button>
        </div>
      </div>
      <button type="button" class="panel-close" :aria-label="locale === 'en' ? 'Close tool panel' : '关闭工具面板'" @click="emit('close-panel')"><CloseOutline /></button>
    </div>
  </header>
</template>

<style scoped>
.tool-tab-bar{position:relative;display:flex;height:44px;flex:none;align-items:stretch;border-bottom:1px solid #e2e8f0;background:#f8fafc;padding-left:7px}.tool-tab-scroll{display:flex;min-width:0;flex:1;align-items:end;gap:2px;overflow-x:auto;overflow-y:hidden;scrollbar-width:thin}.tool-tab-actions{position:relative;display:flex;flex:none;align-items:center;padding:0 7px 0 3px;background:#f8fafc}.tool-tab{display:flex;min-width:104px;max-width:180px;height:36px;align-items:center;border:1px solid transparent;border-bottom:0;border-radius:8px 8px 0 0;background:transparent;color:#64748b;font-size:12px}.tool-tab:hover{background:#eef2f7;color:#334155}.tool-tab.active{border-color:#e2e8f0;background:#fff;color:#1d4ed8}.tool-tab-select{display:flex;min-width:0;flex:1;align-items:center;gap:6px;border:0;background:transparent;padding:0 2px 0 9px;color:inherit;font:inherit;cursor:pointer}.tool-tab-select>svg{width:15px;flex:none}.tool-tab-select>span{overflow:hidden;flex:1;text-align:left;text-overflow:ellipsis;white-space:nowrap}.tab-close{display:grid;width:28px;height:28px;flex:none;place-items:center;border:0;border-radius:5px;background:transparent;color:inherit;cursor:pointer}.tab-close:hover{background:#e2e8f0;color:#0f172a}.tab-close svg{width:13px}.new-tab-wrap{position:relative;display:flex;align-items:center}.new-tab,.panel-close{display:grid;width:36px;height:36px;place-items:center;border:0;border-radius:7px;background:transparent;color:#64748b;cursor:pointer}.new-tab:hover,.panel-close:hover{background:#e2e8f0;color:#0f172a}.new-tab svg,.panel-close svg{width:17px}.new-tab-menu{position:absolute;z-index:80;top:38px;right:0;display:grid;min-width:132px;overflow:hidden;border:1px solid #dbe3ee;border-radius:9px;background:#fff;padding:4px;box-shadow:0 10px 28px #0f172a24}.new-tab-menu button{min-height:36px;border:0;border-radius:6px;background:transparent;padding:8px 10px;text-align:left;color:#334155;font-size:12px;cursor:pointer}.new-tab-menu button:hover{background:#eff6ff;color:#1d4ed8}.tool-tab-select:focus-visible,.new-tab:focus-visible,.panel-close:focus-visible,.tab-close:focus-visible{outline:2px solid #93c5fd;outline-offset:1px}.panel-close{margin-left:2px}
@media(max-width:620px){.tool-tab{min-width:44px;width:44px}.tool-tab-select{justify-content:center;padding:0}.tool-tab-select>span,.tab-close{display:none}}
</style>
