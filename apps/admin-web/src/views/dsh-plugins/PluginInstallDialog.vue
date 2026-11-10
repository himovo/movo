<template>
  <n-modal :show="show" preset="card" :title="t('dshPlugins.add')" style="width:min(560px,92vw)" @update:show="emit('update:show', $event)">
    <div class="source-tabs">
      <n-button :type="mode === 'remote' ? 'primary' : 'default'" @click="mode = 'remote'">{{ t('dshPlugins.remote') }}</n-button>
      <n-button :type="mode === 'local' ? 'primary' : 'default'" @click="mode = 'local'">{{ t('dshPlugins.local') }}</n-button>
    </div>
    <template v-if="mode === 'remote'">
      <n-form-item :label="t('dshPlugins.spec')"><n-input v-model:value="spec" placeholder="@scope/plugin@1.2.3" @keyup.enter="submit" /></n-form-item>
      <div class="install-guide">
        <strong>{{ t('dshPlugins.sourceTypes') }}</strong>
        <div><n-icon :component="CubeOutline" /><span>npm</span><code>@scope/plugin@1.2.3</code></div>
        <div><n-icon :component="CloudDownloadOutline" /><span>HTTPS .tgz</span><code>https://example.com/plugin-1.2.3.tgz</code></div>
        <p>{{ t('dshPlugins.sourceLimits') }}</p>
        <strong>{{ t('dshPlugins.installChecksTitle') }}</strong>
        <p>{{ t('dshPlugins.installChecks') }}</p>
        <p>{{ t('dshPlugins.capabilityLimits') }}</p>
        <strong>{{ t('dshPlugins.capabilitiesTitle') }}</strong>
        <p>{{ t('dshPlugins.capabilitiesSupported') }}</p>
        <p>{{ t('dshPlugins.capabilitiesConditional') }}</p>
        <p>{{ t('dshPlugins.capabilitiesUnsupported') }}</p>
      </div>
      <div v-if="preflight" class="preflight" role="status">
        <strong>{{ t(preflight.status === 'pending_runtime_validation' ? 'dshPlugins.preflightPending' : preflight.status === 'unverified' ? 'dshPlugins.preflightUnknown' : 'dshPlugins.preflightRefused') }}</strong>
        <span>{{ preflight.name || preflight.spec }}{{ preflight.version ? `@${preflight.version}` : '' }} · DSH {{ preflight.dshVersion }}</span>
        <span v-if="preflight.registry">{{ t('dshPlugins.preflightSource', { source: preflight.registry }) }}</span>
        <span v-if="preflight.offlineSourceDshVersion && preflight.offlineSourceDshVersion !== preflight.dshVersion">{{ t('dshPlugins.offlineSourceVersionMismatch', { source: preflight.offlineSourceDshVersion, current: preflight.dshVersion }) }}</span>
        <span v-if="preflight.description">{{ preflight.description }}</span>
        <span v-if="preflight.diagnostic">{{ preflight.problem === 'fixed_plugin_version_required' ? t('dshPlugins.installError.fixedVersion') : preflight.diagnostic }}</span>
      </div>
      <p v-if="preflightError" class="help" role="alert">{{ preflightError }}</p>
    </template>
    <template v-else>
      <n-form-item :label="t('dshPlugins.archive')"><input class="file-input" type="file" accept=".tgz,.gz,application/gzip" @change="selectFile" /></n-form-item>
      <p class="help">{{ t('dshPlugins.archiveHelp') }}</p>
    </template>
    <p v-if="installing" class="help" role="status">{{ t('dshPlugins.environmentPreparing') }}</p>
    <template #footer><n-space justify="end"><n-button @click="emit('update:show', false)">{{ t('dshPlugins.cancel') }}</n-button><n-button type="primary" :loading="installing || checking" :disabled="mode === 'remote' ? !spec.trim() || preflight?.status === 'refused' : !file" @click="submit">{{ t(mode === 'remote' && !preflight ? 'dshPlugins.preflightCheck' : 'dshPlugins.install') }}</n-button></n-space></template>
  </n-modal>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import { NButton, NFormItem, NIcon, NInput, NModal, NSpace } from 'naive-ui'
import { CloudDownloadOutline, CubeOutline } from '@vicons/ionicons5'
import { t } from '@/composables/i18n'
import { preflightDshPlugin, type PluginPreflight } from '@/api/dsh-plugins'

const props = defineProps<{ show: boolean; installing: boolean }>()
const emit = defineEmits<{ 'update:show': [value: boolean]; install: [source: string | File] }>()
const mode = ref<'remote' | 'local'>('remote')
const spec = ref('')
const file = ref<File | null>(null)
const checking = ref(false)
const preflight = ref<PluginPreflight | null>(null)
const preflightError = ref('')
watch(spec, () => { preflight.value = null; preflightError.value = '' })
watch(() => props.show, visible => { if (!visible) { spec.value = ''; file.value = null; mode.value = 'remote' } })
function selectFile(event: Event) { file.value = (event.target as HTMLInputElement).files?.[0] || null }
async function submit() {
  if (props.installing || checking.value) return
  if (mode.value === 'local' && file.value) emit('install', file.value)
  if (mode.value !== 'remote' || !spec.value.trim()) return
  const requested = spec.value.trim()
  if (preflight.value?.spec === requested && preflight.value.status !== 'refused') {
    emit('install', requested)
    return
  }
  checking.value = true
  preflightError.value = ''
  try {
    const result = await preflightDshPlugin(requested)
    if (!props.show || mode.value !== 'remote' || spec.value.trim() !== requested) return
    preflight.value = result
  } catch (error) {
    const detail = (error as any)?.response?.data?.detail
    preflightError.value = detail === 'plugin_source_must_be_prebuilt'
      ? t('dshPlugins.installError.prebuiltOnly')
      : String(detail || (error as Error)?.message || t('dshPlugins.error'))
  } finally { checking.value = false }
}
</script>

<style scoped>.source-tabs{display:flex;gap:8px;margin-bottom:18px}.file-input{width:100%;padding:8px;border:1px solid #d9e0ec;border-radius:8px}.help{margin:0;color:#8490a2;font-size:13px;line-height:1.6}.install-guide{display:grid;gap:7px;font-size:13px;color:#52627b}.install-guide>div{display:flex;gap:9px;align-items:center;min-width:0}.install-guide>div .n-icon{color:#5277cb;font-size:17px;flex:none}.install-guide>div span{width:82px;flex:none}.install-guide code{overflow:auto;white-space:nowrap;color:#2858bc}.install-guide strong{color:#25324b}.install-guide p{margin:0 0 6px;line-height:1.5}.preflight{display:grid;gap:4px;margin:12px 0;padding:10px;border:1px solid #dce5f3;border-radius:8px;color:#43536e;font-size:12px;overflow-wrap:anywhere}</style>
