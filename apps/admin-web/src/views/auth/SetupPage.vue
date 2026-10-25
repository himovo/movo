<template>
  <div class="setup-page">
    <div class="setup-panel">
      <header class="setup-copy">
        <div class="brand-mark">
          <img :src="movoLogo" alt="MOVO" />
        </div>
        <div>
          <div class="eyebrow">MOVO INITIAL SETUP</div>
          <h1>{{ setupCompleted ? t('legacy.system_ready') : t('legacy.set_up_enterprise_service') }}</h1>
          <p>{{ heroDescription }}</p>
        </div>
      </header>

      <SetupProgressSteps :current="currentStep" />

      <n-card class="setup-card" :bordered="false">
        <SetupDeploymentStatus
          v-if="currentStep === 1"
          :ready="setupStore.ready"
          :loading="setupStore.loading"
          :services="setupStore.services"
          @refresh="refreshStatus"
        />

        <SetupCompleteStep
          v-if="setupCompleted"
          :urls="setupStore.urls"
          :org-name="setupStore.orgName || accountForm.orgName"
          :main-id="setupStore.mainId"
          :org-total-tokens="accountForm.orgTotalTokens || 0"
          :default-user-tokens="accountForm.defaultUserTokens || 0"
          @copy="copyText"
          @login="router.push('/login')"
        />

        <template v-else>
          <n-alert v-if="currentStep === 1 && !setupStore.ready" type="warning" :show-icon="true" class="readiness-alert">
            {{ t('legacy.some_services_are_not_ready_refresh_later_and_complete') }}
          </n-alert>
          <div v-if="currentStep === 1" class="deployment-actions">
            <n-button block type="primary" size="large" :disabled="!setupStore.ready" @click="currentStep = 2">
              {{ t('legacy.next_organization_accounts') }}
            </n-button>
          </div>
          <SetupAccountStep v-else-if="currentStep === 2" :model-value="accountForm" @next="goToModelStep" />
          <SetupModelStep
            v-else-if="currentStep === 3"
            :model-value="modelForm"
            :providers="providers"
            :providers-loading="providersLoading"
            :test-state="modelTestState"
            :test-message="modelTestMessage"
            :submitting="submitting"
            @back="currentStep = 2"
            @test="runModelTest"
            @next="currentStep = 4"
          />
          <SetupOptionalModelsStep
            v-else-if="currentStep === 4"
            v-model="optionalModelForms"
            :providers="providers"
            :providers-loading="providersLoading"
            :submitting="submitting"
            @back="currentStep = 3"
            @next="goToSearchStep"
          />
          <SetupSearchStep
            v-else-if="currentStep === 5"
            :model-value="searchForm"
            @update:model-value="updateSearchForm"
            :providers="searchProviders"
            :providers-loading="providersLoading"
            :test-state="searchTestState"
            :test-message="searchTestMessage"
            :submitting="submitting"
            @back="currentStep = 4"
            @test="runSearchTest"
            @submit="submitSetup"
          />
        </template>
      </n-card>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue';
import { useRouter } from 'vue-router';
import { useMessage } from 'naive-ui';
import axios from 'axios';
import movoLogo from '@/assets/images/movo-logo.png';
import {
  fetchSetupModelProviders,
  fetchSetupSearchProviders,
  initializeSetup,
  testSetupModel,
  testSetupSearch,
  type SetupModelProvider,
  type SetupSearchProvider,
} from '@/api/setup';
import SetupAccountStep from '@/components/setup/SetupAccountStep.vue';
import SetupCompleteStep from '@/components/setup/SetupCompleteStep.vue';
import SetupDeploymentStatus from '@/components/setup/SetupDeploymentStatus.vue';
import SetupModelStep from '@/components/setup/SetupModelStep.vue';
import SetupOptionalModelsStep from '@/components/setup/SetupOptionalModelsStep.vue';
import SetupProgressSteps from '@/components/setup/SetupProgressSteps.vue';
import SetupSearchStep from '@/components/setup/SetupSearchStep.vue';
import type {
  ModelTestState,
  SearchTestState,
  SetupAccountForm,
  SetupModelForm,
  SetupOptionalModelForm,
  SetupSearchForm,
} from '@/components/setup/types';
import { t } from '@/composables/i18n';
import { getBrowserTimezone } from '@/composables/adminTimezone';
import { useSetupStore } from '@/stores/setup';

