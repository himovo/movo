<template>
  <div class="step-content">
    <div class="step-heading">
      <span class="step-kicker">{{ t('legacy.step_3_of_4') }}</span>
      <h2>{{ t('legacy.configure_organization_chat_model') }}</h2>
      <p>{{ t('legacy.credentials_are_encrypted_setup_can_finish_only_after_a') }}</p>
    </div>

    <n-alert type="info" :show-icon="true" class="security-note">
      {{ t('legacy.the_api_key_is_never_returned_to_the_browser') }}
    </n-alert>

    <SetupModelFields v-model="model" :providers="providers" :providers-loading="providersLoading" />

    <n-alert v-if="testMessage" :type="testState === 'success' ? 'success' : testState === 'failed' ? 'error' : 'info'" :show-icon="true" class="test-result">
      {{ testMessage }}
    </n-alert>

    <div class="actions">
      <n-button size="large" :disabled="submitting" @click="$emit('back')">{{ t('legacy.previous') }}</n-button>
      <n-button size="large" secondary type="primary" :loading="testState === 'testing'" :disabled="submitting" @click="$emit('test')">
        {{ t('legacy.test_model_connection') }}
      </n-button>
      <n-button size="large" type="primary" :loading="submitting" :disabled="testState !== 'success'" @click="$emit('next')">
        {{ t('legacy.next_other_models') }}
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
