<template>
  <div class="complete-content">
    <n-alert type="success" :show-icon="true" :title="t('legacy.setup_complete')">
      {{ t('legacy.the_organization_initial_accounts_and_organization_models_are_configured') }}
    </n-alert>
    <div class="connection-list">
      <div v-for="item in items" :key="item.key" class="connection-item">
        <span class="connection-label">{{ item.label }}</span>
        <code>{{ item.value }}</code>
        <n-button size="small" secondary :disabled="!item.value" @click="$emit('copy', item.value)">{{ t('legacy.copy') }}</n-button>
      </div>
    </div>
    <p class="desktop-note">{{ t('legacy.enter_only_the_organization_service_url_in_the_desktop') }}</p>
    <div class="complete-actions">
      <n-button size="large" secondary @click="downloadConnectionFile">{{ t('legacy.download_connection_config') }}</n-button>
      <n-button type="primary" size="large" @click="$emit('login')">{{ t('legacy.sign_in_to_admin') }}</n-button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import { t } from '@/composables/i18n';
import type { SetupUrls } from '@/api/setup';

const props = defineProps<{
  urls: SetupUrls;
  orgName: string;
  mainId: string;
  orgTotalTokens: number;
  defaultUserTokens: number;
}>();
defineEmits<{ copy: [value: string]; login: [] }>();

const items = computed(() => [
  { key: 'user', label: t('legacy.employee_web'), value: props.urls.userWeb },
  { key: 'admin', label: t('legacy.admin_portal'), value: props.urls.adminWeb },
  { key: 'desktop', label: t('legacy.desktop_connection_url'), value: props.urls.desktopService },
]);

function downloadConnectionFile() {
  const lines = [
    'MOVO SELF-HOSTED CONNECTION',
    '===========================',
    `Organization: ${props.orgName}`,
    `Tenant ID: ${props.mainId}`,
    '',
    `Employee Web: ${props.urls.userWeb}`,
    `Admin Portal: ${props.urls.adminWeb}`,
    `Desktop Connection URL: ${props.urls.desktopService}`,
    '',
    `Organization Token Quota: ${props.orgTotalTokens}`,
    `Default Employee Token Quota: ${props.defaultUserTokens}`,
    '',
    'Security: passwords and API keys are intentionally excluded.',
  ];
  const blob = new Blob([`${lines.join('\n')}\n`], { type: 'text/plain;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = 'movo-connection.txt';
  link.click();
  URL.revokeObjectURL(url);
}
</script>

<style scoped>
.complete-content { display: grid; gap: 20px; }
.connection-list { display: grid; gap: 12px; }
.connection-item { display: grid; grid-template-columns: 132px minmax(0, 1fr) auto; align-items: center; gap: 12px; padding: 12px 14px; border: 1px solid #e2e8f0; border-radius: 12px; background: #f8fafc; }
.connection-label { color: #475569; font-weight: 600; }
.connection-item code { overflow: hidden; color: #0f172a; font-size: 12px; text-overflow: ellipsis; white-space: nowrap; }
.desktop-note { margin: -8px 2px 0; color: #64748b; font-size: 13px; line-height: 1.6; }
.complete-actions { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
@media (max-width: 600px) { .connection-item { grid-template-columns: 1fr auto; } .connection-label { grid-column: 1 / -1; } }
@media (max-width: 600px) { .complete-actions { grid-template-columns: 1fr; } }
</style>
