<template>
  <div class="plugins-page">
    <DshPluginOverview :plugins="plugins" />
    <DshPluginCatalog :plugins="plugins" :loading="loading" :busy-id="busyId" :can-manage-access="Boolean(pluginAccess)" @reload="reload" @add="showInstall = true" @toggle="toggle" @remove="remove" @verify="verify" @access="openAccess" />
    <PluginInstallDialog v-model:show="showInstall" :installing="installing" @install="install" />
    <n-modal v-if="pluginAccess" v-model:show="accessVisible" preset="card" :title="t('dshPlugins.accessTitle', { name: accessPlugin?.name || '' })" style="width:min(760px,calc(100vw - 32px))">
      <ResourceAccessExtensionPanel v-if="accessVisible && accessPlugin" :resource-id="accessPlugin.id" :extension="pluginAccess" />
    </n-modal>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useMessage } from 'naive-ui'
import { NModal } from 'naive-ui'
import { t } from '@/composables/i18n'
import { installDshPlugin, listDshPlugins, removeDshPlugin, setDshPluginEnabled, uploadDshPlugin, verifyDshPlugin, type DshPlugin } from '@/api/dsh-plugins'
import DshPluginOverview from './DshPluginOverview.vue'
import DshPluginCatalog from './DshPluginCatalog.vue'
import PluginInstallDialog from './PluginInstallDialog.vue'
import ResourceAccessExtensionPanel from '@/components/resources/ResourceAccessExtensionPanel.vue'
import adminProductUiExtension from '@movo-admin-product-extension'

const message = useMessage()
const plugins = ref<DshPlugin[]>([])
const loading = ref(false)
const installing = ref(false)
const busyId = ref('')
const showInstall = ref(false)
const pluginAccess = adminProductUiExtension.pluginAccess
const accessVisible = ref(false)
const accessPlugin = ref<DshPlugin | null>(null)
function openAccess(plugin: DshPlugin) { accessPlugin.value = plugin; accessVisible.value = true }
function errorText(error: unknown): string {
  const detail = (error as any)?.response?.data?.detail
  const messages: Record<string, string> = {
    plugin_package_not_found: 'dshPlugins.installError.notFound',
    plugin_offline_package_missing: 'dshPlugins.installError.offlineMissing',
    plugin_registry_unavailable: 'dshPlugins.installError.registryUnavailable',
    'not-a-bundle': 'dshPlugins.installError.notBundle',
  }
  const key = messages[String(detail)]
  return key ? t(key) : typeof detail === 'string' ? detail : (error as Error)?.message || t('dshPlugins.error')
}

async function reload() {
  loading.value = true
  try { plugins.value = await listDshPlugins() } catch (error) { message.error(String(errorText(error))) }
  finally { loading.value = false }
}
async function install(source: string | File) {
  if (installing.value) return
  installing.value = true
  try {
    const plugin = typeof source === 'string' ? await installDshPlugin(source) : await uploadDshPlugin(source)
    showInstall.value = false
    const status = plugin.availability?.reason === 'no_global_tool_detected' ? 'unsupported' : plugin.availability?.status
    if (status === 'unsupported') message.warning(t('dshPlugins.installedUnsupported'))
    else if (status === 'session_exposed' || status === 'verified') message.success(t('dshPlugins.installed'))
    else message.warning(t('dshPlugins.installedNeedsCheck'))
    await reload()
  } catch (error) { message.error(String(errorText(error))) }
  finally { installing.value = false }
}
async function verify(plugin: DshPlugin) {
  busyId.value = plugin.id
  try { await verifyDshPlugin(plugin.id); await reload() }
  catch (error) { message.error(String(errorText(error))) }
  finally { busyId.value = '' }
}
async function toggle(plugin: DshPlugin, enabled: boolean) {
  busyId.value = plugin.id
  try { await setDshPluginEnabled(plugin.id, enabled); await reload() }
  catch (error) { message.error(String(errorText(error))) }
  finally { busyId.value = '' }
}
async function remove(plugin: DshPlugin) {
  try { await removeDshPlugin(plugin.id); await reload() }
  catch (error) { message.error(String(errorText(error))) }
}
onMounted(reload)
</script>

<style scoped>
.plugins-page{height:calc(100vh - 92px);min-height:0;display:flex;flex-direction:column;gap:16px}
</style>