const router = useRouter();
const message = useMessage();
const setupStore = useSetupStore();
const currentStep = ref(1);
const submitting = ref(false);
const setupCompleted = ref(false);
const providers = ref<SetupModelProvider[]>([]);
const searchProviders = ref<SetupSearchProvider[]>([]);
const providersLoading = ref(false);
const modelTestState = ref<ModelTestState>('idle');
const modelTestMessage = ref('');
const searchTestState = ref<SearchTestState>('idle');
const searchTestMessage = ref('');

const accountForm = reactive<SetupAccountForm>({
  orgName: '',
  adminUsername: 'admin',
  adminPassword: '',
  adminDisplayName: t('legacy.system_administrator'),
  employeeUsername: 'user01',
  employeePassword: '',
  employeeName: '',
  orgTotalTokens: null,
  defaultUserTokens: null,
  quotaPeriod: 'monthly',
  quotaTimezone: getBrowserTimezone(),
});

const modelForm = reactive<SetupModelForm>({
  providerId: '',
  displayName: '',
  modelName: '',
  baseUrl: '',
  apiVersion: '',
  apiKey: '',
  capability: 'chat',
});

function optionalModel(capability: SetupOptionalModelForm['capability']): SetupOptionalModelForm {
  return {
    capability,
    enabled: false,
    model: {
      providerId: '', displayName: '', modelName: '', baseUrl: '', apiVersion: '', apiKey: '', capability,
    },
  };
}

const optionalModelForms = ref<SetupOptionalModelForm[]>([
  optionalModel('embedding'), optionalModel('rerank'), optionalModel('vision'), optionalModel('image'),
]);

const searchForm = reactive<SetupSearchForm>({
  enabled: false,
  provider: 'deepseek',
  apiKey: '',
  endpoint: 'https://api.deepseek.com/v1/tools/search',
  baseUrl: '',
  model: '',
  query: 'MOVO enterprise AI',
});

function updateSearchForm(value: SetupSearchForm) {
  Object.assign(searchForm, value);
}

const heroDescription = computed(() => setupCompleted.value
  ? t('legacy.setup_is_complete_save_the_enterprise_access_addresses_below')
  : t('legacy.employees_can_sign_in_after_deployment_accounts_and_models'));

function parseError(error: unknown, fallback: string) {
  if (axios.isAxiosError(error)) return String(error.response?.data?.detail || error.message || fallback);
  return fallback;
}

function validateAccountForm() {
  if (!accountForm.orgName.trim()) return t('legacy.please_enter_organization_name');
  if (!accountForm.adminUsername.trim() || !accountForm.employeeUsername.trim()) return t('legacy.enter_both_admin_and_employee_usernames');
  if (accountForm.adminUsername.trim() === accountForm.employeeUsername.trim()) return t('legacy.admin_and_employee_usernames_must_be_different');
  if (accountForm.adminPassword.trim().length < 10 || accountForm.employeePassword.trim().length < 10) return t('legacy.admin_and_employee_passwords_must_be_at_least_10');
  if (!accountForm.employeeName.trim()) return t('legacy.please_enter_initial_employee_name');
  if (!accountForm.orgTotalTokens || accountForm.orgTotalTokens <= 0) return t('legacy.enter_the_organization_token_quota');
  if (!accountForm.defaultUserTokens || accountForm.defaultUserTokens <= 0) return t('legacy.enter_the_default_employee_token_quota');
  if (accountForm.defaultUserTokens > accountForm.orgTotalTokens) return t('legacy.default_employee_tokens_cannot_exceed_the_organization_total');
  if (!accountForm.quotaTimezone.trim()) return t('legacy.enter_the_organization_time_zone');
  return '';
}

function validateModelForm() {
  if (!modelForm.providerId) return t('legacy.select_a_model_provider');
  if (!modelForm.displayName.trim() || !modelForm.modelName.trim()) return t('legacy.enter_a_configuration_name_and_model_id');
  if (!modelForm.baseUrl.trim()) return t('legacy.enter_the_model_service_url');
  if (!modelForm.apiKey.trim()) return t('legacy.enter_an_api_key');
  const provider = providers.value.find((item) => item.id === modelForm.providerId);
  if (provider?.providerType === 'azure_openai' && !modelForm.apiVersion.trim()) return t('legacy.enter_an_api_version');
  return '';
}

