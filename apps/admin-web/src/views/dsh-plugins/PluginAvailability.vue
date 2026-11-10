<template>
  <div class="availability">
    <n-tag size="small" :type="tagType" :bordered="false">{{ t(`dshPlugins.cardStatus.${cardStatus}`) }}</n-tag>
    <span v-if="conversationAvailable" class="conversation-capability"><n-icon :component="ChatbubbleOutline" />{{ t('dshPlugins.conversationAvailable') }}</span>
    <n-popover trigger="click" placement="bottom-start" style="max-width:340px">
      <template #trigger><n-button size="small" text type="primary" :title="t('dshPlugins.diagnosis')" :aria-label="t('dshPlugins.diagnosis')"><template #icon><n-icon :component="InformationCircleOutline" /></template></n-button></template>
      <div class="diagnosis">
        <strong>{{ t('dshPlugins.diagnosis') }}</strong>
        <p>{{ reason }}</p>
        <p v-if="status === 'failed'" class="next-step">{{ t('dshPlugins.failureNextStep') }}</p>
        <p v-if="['session_exposed', 'verified'].includes(status)" class="next-step">{{ t('dshPlugins.uiLimit') }}</p>
        <p v-if="availability?.workspace_required_tools?.length" class="next-step">{{ t('dshPlugins.workspaceRequiredTools', { names: availability.workspace_required_tools.join(', ') }) }}</p>
        <div v-for="check in checks" :key="check" class="check">
          <span>{{ availability?.checks?.[check] ? '✓' : '○' }}</span> {{ t(`dshPlugins.check.${check}`) }}
        </div>
        <p v-if="availability?.discovered_tools?.length">{{ t('dshPlugins.detectedToolsList', { names: availability.discovered_tools.join(', ') }) }}</p>
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
const ready = computed(() => ['verified', 'session_exposed'].includes(status.value))
const conversationAvailable = computed(() => ready.value && props.enabled && Boolean(props.availability?.session_tools?.length))
const cardStatus = computed(() => status.value === 'unverified' ? 'checking' : !ready.value ? 'unavailable' : !props.enabled ? 'off' : conversationAvailable.value ? 'ready' : 'loaded')
const tagType = computed(() => cardStatus.value === 'ready' ? 'success' : cardStatus.value === 'checking' ? 'warning' : 'default')
const reason = computed(() => {
  const value = props.availability?.reason || 'legacy_not_assessed'
  const known = ['invocation_verified', 'invocation_not_verified', 'tools_missing_from_session', 'no_global_tool_detected', 'legacy_not_assessed', 'not_assessed']
  return known.includes(value) ? t(`dshPlugins.reason.${value}`) : value
})
</script>

<style scoped>.availability{display:flex;align-items:center;gap:8px;min-width:0}.availability :deep(.n-button){margin-left:auto}.conversation-capability{display:inline-flex;align-items:center;gap:4px;color:#45648c;font-size:12px}.conversation-capability .n-icon{font-size:15px}.diagnosis{font-size:12px;line-height:1.6;color:#4b5972}.diagnosis p{margin:6px 0;overflow-wrap:anywhere;white-space:pre-line}.diagnosis strong{font-size:13px;color:#17233d}.check{display:flex;gap:5px}.next-step{color:#855c15}</style>
