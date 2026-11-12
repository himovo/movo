<template>
  <div class="page-stack plugin-workspace">
    <PluginOverview :plugins="rows" />
    <PluginCatalog
      :plugins="rows"
      :loading="loading"
      :verify-busy-id="verifyBusyId"
      :toggle-busy-id="toggleBusyId"
      :ui-opening-id="uiOpeningId"
      :execution-allowed="executionAllowed"
      :shortcut-ids="shortcutIds"
      @reload="reload"
      @add="installOpen = true"
      @toggle="toggle"
      @remove="remove"
      @verify="verify"
      @open-ui="openUi"
      @toggle-shortcut="toggleShortcut"
    />
    <PluginInstallDialog v-model:show="installOpen" :installing="installing" @install="install" />
    <PluginUiDrawer v-model:show="uiOpen" :name="uiName" :url="uiUrl" @open-session="openPluginSession" />
  </div>
</template>

<script setup lang="ts">
import { onMounted, onUnmounted, ref, watch } from 'vue'
import { useMessage } from 'naive-ui'
import { t } from '../composables/i18n'
import { localizePluginUiUrl } from '../platform'
import { getPluginExecutionAccess, installDshPlugin, launchDshPluginUi, listDshPlugins, removeDshPlugin, resolveDshPluginUiSession, setDshPluginEnabled, uploadDshPlugin, verifyDshPlugin, type DshPlugin } from '../api/dshPlugins'
import PluginOverview from './plugins/PluginOverview.vue'
import PluginCatalog from './plugins/PluginCatalog.vue'
import PluginInstallDialog from './plugins/PluginInstallDialog.vue'
import PluginUiDrawer from './plugins/PluginUiDrawer.vue'
import { pluginShortcutsChanged, readPluginShortcuts, setPluginShortcut } from './plugins/pluginShortcuts'

const props = defineProps<{ mainId: string; userId: string | null }>()
const emit = defineEmits<{ openSession: [sessionId: string] }>()

const message = useMessage()
const rows = ref<DshPlugin[]>([])
const executionAllowed = ref(false)
const loading = ref(false)
const installing = ref(false)
const verifyBusyId = ref('')
const toggleBusyId = ref('')
const uiOpeningId = ref('')
const installOpen = ref(false)
const uiOpen = ref(false)
const uiName = ref('')
const uiUrl = ref('')
const shortcutIds = ref<string[]>([])

function syncShortcuts() {
  shortcutIds.value = readPluginShortcuts(props.mainId, props.userId || '')
}

function toggleShortcut(plugin: DshPlugin) {
  shortcutIds.value = setPluginShortcut(props.mainId, props.userId || '', plugin.id, !shortcutIds.value.includes(plugin.id))
}

async function openUi(plugin: DshPlugin) {
  if (uiOpeningId.value) return
  uiOpeningId.value = plugin.id
  try {
    const { url } = await launchDshPluginUi(plugin.id)
    if (new URL(url).origin === window.location.origin) throw new Error(t('plugins.uiOriginRequired'))
    uiName.value = plugin.name
    uiUrl.value = await localizePluginUiUrl(url)
    uiOpen.value = true
  } catch (error) { message.error(String(errorText(error))) }
  finally { uiOpeningId.value = '' }
}

