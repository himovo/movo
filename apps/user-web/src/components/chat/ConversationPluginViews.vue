<template>
  <n-popover v-if="plugins.length || legacy.length" trigger="click" placement="bottom-end" @update:show="onPopover">
    <template #trigger>
      <button type="button" class="grid h-9 w-9 place-items-center rounded-lg text-slate-600 hover:bg-gray-100 hover:text-blue-600"
        :title="t('plugins.conversationViews')" :aria-label="t('plugins.conversationViews')">
        <n-icon :component="AppsOutline" :size="19" />
      </button>
    </template>
    <div class="min-w-44 max-w-64 space-y-1">
      <div class="px-2 py-1 text-xs font-semibold text-slate-500">{{ t('plugins.conversationViews') }}</div>
      <button v-for="plugin in plugins" :key="plugin.id" type="button" :disabled="openingId !== ''"
        :aria-busy="openingId === plugin.id"
        class="flex w-full items-center gap-2 rounded-lg px-2 py-2 text-left text-sm hover:bg-gray-100 disabled:opacity-50"
        @click="open(plugin)">
        <svg v-if="openingId === plugin.id" class="h-4 w-4 shrink-0 animate-spin text-blue-600" viewBox="0 0 24 24" fill="none" aria-hidden="true">
          <circle cx="12" cy="12" r="9" stroke="currentColor" stroke-opacity=".25" stroke-width="3" />
          <path d="M12 3a9 9 0 0 1 9 9" stroke="currentColor" stroke-linecap="round" stroke-width="3" />
        </svg>
        <span class="min-w-0 truncate">{{ plugin.name }}</span>
      </button>
      <div v-if="checking" class="px-2 py-2 text-sm text-slate-500">{{ t('plugins.checkingConversationViews') }}</div>
      <div v-else-if="!plugins.length" class="px-2 py-2 text-sm text-slate-500">{{ t('plugins.noConversationViews') }}</div>
    </div>
  </n-popover>
  <PluginUiDrawer v-model:show="drawerOpen" :name="drawerName" :url="drawerUrl" />
</template>

<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'
import { NIcon, NPopover, useMessage } from 'naive-ui'
import { AppsOutline } from '@vicons/ionicons5'
import { getPluginExecutionAccess, launchDshPluginUi, listDshPlugins, type DshPlugin } from '../../api/dshPlugins'
import { getLocale, t } from '../../composables/i18n'
import PluginUiDrawer from '../plugins/PluginUiDrawer.vue'
import { cachedConversationView, probeLegacyConversationView, rememberConversationView } from './conversationViewLegacy'

const props = defineProps<{ sessionId: string; userId: string; mainId: string }>()
const message = useMessage()
const plugins = ref<DshPlugin[]>([])
const legacy = ref<DshPlugin[]>([])
const checking = ref(false)
const openingId = ref('')
const drawerOpen = ref(false)
const drawerName = ref('')
const drawerUrl = ref('')
let revision = 0

async function refresh() {
  const current = ++revision
  if (!props.sessionId || !props.userId || !props.mainId) { plugins.value = []; legacy.value = []; return }
  try {
    const [items, allowed] = await Promise.all([listDshPlugins(), getPluginExecutionAccess()])
    if (current !== revision) return
    const eligible = allowed ? items.filter(item => item.enabled && item.execution_allowed !== false &&
      item.availability?.capabilities?.clientModules?.length &&
      (['verified', 'session_exposed', 'runtime_active'].includes(item.availability.status) ||
        item.availability.status === 'unverified' && item.availability.reason === 'revalidation_in_progress')) : []
    plugins.value = eligible.filter(item => item.availability?.capabilities?.clientModules?.some(module => module.conversationView === true) ||
      item.availability?.capabilities?.clientModules?.some(module => module.conversationView === undefined) &&
      cachedConversationView(`${item.id}:${item.version}`) === true)
    legacy.value = eligible.filter(item => item.availability?.capabilities?.clientModules?.some(module => module.conversationView === undefined) &&
      cachedConversationView(`${item.id}:${item.version}`) === undefined)
  } catch {
    if (current === revision) { plugins.value = []; legacy.value = [] }
  }
}

async function onPopover(show: boolean) {
  if (!show || checking.value || !legacy.value.length) return
  const current = revision
  checking.value = true
  for (const item of legacy.value) {
    if (current !== revision) return
    try {
      const { url, kernelSessionId } = await launchDshPluginUi(item.id, props.sessionId)
      const result = kernelSessionId ? await probeLegacyConversationView(url) : undefined
      if (result !== undefined) rememberConversationView(`${item.id}:${item.version}`, result)
      if (current === revision && result === true) plugins.value.push(item)
    } catch { /* Legacy metadata remains pending until revalidation completes. */ }
  }
  if (current === revision) { legacy.value = []; checking.value = false }
}

async function open(plugin: DshPlugin) {
  if (openingId.value) return
  openingId.value = plugin.id
  try {
    const { url, kernelSessionId } = await launchDshPluginUi(plugin.id, props.sessionId)
    if (!kernelSessionId || new URL(url).origin === window.location.origin) throw new Error('plugin_ui_session_unavailable')
    const target = new URL(url)
    target.searchParams.set('locale', getLocale())
    drawerName.value = plugin.name
    drawerUrl.value = target.toString()
    drawerOpen.value = true
  } catch {
    message.error(t('plugins.conversationViewsUnavailable'))
  } finally {
    openingId.value = ''
  }
}

onMounted(refresh)
watch(() => [props.sessionId, props.userId, props.mainId], () => {
  drawerOpen.value = false
  checking.value = false
  void refresh()
})
</script>
