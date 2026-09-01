<template>
  <div class="setup-page">
    <div class="setup-panel">
      <header class="setup-copy">
        <div class="brand-mark">
          <img :src="movoLogo" alt="MOVO" />
        </div>
        <div>
          <div class="eyebrow">MOVO INITIAL SETUP</div>
          <h1>{{ setupCompleted ? t('系统已准备就绪') : t('初始化企业服务') }}</h1>
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
            {{ t('部分服务尚未就绪。可以稍后刷新状态；建议全部正常后再完成初始化。') }}
          </n-alert>
          <div v-if="currentStep === 1" class="deployment-actions">
            <n-button block type="primary" size="large" :disabled="!setupStore.ready" @click="currentStep = 2">
              {{ t('下一步：组织与账号') }}
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
  adminDisplayName: t('系统管理员'),
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
  provider: 'tavily',
  apiKey: '',
  endpoint: '',
  baseUrl: '',
  model: '',
  query: 'MOVO enterprise AI',
});

function updateSearchForm(value: SetupSearchForm) {
  Object.assign(searchForm, value);
}

const heroDescription = computed(() => setupCompleted.value
  ? t('初始化已完成。请保存以下企业访问地址，然后登录管理后台。')
  : t('完成部署检测、企业账号和模型配置后，员工即可登录使用。'));

function parseError(error: unknown, fallback: string) {
  if (axios.isAxiosError(error)) return String(error.response?.data?.detail || error.message || fallback);
  return fallback;
}

function validateAccountForm() {
  if (!accountForm.orgName.trim()) return t('请填写企业名称');
  if (!accountForm.adminUsername.trim() || !accountForm.employeeUsername.trim()) return t('请填写管理员和员工账号');
  if (accountForm.adminUsername.trim() === accountForm.employeeUsername.trim()) return t('管理员账号和员工账号不能相同');
  if (accountForm.adminPassword.trim().length < 6 || accountForm.employeePassword.trim().length < 6) return t('管理员和员工密码至少 6 位');
  if (!accountForm.employeeName.trim()) return t('请填写初始员工姓名');
  if (!accountForm.orgTotalTokens || accountForm.orgTotalTokens <= 0) return t('请填写企业总 Token');
  if (!accountForm.defaultUserTokens || accountForm.defaultUserTokens <= 0) return t('请填写员工默认 Token');
  if (accountForm.defaultUserTokens > accountForm.orgTotalTokens) return t('员工默认 Token 不能超过企业总 Token');
  if (!accountForm.quotaTimezone.trim()) return t('请填写企业时区');
  return '';
}

function validateModelForm() {
  if (!modelForm.providerId) return t('请选择模型供应商');
  if (!modelForm.displayName.trim() || !modelForm.modelName.trim()) return t('请填写配置名称和模型 ID');
  if (!modelForm.baseUrl.trim()) return t('请填写模型服务地址');
  if (!modelForm.apiKey.trim()) return t('请填写 API Key');
  const provider = providers.value.find((item) => item.id === modelForm.providerId);
  if (provider?.providerType === 'azure_openai' && !modelForm.apiVersion.trim()) return t('请填写 API Version');
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
    message.error(parseError(error, t('模型供应商加载失败')));
  } finally {
    providersLoading.value = false;
  }
}

function validateSearchForm() {
  if (!searchForm.enabled) return '';
  if (!searchForm.provider || !searchForm.apiKey.trim()) return t('请选择搜索服务并填写 API Key');
  if (searchForm.provider === 'baidu_qianfan' && !searchForm.endpoint.trim()) return t('请填写 Endpoint');
  if (searchForm.provider === 'volc_ark' && (!searchForm.baseUrl.trim() || !searchForm.model.trim())) {
    return t('请填写 Base URL 和 Bot Model');
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
  searchTestMessage.value = t('正在测试搜索连接…');
  try {
    const result = await testSetupSearch({ ...searchForm });
    searchTestState.value = 'success';
    searchTestMessage.value = result.message || t('搜索连接测试成功');
  } catch (error) {
    searchTestState.value = 'failed';
    searchTestMessage.value = parseError(error, t('搜索连接测试失败'));
  }
}

async function runModelTest() {
  const error = validateModelForm();
  if (error) return void message.warning(error);
  modelTestState.value = 'testing';
  modelTestMessage.value = t('正在连接模型，请稍候…');
  try {
    const result = await testSetupModel({ ...modelForm });
    modelTestState.value = result.success ? 'success' : 'failed';
    modelTestMessage.value = result.success ? t('模型连接测试成功。') : result.message;
  } catch (error) {
    modelTestState.value = 'failed';
    modelTestMessage.value = parseError(error, t('模型连接测试失败'));
  }
}

async function submitSetup() {
  const error = validateAccountForm() || validateModelForm() || optionalModelsError() || validateSearchForm();
  if (error || modelTestState.value !== 'success') return void message.warning(error || t('请先完成模型连接测试'));
  if (searchForm.enabled && searchTestState.value !== 'success') return void message.warning(t('请先完成搜索连接测试'));
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
    message.success(t('初始化完成，租户ID：{id}', { id: result.mainId }));
  } catch (error) {
    message.error(parseError(error, t('初始化失败')));
  } finally {
    submitting.value = false;
  }
}

async function copyText(value: string) {
  try { await navigator.clipboard.writeText(value); message.success(t('已复制')); }
  catch { message.error(t('复制失败，请手动复制')); }
}

async function refreshStatus() {
  try { await setupStore.ensureStatus(true); }
  catch { message.error(t('部署状态刷新失败')); }
}

function validateSpecificModel(form: SetupModelForm) {
  if (!form.providerId || !form.displayName.trim() || !form.modelName.trim() || !form.baseUrl.trim() || !form.apiKey.trim()) {
    return t('请完整填写已启用的可选模型配置');
  }
  const provider = providers.value.find((item) => item.id === form.providerId);
  if (provider?.providerType === 'azure_openai' && !form.apiVersion.trim()) return t('请填写 API Version');
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
    if (setupStore.completed) { message.info(t('系统已完成初始化，请直接登录')); router.replace('/login'); return; }
    await loadProviders();
  } catch (error) {
    console.error(error);
    message.error(t('无法获取初始化状态，请检查 admin-api 是否已启动'));
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