function goToModelStep() {
  const error = validateAccountForm();
  if (error) return void message.warning(error);
  currentStep.value = 3;
}

async function loadProviders() {
  providersLoading.value = true;
  try {
    const [modelProviders, externalSearchProviders] = await Promise.all([
      fetchSetupModelProviders(),
      fetchSetupSearchProviders(),
    ]);
    providers.value = modelProviders;
    searchProviders.value = externalSearchProviders;
    if (!modelForm.providerId && providers.value.length) modelForm.providerId = providers.value[0].id;
    const firstSearchProvider = searchProviders.value[0];
    if (firstSearchProvider) {
      searchForm.provider = firstSearchProvider.id;
      searchForm.endpoint = firstSearchProvider.defaultEndpoint;
      searchForm.baseUrl = firstSearchProvider.defaultBaseUrl;
    }
  } catch (error) {
    message.error(parseError(error, t('legacy.failed_to_load_model_providers')));
  } finally {
    providersLoading.value = false;
  }
}

function validateSearchForm() {
  if (!searchForm.enabled) return '';
  if (!searchForm.provider || !searchForm.apiKey.trim()) return t('legacy.choose_a_search_provider_and_enter_its_api_key');
  if (searchForm.provider === 'baidu_qianfan' && !searchForm.endpoint.trim()) return t('legacy.enter_the_endpoint');
  if (searchForm.provider === 'volc_ark' && (!searchForm.baseUrl.trim() || !searchForm.model.trim())) {
    return t('legacy.enter_the_base_url_and_bot_model');
  }
  return '';
}

function optionalModelsError() {
  return optionalModelForms.value
    .filter((item) => item.enabled)
    .map((item) => validateSpecificModel(item.model))
    .find(Boolean) || '';
}

function goToSearchStep() {
  const error = optionalModelsError();
  if (error) return void message.warning(error);
  currentStep.value = 5;
}

async function runSearchTest() {
  const error = validateSearchForm();
  if (error) return void message.warning(error);
  searchTestState.value = 'testing';
  searchTestMessage.value = t('legacy.testing_search_connection');
  try {
    const result = await testSetupSearch({ ...searchForm });
    searchTestState.value = 'success';
    searchTestMessage.value = result.message || t('legacy.search_connection_test_succeeded');
  } catch (error) {
    searchTestState.value = 'failed';
    searchTestMessage.value = parseError(error, t('legacy.search_connection_test_failed'));
  }
}

async function runModelTest() {
  const error = validateModelForm();
  if (error) return void message.warning(error);
  modelTestState.value = 'testing';
  modelTestMessage.value = t('legacy.connecting_to_the_model_please_wait');
  try {
    const result = await testSetupModel({ ...modelForm });
    modelTestState.value = result.success ? 'success' : 'failed';
    modelTestMessage.value = result.success ? t('legacy.model_connection_tested_successfully') : result.message;
  } catch (error) {
    modelTestState.value = 'failed';
    modelTestMessage.value = parseError(error, t('legacy.model_connection_test_failed'));
  }
}

async function submitSetup() {
  const error = validateAccountForm() || validateModelForm() || optionalModelsError() || validateSearchForm();
  if (error || modelTestState.value !== 'success') return void message.warning(error || t('legacy.complete_the_model_connection_test_first'));
  if (searchForm.enabled && searchTestState.value !== 'success') return void message.warning(t('legacy.complete_the_search_connection_test_first'));
  submitting.value = true;
  try {
    const result = await initializeSetup({
      ...accountForm,
      orgName: accountForm.orgName.trim(), adminUsername: accountForm.adminUsername.trim(),
      adminDisplayName: accountForm.adminDisplayName.trim(), employeeUsername: accountForm.employeeUsername.trim(),
      employeeName: accountForm.employeeName.trim(), model: { ...modelForm },
      orgTotalTokens: accountForm.orgTotalTokens || 0,
      defaultUserTokens: accountForm.defaultUserTokens || 0,
      quotaPeriod: accountForm.quotaPeriod,
      quotaTimezone: accountForm.quotaTimezone.trim(),
      additionalModels: optionalModelForms.value.filter((item) => item.enabled).map((item) => ({ ...item.model })),
      externalSearch: searchForm.enabled ? {
        provider: searchForm.provider,
        apiKey: searchForm.apiKey,
        endpoint: searchForm.endpoint,
        baseUrl: searchForm.baseUrl,
        model: searchForm.model,
        query: searchForm.query,
      } : null,
    });
    await setupStore.ensureStatus(true);
    setupCompleted.value = true;
    currentStep.value = 6;
    message.success(t('legacy.initialization_complete_tenant_id', { id: result.mainId }));
  } catch (error) {
    message.error(parseError(error, t('legacy.initialization_failed')));
  } finally {
    submitting.value = false;
  }
}

