<template>
  <div class="availability">
    <n-tag size="small" :type="tagType" :bordered="false">{{ t(`plugins.cardStatus.${cardStatus}`) }}</n-tag>
    <span v-if="issue && cardStatus === 'unavailable'" class="issue-label">{{ t(`plugins.issue.${issue}`) }}</span>
    <span v-if="conversationAvailable" class="conversation-capability"><n-icon :component="ChatbubbleOutline" />{{ t('plugins.conversationAvailable') }}</span>
    <n-popover trigger="click" placement="bottom-start" style="max-width: 360px">
      <template #trigger><n-button size="small" text type="primary" :title="t('plugins.diagnosis')" :aria-label="t('plugins.diagnosis')"><template #icon><n-icon :component="InformationCircleOutline" /></template></n-button></template>
      <div class="diagnosis">
        <strong>{{ t('plugins.diagnosis') }}</strong>
        <p v-if="issue" class="diagnosis-cause">{{ t(`plugins.issue.${issue}`) }}</p>
        <p v-if="issue === 'version' && requiredVersion">{{ t('plugins.issue.versionDetails', { required: requiredVersion, current: availability?.dsh_version || '—' }) }}</p>
        <p v-else-if="issue === 'version'">{{ t('plugins.versionPair', { dsh: availability?.dsh_version || '—', plugin: availability?.plugin_version || '—' }) }}</p>
        <p v-else-if="!issue || issue === 'unknown'">{{ reason }}</p>
        <p v-if="issue" class="next-step">{{ t(`plugins.issueAction.${issue}${canVerify && issue !== 'version' ? 'Personal' : ''}`) }}</p>
        <p v-if="availability?.offline_source_dsh_mismatch" class="next-step">{{ t('plugins.offlineSourceVersionMismatch', { source: availability.offline_source_dsh_version || '', current: availability.dsh_version || '' }) }}</p>
        <p v-if="hasClientUi && !hasUiSurface" class="next-step">{{ t('plugins.uiNeedsCheck') }}</p>
        <div v-if="completedChecks.length" class="checks">
          <div v-for="check in completedChecks" :key="check" class="check"><span>✓</span>{{ t(`plugins.check.${check}`) }}</div>
        </div>
        <div v-if="hasCapabilities" class="capabilities">
          <p v-if="availability?.discovered_tools?.length">{{ t('plugins.detectedToolsList', { names: availability.discovered_tools.join(', ') }) }}</p>
          <p v-if="availability?.capabilities?.skills?.length">{{ t('plugins.detectedSkillsList', { names: availability.capabilities.skills.map(item => item.name).join(', ') }) }}</p>
          <p v-if="availability?.capabilities?.commands?.length">{{ t('plugins.detectedCommandsList', { names: availability.capabilities.commands.map(item => `/${item.name}`).join(', ') }) }}</p>
          <p v-if="availability?.capabilities?.mcpServers?.length">{{ t('plugins.detectedMcpServersList', { names: availability.capabilities.mcpServers.map(item => `${item.name} (${item.tools.length})`).join(', ') }) }}</p>
          <p v-if="availability?.capabilities?.rows?.length">{{ t('plugins.detectedModulesList', { names: availability.capabilities.rows.map(item => item.moduleName).join(', ') }) }}</p>
          <p v-if="hasClientUi">{{ t('plugins.detectedClientModulesList', { names: availability?.capabilities?.clientModules?.map(item => item.id).join(', ') || '' }) }}</p>
        </div>
        <div v-if="showRawReason" class="raw-diagnostic">
          <n-button size="tiny" text :title="t('plugins.rawDiagnostic')" :aria-label="t('plugins.rawDiagnostic')" :aria-expanded="rawExpanded" @click="rawExpanded = !rawExpanded"><template #icon><n-icon :component="rawExpanded ? ChevronUpOutline : ChevronDownOutline" /></template></n-button>
          <pre v-if="rawExpanded">{{ availability?.reason }}</pre>
        </div>
        <n-button v-if="canVerify && status !== 'unverified'" size="small" :loading="busy" @click="emit('verify')">{{ t(status === 'failed' ? 'plugins.retryPreparation' : 'plugins.verify') }}</n-button>
      </div>
    </n-popover>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { NButton, NIcon, NPopover, NTag } from 'naive-ui'
