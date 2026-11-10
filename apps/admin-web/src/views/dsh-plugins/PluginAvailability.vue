<template>
  <div class="availability">
    <n-tag size="small" :type="tagType" :bordered="false">{{ t(`dshPlugins.cardStatus.${cardStatus}`) }}</n-tag>
    <span v-if="conversationAvailable" class="conversation-capability"><n-icon :component="ChatbubbleOutline" />{{ t('dshPlugins.conversationAvailable') }}</span>
    <n-popover trigger="click" placement="bottom-start" style="max-width:340px">
      <template #trigger><n-button size="small" text type="primary" :title="t('dshPlugins.diagnosis')" :aria-label="t('dshPlugins.diagnosis')"><template #icon><n-icon :component="InformationCircleOutline" /></template></n-button></template>
      <div class="diagnosis">
        <strong>{{ t('dshPlugins.diagnosis') }}</strong>
        <p v-if="availability?.dsh_version">{{ t('dshPlugins.versionPair', { dsh: availability.dsh_version, plugin: availability.plugin_version || '' }) }}</p>
        <p v-if="availability?.offline_source_dsh_mismatch" class="next-step">{{ t('dshPlugins.offlineSourceVersionMismatch', { source: availability.offline_source_dsh_version || '', current: availability.dsh_version || '' }) }}</p>
        <p>{{ reason }}</p>
        <p v-if="status === 'failed' || status === 'version_incompatible'" class="next-step">{{ t('dshPlugins.failureNextStep') }}</p>
        <p v-if="hasClientUi" class="next-step">{{ t('dshPlugins.uiPending') }}</p>
        <p v-if="availability?.workspace_required_tools?.length" class="next-step">{{ t('dshPlugins.workspaceRequiredTools', { names: availability.workspace_required_tools.join(', ') }) }}</p>
        <div v-for="check in checks" :key="check" class="check">
          <span>{{ availability?.checks?.[check] ? '✓' : '○' }}</span> {{ t(`dshPlugins.check.${check}`) }}
        </div>
        <p v-if="availability?.discovered_tools?.length">{{ t('dshPlugins.detectedToolsList', { names: availability.discovered_tools.join(', ') }) }}</p>
        <p v-if="availability?.capabilities?.skills?.length">{{ t('dshPlugins.detectedSkillsList', { names: availability.capabilities.skills.map(item => item.name).join(', ') }) }}</p>
        <p v-if="availability?.capabilities?.commands?.length">{{ t('dshPlugins.detectedCommandsList', { names: availability.capabilities.commands.map(item => `/${item.name}`).join(', ') }) }}</p>
        <p v-if="availability?.capabilities?.modelProviders?.length">{{ t('dshPlugins.detectedModelProvidersList', { names: availability.capabilities.modelProviders.map(item => item.name).join(', ') }) }}</p>
        <p v-if="availability?.capabilities?.mcpServers?.length">{{ t('dshPlugins.detectedMcpServersList', { names: availability.capabilities.mcpServers.map(item => `${item.name} (${item.tools.length})`).join(', ') }) }}</p>
        <p v-if="availability?.capabilities?.rows?.length">{{ t('dshPlugins.detectedModulesList', { names: availability.capabilities.rows.map(item => item.moduleName).join(', ') }) }}</p>
        <p v-if="hasClientUi">{{ t('dshPlugins.detectedClientModulesList', { names: availability?.capabilities?.clientModules?.map(item => item.id).join(', ') || '' }) }}</p>
        <n-button size="small" :loading="busy" @click="emit('verify')">{{ t(status === 'failed' ? 'dshPlugins.retryPreparation' : 'dshPlugins.verify') }}</n-button>
      </div>
    </n-popover>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { NButton, NIcon, NPopover, NTag } from 'naive-ui'
import { ChatbubbleOutline, InformationCircleOutline } from '@vicons/ionicons5'
import type { PluginAvailability as Assessment } from '@/api/dsh-plugins'
import { t } from '@/composables/i18n'

const props = defineProps<{ availability?: Assessment; enabled: boolean; busy?: boolean }>()
const emit = defineEmits<{ verify: [] }>()
const checks = ['package', 'runtime', 'session', 'invocation']
const status = computed(() => props.availability?.status || 'unverified')
const hasClientUi = computed(() => ['verified', 'session_exposed', 'runtime_active'].includes(status.value) && Boolean(props.availability?.capabilities?.clientModules?.length))
const ready = computed(() => ['verified', 'session_exposed', 'runtime_active'].includes(status.value))
const conversationAvailable = computed(() => ready.value && props.enabled && Boolean(props.availability?.session_tools?.length || props.availability?.capabilities?.skills?.some(skill => skill.userInvocable || skill.modelInvocable) || props.availability?.capabilities?.commands?.length || props.availability?.capabilities?.mcpServers?.some(server => server.tools.length)))
const cardStatus = computed(() => status.value === 'unverified' ? 'checking' : !ready.value ? 'unavailable' : !props.enabled ? 'off' : !conversationAvailable.value && !hasClientUi.value ? 'loaded' : 'ready')
const tagType = computed(() => cardStatus.value === 'ready' ? 'success' : cardStatus.value === 'checking' ? 'warning' : 'default')
const reason = computed(() => {
  const value = props.availability?.reason || 'legacy_not_assessed'
  const known = ['invocation_verified', 'invocation_not_verified', 'tools_missing_from_session', 'no_conversation_tools', 'other_capabilities_available', 'no_global_tool_detected', 'legacy_not_assessed', 'not_assessed', 'dsh_version_changed', 'revalidation_in_progress', 'plugin_revalidation_interrupted']
  return known.includes(value) ? t(`dshPlugins.reason.${value}`) : value
})
</script>

<style scoped>.availability{display:flex;align-items:center;gap:8px;min-width:0}.availability :deep(.n-button){margin-left:auto}.conversation-capability{display:inline-flex;align-items:center;gap:4px;color:#45648c;font-size:12px}.conversation-capability .n-icon{font-size:15px}.diagnosis{font-size:12px;line-height:1.6;color:#4b5972;max-height:min(70vh,520px);overflow-y:auto;min-width:280px}.diagnosis p{margin:6px 0;overflow-wrap:anywhere;white-space:pre-line}.diagnosis strong{font-size:13px;color:#17233d}.check{display:flex;gap:5px}.next-step{color:#855c15}</style>