async function copyText(value: string) {
  try { await navigator.clipboard.writeText(value); message.success(t('legacy.copied')); }
  catch { message.error(t('legacy.copy_failed_please_copy_manually')); }
}

async function refreshStatus() {
  try { await setupStore.ensureStatus(true); }
  catch { message.error(t('legacy.failed_to_refresh_deployment_status')); }
}

function validateSpecificModel(form: SetupModelForm) {
  if (!form.providerId || !form.displayName.trim() || !form.modelName.trim() || !form.baseUrl.trim() || !form.apiKey.trim()) {
    return t('legacy.complete_every_enabled_optional_model_configuration');
  }
  const provider = providers.value.find((item) => item.id === form.providerId);
  if (provider?.providerType === 'azure_openai' && !form.apiVersion.trim()) return t('legacy.enter_an_api_version');
  return '';
}

watch(modelForm, () => {
  if (modelTestState.value !== 'testing') { modelTestState.value = 'idle'; modelTestMessage.value = ''; }
}, { deep: true });

watch(searchForm, () => {
  if (searchTestState.value !== 'testing') { searchTestState.value = 'idle'; searchTestMessage.value = ''; }
}, { deep: true });

onMounted(async () => {
  try {
    await setupStore.ensureStatus();
    if (setupStore.completed) { message.info(t('legacy.the_system_has_been_initialized_please_sign_in_directly')); router.replace('/login'); return; }
    await loadProviders();
  } catch (error) {
    console.error(error);
    message.error(t('legacy.unable_to_fetch_initialization_status_please_check_if_the'));
  }
});
</script>

<style scoped>
.setup-page {
  min-height: 100vh;
  padding: 36px 20px 56px;
  background:
    radial-gradient(circle at 12% 4%, rgba(99, 142, 255, .15), transparent 30%),
    radial-gradient(circle at 88% 88%, rgba(69, 112, 229, .1), transparent 28%),
    #f1f5ff;
}

.setup-panel { display: grid; width: min(820px, 100%); margin: 0 auto; gap: 16px; }
.setup-copy { display: flex; align-items: center; gap: 20px; padding: 22px 26px; border-radius: 22px; background: linear-gradient(135deg, #1d3e91, #315ec8); color: #fff; box-shadow: 0 18px 48px rgba(35, 73, 160, .2); }
.brand-mark { display: grid; width: 64px; height: 58px; flex: 0 0 64px; place-items: center; border: 1px solid rgba(255,255,255,.22); border-radius: 17px; background: rgba(255,255,255,.12); }
.brand-mark img { display: block; width: 48px; height: 40px; object-fit: contain; }
.eyebrow { font-size: 11px; font-weight: 700; letter-spacing: .18em; color: rgba(255,255,255,.72); }
.setup-copy h1 { margin: 5px 0 4px; font-size: clamp(26px, 4vw, 34px); line-height: 1.2; }
.setup-copy p { max-width: 650px; margin: 0; color: rgba(255,255,255,.82); font-size: 14px; line-height: 1.6; }
.setup-card { border-radius: 22px; box-shadow: 0 24px 70px rgba(27, 55, 116, .12); }
.readiness-alert { margin-bottom: 18px; }
.deployment-actions { margin-top: 4px; }

@media (max-width: 600px) {
  .setup-page { padding: 18px 12px 32px; }
  .setup-copy { align-items: flex-start; padding: 20px; border-radius: 18px; }
  .brand-mark { width: 48px; height: 44px; flex-basis: 48px; border-radius: 13px; }
  .brand-mark img { width: 38px; height: 32px; }
  .setup-copy h1 { font-size: 25px; }
}
</style>
