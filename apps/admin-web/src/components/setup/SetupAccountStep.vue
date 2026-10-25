<template>
  <div class="step-content">
    <div class="step-heading">
      <span class="step-kicker">{{ t('legacy.step_2_of_4') }}</span>
      <div class="section-heading">
        <span class="section-heading-icon" aria-hidden="true">
          <svg viewBox="0 0 24 24">
            <path d="M4 20v-9l8-5 8 5v9M9 20v-5h6v5M9 11h.01M15 11h.01" />
          </svg>
        </span>
        <div>
          <h2>{{ t('legacy.organization_initial_accounts') }}</h2>
          <p>{{ t('legacy.create_the_enterprise_administrator_and_first_employee_passwords_apply') }}</p>
        </div>
      </div>
    </div>

    <n-form label-placement="top">
      <n-grid :cols="2" :x-gap="12">
        <n-grid-item :span="2">
          <n-form-item :label="t('legacy.organization_name')">
            <n-input v-model:value="model.orgName" :placeholder="t('legacy.example_movo_technology_co_ltd')" />
          </n-form-item>
        </n-grid-item>
        <n-grid-item>
          <n-form-item :label="t('legacy.admin_username')">
            <n-input v-model:value="model.adminUsername" placeholder="admin" autocomplete="username" />
          </n-form-item>
        </n-grid-item>
        <n-grid-item>
          <n-form-item :label="t('legacy.admin_display_name')">
            <n-input v-model:value="model.adminDisplayName" :placeholder="t('legacy.system_administrator')" />
          </n-form-item>
        </n-grid-item>
        <n-grid-item :span="2">
          <n-form-item :label="t('legacy.admin_password')">
            <n-input v-model:value="model.adminPassword" type="password" show-password-on="click" autocomplete="new-password" />
          </n-form-item>
        </n-grid-item>
        <n-grid-item>
          <n-form-item :label="t('legacy.initial_employee_username')">
            <n-input v-model:value="model.employeeUsername" placeholder="user01" autocomplete="off" />
          </n-form-item>
        </n-grid-item>
        <n-grid-item>
          <n-form-item :label="t('legacy.initial_employee_name')">
            <n-input v-model:value="model.employeeName" :placeholder="t('legacy.john_doe')" />
          </n-form-item>
        </n-grid-item>
        <n-grid-item :span="2">
          <n-form-item :label="t('legacy.initial_employee_password')">
            <n-input v-model:value="model.employeePassword" type="password" show-password-on="click" autocomplete="new-password" />
          </n-form-item>
        </n-grid-item>
      </n-grid>

      <div class="section-heading quota-heading">
        <span class="section-heading-icon" aria-hidden="true">
            <svg viewBox="0 0 24 24">
              <ellipse cx="12" cy="6" rx="7" ry="3" />
              <path d="M5 6v5c0 1.7 3.1 3 7 3s7-1.3 7-3V6M5 11v5c0 1.7 3.1 3 7 3s7-1.3 7-3v-5" />
            </svg>
        </span>
        <div>
          <h2>{{ t('legacy.token_quotas') }}</h2>
          <p>{{ t('legacy.the_organization_quota_is_the_shared_per_period_limit') }}</p>
        </div>
      </div>
      <n-grid :cols="2" :x-gap="12">
        <n-grid-item>
          <n-form-item :label="t('legacy.organization_total_tokens')">
            <n-input-number v-model:value="model.orgTotalTokens" :min="1" :show-button="false" :placeholder="t('legacy.example_10000000')" style="width: 100%" />
          </n-form-item>
        </n-grid-item>
        <n-grid-item>
          <n-form-item :label="t('legacy.default_tokens_per_employee')">
            <n-input-number v-model:value="model.defaultUserTokens" :min="1" :max="model.orgTotalTokens || undefined" :show-button="false" :placeholder="t('legacy.example_1000000')" style="width: 100%" />
          </n-form-item>
        </n-grid-item>
      </n-grid>

      <p class="quota-period-note">
        {{ t('legacy.during_setup_both_organization_and_employee_quotas_reset_by') }}
      </p>

      <details class="quota-advanced">
        <summary>
          <span>{{ t('legacy.advanced_organization_time_zone') }}</span>
          <svg viewBox="0 0 24 24" aria-hidden="true"><path d="m6 9 6 6 6-6" /></svg>
        </summary>
        <div class="timezone-content">
          <p class="timezone-description">
            {{ t('legacy.the_time_zone_defines_calendar_boundaries_for_token_quotas') }}
          </p>
          <n-form-item :label="t('legacy.organization_time_zone')" :show-feedback="false">
            <n-select
              v-model:value="model.quotaTimezone"
              :options="timezoneOptions"
              filterable
              :placeholder="t('legacy.search_time_zones')"
            />
          </n-form-item>
          <div class="timezone-detected">
            <span>{{ t('legacy.browser_detected', { timezone: detectedTimezone }) }}</span>
            <n-button text type="primary" @click="model.quotaTimezone = detectedTimezone">
              {{ t('legacy.use_detected_value') }}
            </n-button>
          </div>
        </div>
      </details>
    </n-form>

    <n-button block type="primary" size="large" @click="$emit('next')">
      {{ t('legacy.next_base_model') }}
    </n-button>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import { t } from '@/composables/i18n';
