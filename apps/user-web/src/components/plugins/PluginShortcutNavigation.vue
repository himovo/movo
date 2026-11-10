<template>
  <section v-if="shortcuts.length" class="plugin-shortcuts">
    <button type="button" class="shortcut-heading" :aria-expanded="expanded" @click="expanded = !expanded">
      <span>{{ t('plugins.shortcuts') }}</span>
      <svg class="heading-arrow" :class="{ expanded }" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><path d="m5 3 5 5-5 5"/></svg>
    </button>
    <div v-if="expanded" class="shortcut-items">
      <button v-for="plugin in shortcuts.slice(0, 3)" :key="plugin.id" type="button" class="shortcut-item" :title="plugin.name" :disabled="openingId === plugin.id" @click="open(plugin)">
        <n-icon :component="DesktopOutline" /><span>{{ plugin.name }}</span>
      </button>
      <n-popover v-if="shortcuts.length > 3" trigger="hover" placement="right-start" :show-arrow="false">
        <template #trigger>
          <button type="button" class="shortcut-item shortcut-more" :aria-label="t('plugins.moreShortcuts', { count: shortcuts.length - 3 })">
            <span>{{ t('plugins.moreShortcuts', { count: shortcuts.length - 3 }) }}</span>
            <n-icon :component="ChevronForwardOutline" />
          </button>
        </template>
        <div class="overflow-items">
          <button v-for="plugin in shortcuts.slice(3)" :key="plugin.id" type="button" :disabled="openingId === plugin.id" @click="open(plugin)">{{ plugin.name }}</button>
        </div>
      </n-popover>
    </div>
    <PluginUiDrawer v-model:show="uiOpen" :name="uiName" :url="uiUrl" />
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { NIcon, NPopover, useMessage } from 'naive-ui'
import { ChevronForwardOutline, DesktopOutline } from '@vicons/ionicons5'
import { getPluginExecutionAccess, launchDshPluginUi, listDshPlugins, type DshPlugin } from '../../api/dshPlugins'
import { t } from '../../composables/i18n'
import { entryVisible } from '../../composables/useEntryVisibility'
import PluginUiDrawer from './PluginUiDrawer.vue'
import { pluginShortcutsChanged, readPluginShortcuts } from './pluginShortcuts'
import { hasStandalonePluginUi } from './pluginUiSurface'

const props = defineProps<{ mainId: string; userId: string; loggedIn: boolean; currentView: string }>()
const message = useMessage()
const expanded = ref(true)
const plugins = ref<DshPlugin[]>([])
const executionAllowed = ref(false)
const selectedIds = ref<string[]>([])
const openingId = ref('')
const uiOpen = ref(false)
const uiName = ref('')
const uiUrl = ref('')
let requestId = 0

const shortcuts = computed(() => {
  if (!props.loggedIn || !executionAllowed.value || !entryVisible('plugins')) return []
  const available = new Map(plugins.value.filter(plugin =>
    plugin.enabled && plugin.execution_allowed !== false &&
    ['verified', 'session_exposed', 'runtime_active'].includes(plugin.availability?.status || '') &&
    hasStandalonePluginUi(plugin),
  ).map(plugin => [plugin.id, plugin]))
  return selectedIds.value.map(id => available.get(id)).filter((plugin): plugin is DshPlugin => Boolean(plugin))
})

async function refresh() {
  selectedIds.value = readPluginShortcuts(props.mainId, props.userId)
  const current = ++requestId
  if (!props.loggedIn || !selectedIds.value.length) { plugins.value = []; executionAllowed.value = false; return }
  try {
    const [result, allowed] = await Promise.all([listDshPlugins(), getPluginExecutionAccess()])
    if (current === requestId) { plugins.value = result; executionAllowed.value = allowed }
  } catch {
    if (current === requestId) { plugins.value = []; executionAllowed.value = false }
  }
}

async function open(plugin: DshPlugin) {
  if (openingId.value) return
  openingId.value = plugin.id
  try {
    const { url } = await launchDshPluginUi(plugin.id)
    if (new URL(url).origin === window.location.origin) throw new Error(t('plugins.uiOriginRequired'))
    uiName.value = plugin.name
    uiUrl.value = url
    uiOpen.value = true
  } catch (error) {
    const detail = (error as { response?: { data?: { detail?: string } } })?.response?.data?.detail
    const key = detail === 'plugin_ui_access_denied' ? 'plugins.uiAccessDenied' : 'plugins.uiRuntimeUnavailable'
    message.error(detail ? t(key) : (error as Error).message || t(key))
    void refresh()
  } finally {
    openingId.value = ''
  }
}

onMounted(() => { window.addEventListener(pluginShortcutsChanged, refresh); window.addEventListener('storage', refresh); void refresh() })
onUnmounted(() => { window.removeEventListener(pluginShortcutsChanged, refresh); window.removeEventListener('storage', refresh) })
watch(() => [props.mainId, props.userId, props.loggedIn, props.currentView], refresh)
</script>

<style scoped>
.plugin-shortcuts{padding:0 12px 8px}.shortcut-heading{display:flex;width:100%;align-items:center;gap:4px;padding:12px 8px 4px;text-align:left;color:#9ca3af;font-size:10px;font-weight:700;letter-spacing:.1em;text-transform:uppercase}.heading-arrow{width:14px;height:14px;transition:transform .15s}.heading-arrow.expanded{transform:rotate(90deg)}.shortcut-items{display:grid;gap:2px}.shortcut-item{display:flex;min-height:34px;align-items:center;gap:10px;width:100%;padding:5px 10px;border-radius:9px;text-align:left;color:#4b5563;font-size:13px}.shortcut-item:hover,.overflow-items button:hover{background:#e9edf4}.shortcut-item:disabled{opacity:.5}.shortcut-item span{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.shortcut-item .n-icon{flex:none;font-size:17px}.shortcut-more{justify-content:space-between}.overflow-items{display:grid;min-width:200px;max-width:300px;max-height:240px;overflow:auto;padding:4px}.overflow-items button{padding:7px 10px;border-radius:7px;text-align:left;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
</style>