async function openPluginSession(kernelSessionId: string) {
  try {
    const conversationId = await resolveDshPluginUiSession(kernelSessionId)
    uiOpen.value = false
    emit('openSession', conversationId)
  } catch {
    message.error(t('plugins.uiSessionUnavailable'))
  }
}
function errorText(error: unknown): string {
  const detail = (error as any)?.response?.data?.detail
  if (typeof detail === 'string' && detail.startsWith('incompatible-version')) {
    return `${t('plugins.installError.incompatibleVersion')} ${detail}`
  }
  if (typeof detail === 'string' && detail.startsWith('dsh_runtime_version_mismatch')) {
    return `${t('plugins.installError.runtimeMismatch')} ${detail}`
  }
  const messages: Record<string, string> = {
    plugin_package_not_found: 'plugins.installError.notFound',
    plugin_registry_unavailable: 'plugins.installError.registryUnavailable',
    fixed_plugin_version_required: 'plugins.installError.fixedVersion',
    plugin_source_must_be_prebuilt: 'plugins.installError.prebuiltOnly',
    personal_plugin_source_must_be_public: 'plugins.installError.publicSource',
    personal_plugin_conflicts_with_restricted_enterprise_plugin: 'plugins.installError.restrictedEnterprise',
    plugin_runtime_access_denied: 'plugins.executionAccessDenied',
    plugin_ui_access_denied: 'plugins.uiAccessDenied',
    plugin_ui_unavailable: 'plugins.uiUnavailable',
    plugin_ui_runtime_unavailable: 'plugins.uiRuntimeUnavailable',
    plugin_ui_runtime_not_active: 'plugins.uiRuntimeNotActive',
    plugin_ui_public_origin_required: 'plugins.uiOriginRequired',
    plugin_ui_origin_invalid: 'plugins.uiOriginRequired',
    plugin_ui_origin_must_be_separate: 'plugins.uiOriginRequired',
    'not-a-bundle': 'plugins.installError.notBundle',
  }
  const key = messages[String(detail)]
  return key ? t(key) : typeof detail === 'string' ? detail : (error as Error)?.message || t('plugins.error')
}

async function reload() {
  loading.value = true
  executionAllowed.value = false
  try {
    const [plugins, allowed] = await Promise.all([listDshPlugins(), getPluginExecutionAccess()])
    rows.value = plugins
    executionAllowed.value = allowed
  }
  catch (error) { message.error(String(errorText(error))) }
  finally { loading.value = false }
}

async function install(source: string | File) {
  if (installing.value) return
  installing.value = true
  try {
    const plugin = typeof source === 'string' ? await installDshPlugin(source) : await uploadDshPlugin(source)
    installOpen.value = false
    const status = plugin.availability?.reason === 'no_global_tool_detected' ? 'unsupported' : plugin.availability?.status
    if (status === 'unsupported') message.warning(t('plugins.installedUnsupported'))
    else if (status === 'session_exposed' || status === 'runtime_active' || status === 'verified') message.success(t('plugins.installed'))
    else message.warning(t('plugins.installedNeedsCheck'))
    await reload()
  } catch (error) { message.error(String(errorText(error))) }
  finally { installing.value = false }
}

async function verify(plugin: DshPlugin) {
  if (verifyBusyId.value || toggleBusyId.value) return
  verifyBusyId.value = plugin.id
  try { await verifyDshPlugin(plugin.id); await reload() }
  catch (error) { message.error(String(errorText(error))) }
  finally { verifyBusyId.value = '' }
}

async function toggle(plugin: DshPlugin, enabled: boolean) {
  if (verifyBusyId.value || toggleBusyId.value) return
  toggleBusyId.value = plugin.id
  try { await setDshPluginEnabled(plugin.id, enabled); await reload() }
  catch (error) { message.error(String(errorText(error))) }
  finally { toggleBusyId.value = '' }
}

async function remove(plugin: DshPlugin) {
  try { await removeDshPlugin(plugin.id); await reload() }
  catch (error) { message.error(String(errorText(error))) }
}

onMounted(() => { syncShortcuts(); window.addEventListener(pluginShortcutsChanged, syncShortcuts); void reload() })
onUnmounted(() => window.removeEventListener(pluginShortcutsChanged, syncShortcuts))
watch(() => [props.mainId, props.userId], syncShortcuts)
</script>

<style scoped>
.plugin-workspace {
  height: 100%;
  min-height: 0;
  display: flex;
  flex-direction: column;
  gap: 16px;
  padding: 12px;
  background: #f6f8fc;
}
</style>
