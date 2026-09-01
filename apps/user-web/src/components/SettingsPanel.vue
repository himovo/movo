<script setup lang="ts">
// Shell-aware settings panel.
// - On Web: lets the user persist a custom backend URL locally.
// - On Desktop: same + agent lifecycle controls (start/stop/restart).

import { onMounted, ref } from 'vue'
import {
  NAlert,
  NBadge,
  NButton,
  NCard,
  NFormItem,
  NInput,
  NSelect,
  NSpace,
  NSwitch,
  NTag,
} from 'naive-ui'
import {
  capabilities,
  connectEnterpriseServer, getSettings, updateSettings,
  getAgentStatus, startAgent, stopAgent, restartAgent,
  type Settings, type AgentStatus,
} from '../platform'
import { setLocale, t } from '../composables/i18n'

const settings = ref<Settings | null>(null)
const status = ref<AgentStatus>({
  running: false,
  ws_url: '',
  user_id: '',
  local_control_url: '',
  local_control_token: '',
})
const saving = ref(false)
const error = ref('')
const serviceAddress = ref('')

const languageOptions = [
  { label: () => t('settings.language.zh'), value: 'zh' },
  { label: () => t('settings.language.en'), value: 'en' },
]

async function refresh() {
  try {
    settings.value = await getSettings()
    serviceAddress.value = settings.value.service_url
    status.value = await getAgentStatus()
  } catch (e: any) {
    error.value = String(e?.message || e)
  }
}

onMounted(refresh)

async function save() {
  if (!settings.value) return
  saving.value = true
  error.value = ''
  try {
    if (capabilities.isDesktop && serviceAddress.value.trim() !== settings.value.service_url) {
      if (!window.confirm(t('settings.server_change_confirm'))) return
      const result = await connectEnterpriseServer(serviceAddress.value)
      await updateSettings({
        ...result.settings,
        language: settings.value.language,
        timezone: settings.value.timezone,
        auto_start_agent: settings.value.auto_start_agent,
      })
      for (const key of ['auth_token', 'auth_account', 'auth_users', 'auth_user_profile']) localStorage.removeItem(key)
      window.location.reload()
      return
    }
    settings.value = await updateSettings(settings.value)
    setLocale(settings.value.language)
  } catch (e: any) {
    error.value = String(e?.message || e)
  } finally {
    saving.value = false
  }
}

async function onAgentAction(action: 'start' | 'stop' | 'restart') {
  error.value = ''
  try {
    const fn = action === 'start' ? startAgent : action === 'stop' ? stopAgent : restartAgent
    status.value = await fn()
  } catch (e: any) {
    error.value = String(e?.message || e)
  }
}
</script>

<template>
  <div class="settings-panel max-w-xl mx-auto p-6 space-y-6 text-sm">
    <div class="flex items-center gap-2">
      <h2 class="text-lg font-semibold text-slate-800">{{ t('ui.settings') }}</h2>
      <n-tag size="small" :bordered="false" type="default">
        {{ capabilities.isDesktop ? t('settings.platform.desktop') : t('settings.platform.web') }}
      </n-tag>
    </div>

    <n-alert v-if="error" type="error" :show-icon="true">{{ error }}</n-alert>

    <n-card
      v-if="settings"
      :title="t('settings.enterprise_service')"
      :bordered="false"
      size="small"
      class="!rounded-xl"
    >
      <n-space vertical :size="14">
        <n-form-item :label="t('settings.language')" :show-feedback="false">
          <n-select v-model:value="settings.language" :options="languageOptions" />
        </n-form-item>
        <n-form-item v-if="capabilities.isDesktop" :label="t('settings.service_url')" :show-feedback="false">
          <n-input
            v-model:value="serviceAddress"
            placeholder="https://movo.company.com"
            :input-props="{ spellcheck: false, autocomplete: 'off' }"
            style="font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 12px"
          />
        </n-form-item>
        <n-alert v-if="capabilities.isDesktop" type="info" :show-icon="true">
          {{ t('settings.service_url_help') }}
        </n-alert>
        <div v-if="capabilities.isDesktop" class="flex items-center gap-2">
          <n-switch v-model:value="settings.auto_start_agent" size="small" />
          <span class="text-slate-600">{{ t('settings.auto_start_agent') }}</span>
        </div>
        <div>
          <n-button type="primary" :loading="saving" :disabled="saving" @click="save">
            {{ t('ui.save') }}
          </n-button>
        </div>
      </n-space>
    </n-card>

    <n-card
      v-if="capabilities.isDesktop"
      :title="t('settings.local_agent')"
      :bordered="false"
      size="small"
      class="!rounded-xl"
    >
      <n-space vertical :size="14">
        <div class="flex items-center gap-3">
          <n-badge
            :color="status.running ? '#10b981' : '#94a3b8'"
            dot
            :processing="status.running"
          >
            <n-tag size="small" :bordered="false" :type="status.running ? 'success' : 'default'">
              {{ status.running ? t('settings.agent_running') : t('settings.agent_stopped') }}
            </n-tag>
          </n-badge>
          <span v-if="status.ws_url" class="text-[11px] text-slate-400 font-mono truncate">
            {{ status.ws_url }}
          </span>
        </div>
        <n-space :size="8">
          <n-button size="small" :disabled="status.running" @click="onAgentAction('start')">
            {{ t('settings.agent_start') }}
          </n-button>
          <n-button size="small" :disabled="!status.running" @click="onAgentAction('stop')">
            {{ t('settings.agent_stop') }}
          </n-button>
          <n-button size="small" @click="onAgentAction('restart')">
            {{ t('settings.agent_restart') }}
          </n-button>
        </n-space>
      </n-space>
    </n-card>
  </div>
</template>
