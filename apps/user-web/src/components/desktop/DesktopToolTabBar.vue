<script setup lang="ts">
import { computed, ref } from 'vue'
import AddOutline from '@vicons/ionicons5/es/AddOutline'
import CloseOutline from '@vicons/ionicons5/es/CloseOutline'
import FolderOpenOutline from '@vicons/ionicons5/es/FolderOpenOutline'
import GitCompareOutline from '@vicons/ionicons5/es/GitCompareOutline'
import GlobeOutline from '@vicons/ionicons5/es/GlobeOutline'
import TerminalOutline from '@vicons/ionicons5/es/TerminalOutline'
import type { DesktopToolTab, DesktopToolTabKind } from './desktopToolTabs'

const props = defineProps<{
  tabs: DesktopToolTab[]
  active?: DesktopToolTabKind | null
  available: DesktopToolTabKind[]
  locale?: 'zh' | 'en'
}>()
const emit = defineEmits<{
  (event: 'select', kind: DesktopToolTabKind): void
  (event: 'close', kind: DesktopToolTabKind): void
  (event: 'open', kind: DesktopToolTabKind): void
  (event: 'close-panel'): void
}>()
const menuOpen = ref(false)
const labels: Record<DesktopToolTabKind, { zh: string; en: string }> = {
  browser: { zh: '浏览器', en: 'Browser' },
  changes: { zh: '变更', en: 'Changes' },
  files: { zh: '文件', en: 'Files' },
  terminal: { zh: '终端', en: 'Terminal' },
}
const choices = computed(() => props.available.filter(kind => !props.tabs.some(tab => tab.kind === kind)))
function label(kind: DesktopToolTabKind): string { return labels[kind][props.locale === 'en' ? 'en' : 'zh'] }
function open(kind: DesktopToolTabKind): void { menuOpen.value = false; emit('open', kind) }
</script>

<template>
  <header class="tool-tab-bar">
    <div class="tool-tab-list" role="tablist" :aria-label="locale === 'en' ? 'Workspace tools' : '工作区工具'">
      <div
        v-for="tab in tabs"
        :key="tab.id"
        class="tool-tab"
        :class="{ active: active === tab.kind }"
      >
        <button type="button" role="tab" class="tool-tab-select" :aria-selected="active === tab.kind" @click="emit('select', tab.kind)">
          <GlobeOutline v-if="tab.kind === 'browser'" />
          <GitCompareOutline v-else-if="tab.kind === 'changes'" />
          <FolderOpenOutline v-else-if="tab.kind === 'files'" />
          <TerminalOutline v-else />
          <span>{{ label(tab.kind) }}</span>
        </button>
        <button type="button" class="tab-close" :aria-label="`${locale === 'en' ? 'Close' : '关闭'} ${label(tab.kind)}`" @click="emit('close', tab.kind)"><CloseOutline /></button>
      </div>
      <div v-if="choices.length" class="new-tab-wrap">
        <button type="button" class="new-tab" :aria-label="locale === 'en' ? 'New tool tab' : '新建工具标签页'" :title="locale === 'en' ? 'New tab' : '新建标签页'" @click="menuOpen = !menuOpen"><AddOutline /></button>
        <div v-if="menuOpen" class="new-tab-menu">
          <button v-for="kind in choices" :key="kind" type="button" @click="open(kind)">{{ label(kind) }}</button>
        </div>
      </div>
    </div>
    <button type="button" class="panel-close" :aria-label="locale === 'en' ? 'Close tool panel' : '关闭工具面板'" @click="emit('close-panel')"><CloseOutline /></button>
  </header>
</template>

<style scoped>
.tool-tab-bar{position:relative;display:flex;height:42px;flex:none;align-items:stretch;justify-content:space-between;border-bottom:1px solid #e2e8f0;background:#f8fafc;padding:0 7px}.tool-tab-list{display:flex;min-width:0;align-items:end;gap:2px;overflow:visible}.tool-tab{display:flex;min-width:92px;max-width:150px;height:34px;align-items:center;border:1px solid transparent;border-bottom:0;border-radius:8px 8px 0 0;background:transparent;color:#64748b;font-size:12px}.tool-tab:hover{background:#eef2f7;color:#334155}.tool-tab.active{border-color:#e2e8f0;background:#fff;color:#1d4ed8}.tool-tab-select{display:flex;min-width:0;flex:1;align-items:center;gap:6px;border:0;background:transparent;padding:0 2px 0 9px;color:inherit;font:inherit;cursor:pointer}.tool-tab-select>svg{width:15px;flex:none}.tool-tab-select>span{overflow:hidden;flex:1;text-align:left;text-overflow:ellipsis;white-space:nowrap}.tab-close{display:grid;width:25px;height:25px;flex:none;place-items:center;border:0;border-radius:5px;background:transparent;color:inherit;cursor:pointer}.tab-close:hover{background:#e2e8f0;color:#0f172a}.tab-close svg{width:13px}.new-tab-wrap{position:relative;display:flex;align-items:center}.new-tab,.panel-close{display:grid;width:32px;height:32px;place-items:center;border:0;border-radius:7px;background:transparent;color:#64748b;cursor:pointer}.new-tab:hover,.panel-close:hover{background:#e2e8f0;color:#0f172a}.new-tab svg,.panel-close svg{width:17px}.new-tab-menu{position:absolute;z-index:80;top:37px;left:0;display:grid;min-width:132px;overflow:hidden;border:1px solid #dbe3ee;border-radius:9px;background:#fff;padding:4px;box-shadow:0 10px 28px #0f172a24}.new-tab-menu button{border:0;border-radius:6px;background:transparent;padding:8px 10px;text-align:left;color:#334155;font-size:12px;cursor:pointer}.new-tab-menu button:hover{background:#eff6ff;color:#1d4ed8}.tool-tab-select:focus-visible,.new-tab:focus-visible,.panel-close:focus-visible,.tab-close:focus-visible{outline:2px solid #93c5fd;outline-offset:1px}.panel-close{align-self:center;margin-left:6px}
@media(max-width:620px){.tool-tab{min-width:44px;width:44px}.tool-tab-select{justify-content:center;padding:0}.tool-tab-select>span,.tab-close{display:none}}
</style>
