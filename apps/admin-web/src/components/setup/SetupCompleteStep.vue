<template>
  <div class="complete-content">
    <n-alert type="success" :show-icon="true" :title="t('初始化完成')">
      {{ t('企业、初始账号和企业模型均已配置，可以开始使用 MOVO。') }}
    </n-alert>
    <div class="connection-list">
      <div v-for="item in items" :key="item.key" class="connection-item">
        <span class="connection-label">{{ item.label }}</span>
        <code>{{ item.value }}</code>
        <n-button size="small" secondary :disabled="!item.value" @click="$emit('copy', item.value)">{{ t('复制') }}</n-button>
      </div>
    </div>
    <p class="desktop-note">{{ t('桌面端只需填写企业服务地址，系统会自动连接 API 与浏览器 Agent，无需单独配置 WebSocket。') }}</p>
    <div class="complete-actions">
      <n-button size="large" secondary @click="downloadConnectionFile">{{ t('下载连接配置') }}</n-button>
      <n-button type="primary" size="large" @click="$emit('login')">{{ t('登录管理后台') }}</n-button>
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
  { key: 'user', label: t('员工 Web'), value: props.urls.userWeb },
  { key: 'admin', label: t('管理后台'), value: props.urls.adminWeb },
  { key: 'desktop', label: t('桌面端连接地址'), value: props.urls.desktopService },
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
