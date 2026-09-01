<template>
  <div class="step-content">
    <div class="step-heading">
      <span class="step-kicker">{{ t('步骤 3 / 4') }}</span>
      <h2>{{ t('配置企业对话模型') }}</h2>
      <p>{{ t('配置将加密保存。连接测试成功后才能完成初始化。') }}</p>
    </div>

    <n-alert type="info" :show-icon="true" class="security-note">
      {{ t('API Key 不会返回到浏览器，保存后仅显示掩码。') }}
    </n-alert>

    <SetupModelFields v-model="model" :providers="providers" :providers-loading="providersLoading" />

    <n-alert v-if="testMessage" :type="testState === 'success' ? 'success' : testState === 'failed' ? 'error' : 'info'" :show-icon="true" class="test-result">
      {{ testMessage }}
    </n-alert>

    <div class="actions">
      <n-button size="large" :disabled="submitting" @click="$emit('back')">{{ t('上一步') }}</n-button>
      <n-button size="large" secondary type="primary" :loading="testState === 'testing'" :disabled="submitting" @click="$emit('test')">
        {{ t('测试模型连接') }}
      </n-button>
      <n-button size="large" type="primary" :loading="submitting" :disabled="testState !== 'success'" @click="$emit('next')">
        {{ t('下一步：其他模型') }}
      </n-button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { t } from '@/composables/i18n';
import type { SetupModelProvider } from '@/api/setup';
import type { ModelTestState, SetupModelForm } from './types';
import SetupModelFields from './SetupModelFields.vue';

const props = defineProps<{
  providers: SetupModelProvider[];
  providersLoading: boolean;
  testState: ModelTestState;
  testMessage: string;
  submitting: boolean;
}>();
const model = defineModel<SetupModelForm>({ required: true });
defineEmits<{ back: []; test: []; next: [] }>();
</script>

<style scoped>
.step-content { display: grid; gap: 4px; }
.step-heading { margin-bottom: 12px; }
.step-kicker { color: #3568e8; font-size: 12px; font-weight: 700; letter-spacing: .08em; text-transform: uppercase; }
.step-heading h2 { margin: 6px 0; color: #10204a; font-size: 24px; }
.step-heading p { margin: 0; color: #64748b; line-height: 1.6; }
.security-note { margin-bottom: 14px; }
.test-result { margin: 4px 0 14px; }
.actions { display: grid; grid-template-columns: auto 1fr 1fr; gap: 10px; }
@media (max-width: 600px) { .actions { grid-template-columns: 1fr; } }
</style>