import { getBrowserTimezone } from '@/composables/adminTimezone';
import type { SetupAccountForm } from './types';

const model = defineModel<SetupAccountForm>({ required: true });
defineEmits<{ next: [] }>();
const detectedTimezone = getBrowserTimezone();
const timezoneOptions = computed(() => {
  const supportedValuesOf = (Intl as typeof Intl & {
    supportedValuesOf?: (key: 'timeZone') => string[];
  }).supportedValuesOf;
  const supported = supportedValuesOf?.('timeZone') || [];
  const values = Array.from(new Set([
    detectedTimezone,
    'Asia/Shanghai',
    'UTC',
    ...supported,
  ]));
  return values.map((timezone) => ({
    label: timezone === detectedTimezone
      ? `${t('legacy.auto_detected')} · ${timezone}`
      : timezone,
    value: timezone,
  }));
});
</script>

<style scoped>
.step-content { display: grid; gap: 4px; }
.step-heading { margin-bottom: 14px; }
.step-kicker { color: #3568e8; font-size: 12px; font-weight: 700; letter-spacing: .08em; text-transform: uppercase; }
.section-heading { display: flex; align-items: flex-start; gap: 12px; margin-top: 8px; }
.section-heading-icon { display: grid; width: 38px; height: 38px; flex: 0 0 38px; place-items: center; border-radius: 11px; background: #eaf0ff; color: #315fc8; }
.section-heading-icon svg { width: 20px; fill: none; stroke: currentColor; stroke-linecap: round; stroke-linejoin: round; stroke-width: 1.8; }
.section-heading h2 { margin: 0 0 4px; color: #10204a; font-size: 24px; line-height: 1.35; }
.section-heading p { margin: 0; color: #64748b; font-size: 13px; line-height: 1.6; }
.quota-heading { margin: 10px 0 16px; padding-top: 20px; border-top: 1px solid #e2e8f0; }
.quota-period-note { margin: -2px 0 14px; color: #64748b; font-size: 12px; line-height: 1.6; }
.quota-advanced { margin: -2px 0 16px; overflow: hidden; border: 1px solid #e2e8f0; border-radius: 12px; background: #f8fafc; }
.quota-advanced summary { display: flex; min-height: 44px; align-items: center; justify-content: space-between; gap: 12px; padding: 0 14px; color: #34425e; cursor: pointer; font-size: 13px; font-weight: 600; list-style: none; }
.quota-advanced summary::-webkit-details-marker { display: none; }
.quota-advanced summary:focus-visible { outline: 3px solid rgba(53, 104, 232, .25); outline-offset: -3px; }
.quota-advanced summary svg { width: 17px; fill: none; stroke: currentColor; stroke-linecap: round; stroke-linejoin: round; stroke-width: 2; transition: transform .2s ease; }
.quota-advanced[open] summary { border-bottom: 1px solid #e2e8f0; }
.quota-advanced[open] summary svg { transform: rotate(180deg); }
.timezone-content { padding: 14px; }
.timezone-description { margin: 0 0 12px; color: #64748b; font-size: 13px; line-height: 1.6; }
.timezone-detected { display: flex; align-items: center; justify-content: space-between; gap: 12px; margin-top: 10px; color: #64748b; font-size: 12px; }
@media (max-width: 640px) {
  .timezone-detected { align-items: flex-start; flex-direction: column; gap: 6px; }
}
@media (prefers-reduced-motion: reduce) {
  .quota-advanced summary svg { transition: none; }
}
</style>
