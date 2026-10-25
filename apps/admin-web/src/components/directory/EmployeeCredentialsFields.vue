<script setup lang="ts">
import { computed } from 'vue';
import { t } from '@/composables/i18n';

const props = defineProps<{
  mode: 'create' | 'edit';
  source: 'local' | 'dingtalk' | 'wecom' | 'feishu';
}>();

const loginName = defineModel<string>('loginName', { required: true });
const password = defineModel<string>('password', { required: true });
const isLocal = computed(() => props.source === 'local');
const passwordLabel = computed(() => (props.mode === 'create' ? t('legacy.initial_password') : t('legacy.reset_password_optional')));
const passwordPlaceholder = computed(() => (props.mode === 'create' ? t('legacy.at_least_10_characters') : t('legacy.leave_blank_to_keep_current_password')));
</script>

<template>
  <section class="credentials-section" aria-labelledby="employee-credentials-heading">
    <div class="credentials-heading">
      <div>
        <h3 id="employee-credentials-heading">{{ t('legacy.sign_in_credentials') }}</h3>
        <p v-if="isLocal">
          {{ mode === 'create' ? t('legacy.create_credentials_the_employee_can_use_to_sign_in') : t('legacy.the_login_name_can_be_changed_leave_the_password') }}
        </p>
        <p v-else>{{ t('legacy.external_users_sign_in_through_their_identity_source_local') }}</p>
      </div>
      <n-tag size="small" :type="isLocal ? 'success' : 'default'">
        {{ isLocal ? t('legacy.local_account') : t('legacy.external_identity') }}
      </n-tag>
    </div>

    <n-grid v-if="isLocal" :cols="2" :x-gap="12">
      <n-grid-item>
        <n-form-item :label="t('legacy.login_name')" required>
          <n-input
            v-model:value="loginName"
            autocomplete="off"
            :placeholder="t('legacy.please_enter_login_name_for_sign_in')"
          />
        </n-form-item>
      </n-grid-item>
      <n-grid-item>
        <n-form-item :label="passwordLabel" :required="mode === 'create'">
          <n-input
            v-model:value="password"
            type="password"
            show-password-on="click"
            autocomplete="new-password"
            :placeholder="passwordPlaceholder"
          />
        </n-form-item>
      </n-grid-item>
    </n-grid>
  </section>
</template>

<style scoped>
.credentials-section {
  margin: 4px 0 18px;
  padding: 16px 16px 2px;
  border: 1px solid #dbe4f0;
  border-radius: 12px;
  background: #f8fafc;
}

.credentials-heading {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 14px;
}

.credentials-heading h3 {
  margin: 0;
  color: #172033;
  font-size: 15px;
  line-height: 22px;
}

.credentials-heading p {
  margin: 3px 0 0;
  color: #64748b;
  font-size: 12px;
  line-height: 18px;
}
</style>