import { ChatbubbleOutline, ChevronDownOutline, ChevronUpOutline, InformationCircleOutline } from '@vicons/ionicons5'
import type { PluginAvailability as Assessment } from '../../api/dshPlugins'
import { t } from '../../composables/i18n'
import { pluginIssue, requiredDshVersion } from './pluginDiagnosis'
import { hasStandaloneUiSurface } from './pluginUiSurface'

const props = defineProps<{ availability?: Assessment; busy?: boolean; canVerify?: boolean; cardStatus: 'ready' | 'loaded' | 'checking' | 'unavailable' | 'off'; conversationAvailable: boolean; executionAllowed: boolean }>()
const emit = defineEmits<{ verify: [] }>()
const rawExpanded = ref(false)
const status = computed(() => props.availability?.status || 'unverified')
const issue = computed(() => pluginIssue(props.availability, props.executionAllowed))
const requiredVersion = computed(() => requiredDshVersion(props.availability))
const hasClientUi = computed(() => ['verified', 'session_exposed', 'runtime_active'].includes(status.value) && Boolean(props.availability?.capabilities?.clientModules?.length))
const hasUiSurface = computed(() => hasStandaloneUiSurface(props.availability))
const tagType = computed(() => props.cardStatus === 'ready' ? 'success' : props.cardStatus === 'checking' ? 'warning' : 'default')
const completedChecks = computed(() => ['package', 'runtime', 'session', 'invocation'].filter(check => props.availability?.checks?.[check]))
const hasCapabilities = computed(() => Boolean(props.availability?.discovered_tools?.length || props.availability?.capabilities && Object.values(props.availability.capabilities).some(value => Array.isArray(value) && value.length)))
const knownReasons = new Set(['invocation_verified', 'invocation_not_verified', 'tools_missing_from_session', 'no_conversation_tools', 'other_capabilities_available', 'no_global_tool_detected', 'legacy_not_assessed', 'not_assessed', 'dsh_version_changed', 'revalidation_in_progress', 'plugin_revalidation_interrupted'])
const reason = computed(() => {
  const value = props.availability?.reason || 'legacy_not_assessed'
  return knownReasons.has(value) ? t(`plugins.reason.${value}`) : value
})
const showRawReason = computed(() => Boolean(props.availability?.reason && !knownReasons.has(props.availability.reason)))
</script>

<style scoped>
.availability{display:flex;align-items:center;gap:8px;min-width:0}.availability :deep(.n-button){margin-left:auto}.issue-label{color:#66758e;font-size:12px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.conversation-capability{display:inline-flex;align-items:center;gap:4px;font-size:12px;color:#45648c}.conversation-capability .n-icon{font-size:15px}.diagnosis{font-size:12px;line-height:1.6;color:#4b5972;max-height:min(70vh,520px);overflow-y:auto;min-width:280px}.diagnosis p{margin:6px 0;overflow-wrap:anywhere}.diagnosis strong{font-size:13px;color:#17233d}.diagnosis-cause{font-weight:600;color:#17233d}.check{display:flex;gap:5px}.checks,.capabilities{margin:10px 0;border-top:1px solid #e9edf3;padding-top:8px}.next-step{color:#596b86}.raw-diagnostic{margin:8px 0}.raw-diagnostic :deep(.n-button){margin-left:0}.raw-diagnostic pre{max-height:160px;overflow:auto;white-space:pre-wrap;overflow-wrap:anywhere;background:#f4f6fa;border-radius:6px;padding:8px;font-size:11px}
</style>
