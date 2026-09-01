<template>
  <div class="page-stack model-page">

    <div class="metrics-row">
      <n-card v-for="item in metricCards" :key="item.key" class="metric-card" :bordered="false" size="small">
        <div class="metric-main">
          <span class="metric-icon" :class="`metric-icon-${item.key}`" v-html="item.icon"></span>
          <div class="metric-body">
            <div class="metric-label">{{ item.label }}</div>
            <div class="metric-value">{{ item.value }}</div>
          </div>
        </div>
        <div class="metric-note">{{ item.note }}</div>
      </n-card>
    </div>

    <n-card class="list-card shell-card" :bordered="false" size="large">
      <n-alert
        v-if="orgQuota === 0 && instances.length > 0"
        type="warning"
        closable
        class="quota-warning-alert"
        :title="t('企业额度警示')"
        style="margin-bottom: 16px;"
      >
        {{ t('当前企业本周期总额度为 0，所有模型将无法被调用。请先前往') }}
        <router-link to="/organizations/traffic?open=quota" class="alert-link" style="color: #2563eb; font-weight: 600; text-decoration: underline;">
          {{ t('流量分配') }}
        </router-link>
        {{ t('配置企业总额度与成员额度。') }}
      </n-alert>

      <div class="list-filter-row">

        <div class="filter-toolbar">
          <n-space align="center" :size="10" class="filter-left">
            <n-input v-model:value="filters.keyword" :placeholder="t('搜索名称 / 模型 ID / Base URL')" clearable class="keyword-input" />
            <n-select
              v-model:value="filters.providerId"
              :options="providerOptions"
              :placeholder="t('供应商')"
              clearable
              style="width: 160px"
            />
            <n-select
              v-model:value="filters.status"
              :options="statusOptions"
              :placeholder="t('状态')"
              clearable
              style="width: 120px"
            />
          </n-space>
          <n-space :size="10" class="filter-right">
            <n-button secondary @click="reload">
              <template #icon>
                <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                  <path d="M21 12a9 9 0 0 0-9-9 9.75 9.75 0 0 0-6.74 2.74L3 8" />
                  <path d="M3 3v5h5" />
                  <path d="M3 12a9 9 0 0 0 9 9 9.75 9.75 0 0 0 6.74-2.74L21 16" />
                  <path d="M16 16h5v5" />
                </svg>
              </template>
              {{ t('刷新') }}
            </n-button>
            <n-button type="primary" strong @click="openCreate">
              <template #icon>
                <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                  <path d="M5 12h14" />
                  <path d="M12 5v14" />
                </svg>
              </template>
              {{ t('新增模型') }}
            </n-button>
          </n-space>
        </div>
      </div>

      <div class="list-body">
        <n-spin :show="loading">
          <div v-if="filteredInstances.length" class="model-grid">
            <button
              v-for="model in filteredInstances"
              :key="model.id"
              class="model-config-card"
              type="button"
              @click="openEdit(model)"
            >
              <div class="card-head">
                <span class="provider-badge">{{ model.providerName || t('自定义') }}</span>
                <n-space :size="6" class="state-tags">
                  <n-tag :type="model.status === 'active' ? 'success' : 'default'" size="small" :bordered="false">
                    {{ model.status === 'active' ? t('启用') : t('禁用') }}
                  </n-tag>
                </n-space>
              </div>

              <div class="card-body">
                <div class="card-title">{{ model.displayName }}</div>
                <div class="card-model-id">{{ model.modelName }}</div>
              </div>

              <div class="capability-row">
                <n-tag
                  v-for="item in model.capabilities"
                  :key="item"
                  size="small"
                  :bordered="false"
                  class="capability-tag"
                >
                  {{ capabilityLabel(item) }}
                </n-tag>
              </div>

              <div class="card-footnote">
                {{ t('最近更新：') }}{{ formatAdminDateTime(model.updatedAt, t('未知')) }}
              </div>

              <div class="card-bottom">
                <div class="card-actions">
                  <n-button size="small" tertiary @click.stop="runTest(model)">{{ t('测试') }}</n-button>
                  <n-button size="small" tertiary type="error" @click.stop="confirmDelete(model)">{{ t('删除') }}</n-button>
                </div>
              </div>
            </button>

            <button class="model-config-card add-model-card" type="button" @click="openCreate">
              <div class="add-symbol">+</div>
              <div class="add-title">{{ t('新增模型') }}</div>
              <div class="add-copy">{{ t('配置 OpenAI、Azure OpenAI、通义千问、DeepSeek 或自定义兼容接口。') }}</div>
            </button>
          </div>

          <n-empty v-else :description="t('暂无模型配置')">
            <template #extra>
              <n-button type="primary" @click="openCreate">{{ t('新增第一个模型') }}</n-button>
            </template>
          </n-empty>
        </n-spin>
      </div>
    </n-card>
  </div>

  <n-modal v-model:show="editorVisible" preset="card" :title="editorTitle" style="width: 980px">
    <div class="editor-layout" :class="{ 'single-column': editorMode === 'create' }">
      <n-form class="editor-form" :model="form" label-placement="left" label-width="96">
        <n-grid :cols="2" :x-gap="14">
          <n-grid-item>
            <n-form-item :label="t('供应商')">
              <n-select
                v-model:value="form.providerId"
                :options="providerOptions"
                :placeholder="t('选择供应商')"
              />
            </n-form-item>
          </n-grid-item>
          <n-grid-item>
            <n-form-item :label="t('显示名称')">
              <n-input v-model:value="form.displayName" :placeholder="t('如: OpenAI 主模型')" />
            </n-form-item>
          </n-grid-item>
          <n-grid-item>
            <n-form-item :label="modelFieldLabel">
              <n-input v-model:value="form.modelName" :placeholder="modelFieldPlaceholder" />
            </n-form-item>
          </n-grid-item>
          <n-grid-item>
            <n-form-item :label="t('状态')">
              <n-select v-model:value="form.status" :options="statusOptions" />
            </n-form-item>
          </n-grid-item>
          <n-grid-item :span="2">
            <n-form-item label="Base URL">
              <n-input v-model:value="form.baseUrl" :placeholder="baseUrlPlaceholder" />
            </n-form-item>
          </n-grid-item>
          <n-grid-item v-if="isAzureProvider">
            <n-form-item label="API Version">
              <n-input v-model:value="form.apiVersion" placeholder="如: 2024-10-21" />
            </n-form-item>
          </n-grid-item>
          <n-grid-item>
            <n-form-item label="API Key">
              <n-input
                v-model:value="form.apiKey"
                type="password"
                show-password-on="click"
                :placeholder="apiKeyPlaceholder"
              />
            </n-form-item>
          </n-grid-item>
          <n-grid-item>
            <n-form-item :label="t('能力')">
              <n-select v-model:value="form.capabilities" multiple :options="capabilityOptions" />
            </n-form-item>
          </n-grid-item>
        </n-grid>
        <div class="form-hint">
          {{ t('保存后仅返回脱敏 Key。编辑已有模型时，API Key 留空会保留原值。') }}
          <template v-if="isAzureProvider"> {{ t('Azure OpenAI 请在“模型 ID”填写 Deployment 名称。') }}</template>
        </div>
      </n-form>

      <aside v-if="editorMode === 'edit'" class="test-panel">
        <div class="test-title">{{ t('配置测试') }}</div>
        <div class="test-summary">
          <div>
            <span>{{ t('供应商') }}</span>
            <strong>{{ currentProvider?.name || t('未选择') }}</strong>
          </div>
          <div>
            <span>{{ t('模型 ID') }}</span>
            <strong>{{ form.modelName || t('未填写') }}</strong>
          </div>
          <div>
            <span>Base URL</span>
            <strong>{{ form.baseUrl || currentProvider?.defaultBaseUrl || t('未设置') }}</strong>
          </div>
          <div v-if="isAzureProvider">
            <span>API Version</span>
            <strong>{{ form.apiVersion || t('未填写（默认 2024-10-21）') }}</strong>
          </div>
          <div>
            <span>{{ t('Key 状态') }}</span>
            <strong>{{ keyStateText }}</strong>
          </div>
        </div>

        <n-input
          v-model:value="testPrompt"
          type="textarea"
          :rows="4"
          :placeholder="t('测试提示词，后续接入 runtime 后用于发起一次轻量调用')"
        />
        <n-button block type="primary" secondary :loading="testing" :disabled="!form.id" @click="runEditorTest">
          {{ t('测试当前配置') }}
        </n-button>
        <div class="test-result" :class="{ success: testResultType === 'success', failed: testResultType === 'failed' }">
          {{ testResultText }}
        </div>
      </aside>
    </div>

    <template #footer>
      <n-space justify="space-between" align="center">
        <n-button v-if="editorMode === 'edit'" tertiary type="error" @click="confirmDeleteFromEditor">{{ t('删除模型') }}</n-button>
        <span v-else />
        <n-space>
          <n-button @click="editorVisible = false">{{ t('取消') }}</n-button>
          <n-button type="primary" :loading="saving" @click="saveModel">{{ t('保存') }}</n-button>
        </n-space>
      </n-space>
    </template>
  </n-modal>
</template>

<script setup lang="ts">
import { computed, nextTick, onMounted, ref, watch } from 'vue';
import { useRouter } from 'vue-router';
import axios from 'axios';
import { useDialog, useMessage } from 'naive-ui';
import PageIntro from '@/components/PageIntro.vue';
import { t } from '@/composables/i18n';
import { formatAdminDateTime } from '@/composables/adminTimezone';
import {
  createModelInstance,
  deleteModelInstance,
  fetchModelInstances,
  fetchModelProviders,
  streamModelInstanceTest,
  updateModelInstance,
  type ModelInstanceItem,
  type ModelInstancePayload,
  type ModelProviderItem,
  type ModelStatus,
} from '@/api/models';
import { fetchTrafficAllocationOverview } from '@/api/traffic-allocations';


interface ModelForm extends ModelInstancePayload {
  id: string;
  apiKeyMasked: string;
}

const loading = ref(false);
const saving = ref(false);
const testing = ref(false);
const message = useMessage();
const dialog = useDialog();
const router = useRouter();
const providers = ref<ModelProviderItem[]>([]);
const instances = ref<ModelInstanceItem[]>([]);
const editorVisible = ref(false);
const editorMode = ref<'create' | 'edit'>('create');
const suppressProviderChange = ref(false);
const testPrompt = ref('请用一句话回复当前模型连接测试。');
const testResultText = ref('保存模型配置后可测试。');
const testResultType = ref<'idle' | 'success' | 'failed'>('idle');

const filters = ref({
  keyword: '',
  providerId: null as string | null,
  status: null as ModelStatus | null,
});

const defaultForm = (): ModelForm => ({
  id: '',
  providerId: '',
  orgId: '',
  displayName: '',
  modelName: '',
  baseUrl: '',
  apiVersion: '',
  apiKey: '',
  apiKeyMasked: '',
  capabilities: ['chat'],
  status: 'active',
  isDefault: false,
});

const form = ref<ModelForm>(defaultForm());
const orgQuota = ref<number | null>(null);


const statusOptions = computed(() => [
  { label: t('启用'), value: 'active' },
  { label: t('禁用'), value: 'disabled' },
]);

const capabilityOptions = computed(() => [
  { label: t('对话 Chat'), value: 'chat' },
  { label: t('视觉 Vision'), value: 'vision' },
  { label: t('向量 Embedding'), value: 'embedding' },
  { label: t('重排 Rerank'), value: 'rerank' },
  { label: t('图像 Image'), value: 'image' },
]);

const providerOptions = computed(() =>
  providers.value
    .filter((item) => item.status === 'active')
    .map((item) => ({
      label: item.name,
      value: item.id,
    })),
);

const providerMap = computed(() => new Map(providers.value.map((item) => [item.id, item])));
const currentProvider = computed(() => providerMap.value.get(form.value.providerId));
const isAzureProvider = computed(() => currentProvider.value?.providerType === 'azure_openai');
const editorTitle = computed(() => (editorMode.value === 'create' ? t('新增模型配置') : t('模型配置详情')));
const apiKeyPlaceholder = computed(() =>
  editorMode.value === 'create' ? t('请输入 API Key') : t('留空则保留当前 Key'),
);
const modelFieldLabel = computed(() => (isAzureProvider.value ? t('Deployment 名称') : t('模型 ID')));
const modelFieldPlaceholder = computed(() =>
  isAzureProvider.value ? t('如: gpt-4o-mini-prod（Azure 部署名）') : t('如: gpt-4.1 / qwen-plus / deepseek-chat'),
);
const baseUrlPlaceholder = computed(() =>
  isAzureProvider.value ? 'https://YOUR-RESOURCE-NAME.openai.azure.com' : 'https://api.openai.com/v1',
);
const keyStateText = computed(() => {
  if (form.value.apiKey.trim()) {
    return t('已填写新 Key');
  }
  if (form.value.apiKeyMasked) {
    return form.value.apiKeyMasked;
  }
  return t('未配置');
});

const metricCards = computed(() => {
  const enabled = instances.value.filter((item) => item.status === 'active').length;
  const chatModels = instances.value.filter((item) => item.status === 'active' && item.capabilities.includes('chat')).length;
  const configuredProviders = new Set(instances.value.map((item) => item.providerId)).size;
  return [
    { key: 'total', icon: '<svg viewBox="0 0 24 24"><rect x="4" y="4" width="16" height="16" rx="2" /><rect x="9" y="9" width="6" height="6" /><line x1="9" y1="1" x2="9" y2="4" /><line x1="15" y1="1" x2="15" y2="4" /><line x1="9" y1="20" x2="9" y2="23" /><line x1="15" y1="20" x2="15" y2="23" /><line x1="20" y1="9" x2="23" y2="9" /><line x1="20" y1="15" x2="23" y2="15" /><line x1="1" y1="9" x2="4" y2="9" /><line x1="1" y1="15" x2="4" y2="15" /></svg>', label: t('模型配置'), value: instances.value.length, note: t('当前主账号下的模型实例') },
    { key: 'active', icon: '<svg viewBox="0 0 24 24"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2" /></svg>', label: t('已启用'), value: enabled, note: t('可被后续 runtime 路由选用') },
    { key: 'chat', icon: '<svg viewBox="0 0 24 24"><path d="M21 15a4 4 0 0 1-4 4H8l-5 3V7a4 4 0 0 1 4-4h10a4 4 0 0 1 4 4z" /><path d="M8 9h8M8 13h5" /></svg>', label: t('对话模型'), value: chatModels, note: t('仅使用企业已配置的模型') },
    { key: 'providers', icon: '<svg viewBox="0 0 24 24"><rect width="20" height="8" x="2" y="2" rx="2" ry="2" /><rect width="20" height="8" x="2" y="14" rx="2" ry="2" /><line x1="6" x2="6.01" y1="6" y2="6" /><line x1="6" x2="6.01" y1="18" y2="18" /></svg>', label: t('供应商'), value: configuredProviders, note: t('OpenAI / Azure OpenAI / Qwen / DeepSeek 等') },
  ];
});

const filteredInstances = computed(() => {
  const keyword = filters.value.keyword.trim().toLowerCase();
  return instances.value.filter((row) => {
    const hitKeyword =
      !keyword ||
      [row.displayName, row.modelName, row.baseUrl, row.providerName].some((field) =>
        field.toLowerCase().includes(keyword),
      );
    const hitProvider = !filters.value.providerId || row.providerId === filters.value.providerId;
    const hitStatus = !filters.value.status || row.status === filters.value.status;
    return hitKeyword && hitProvider && hitStatus;
  });
});

function capabilityLabel(value: string) {
  return capabilityOptions.value.find((item) => item.value === value)?.label.split(' ')[0] || value;
}

function providerInitial(name: string) {
  return (name || 'M').slice(0, 1).toUpperCase();
}

function resetTestState(text = t('保存模型配置后可测试。')) {
  testResultText.value = text;
  testResultType.value = 'idle';
}

function defaultProviderDisplayName(provider: ModelProviderItem) {
  return `${provider.name} ${t('模型')}`;
}

function isAutoProviderDisplayName(value: string, previousProvider?: ModelProviderItem) {
  const normalized = value.trim();
  if (!normalized) {
    return true;
  }
  if (previousProvider && normalized === defaultProviderDisplayName(previousProvider)) {
    return true;
  }
  return providers.value.some((provider) => normalized === defaultProviderDisplayName(provider));
}

function handleProviderChange(providerId: string, previousProviderId?: string) {
  const provider = providerMap.value.get(providerId);
  if (!provider) {
    return;
  }
  const previousProvider = previousProviderId ? providerMap.value.get(previousProviderId) : undefined;
  const baseUrl = form.value.baseUrl.trim();
  const shouldUseProviderBaseUrl = !baseUrl || Boolean(previousProvider?.defaultBaseUrl && baseUrl === previousProvider.defaultBaseUrl);
  if (shouldUseProviderBaseUrl) {
    form.value.baseUrl = provider.defaultBaseUrl;
  }
  if (provider.providerType === 'azure_openai' && !form.value.apiVersion) {
    form.value.apiVersion = '2024-10-21';
  }
  if (isAutoProviderDisplayName(form.value.displayName, previousProvider)) {
    form.value.displayName = defaultProviderDisplayName(provider);
  }
}

function suppressNextProviderChangeTick() {
  suppressProviderChange.value = true;
  void nextTick(() => {
    suppressProviderChange.value = false;
  });
}

function openCreate() {
  editorMode.value = 'create';
  suppressNextProviderChangeTick();
  form.value = defaultForm();
  const firstProvider = providers.value.find((item) => item.status === 'active');
  if (firstProvider) {
    form.value.providerId = firstProvider.id;
    form.value.baseUrl = firstProvider.defaultBaseUrl;
    form.value.displayName = defaultProviderDisplayName(firstProvider);
  }
  resetTestState(t('新增配置保存后可测试。'));
  editorVisible.value = true;
}

function openEdit(row: ModelInstanceItem) {
  editorMode.value = 'edit';
  suppressNextProviderChangeTick();
  form.value = {
    id: row.id,
    providerId: row.providerId,
    orgId: row.orgId,
    displayName: row.displayName,
    modelName: row.modelName,
    baseUrl: row.baseUrl,
    apiVersion: row.apiVersion || '',
    apiKey: '',
    apiKeyMasked: row.apiKeyMasked,
    capabilities: [...row.capabilities],
    status: row.status,
    isDefault: false,
  };
  resetTestState(t('可在右侧测试当前已保存的配置。'));
  editorVisible.value = true;
}

async function saveModel() {
  if (!form.value.providerId || !form.value.displayName.trim() || !form.value.modelName.trim()) {
    message.warning(t('请补齐供应商、显示名称和模型 ID'));
    return;
  }
  if (editorMode.value === 'create' && !form.value.apiKey.trim()) {
    message.warning(t('新增模型需要填写 API Key'));
    return;
  }
  if (isAzureProvider.value && !form.value.apiVersion.trim()) {
    message.warning(t('Azure OpenAI 需要填写 API Version'));
    return;
  }
  saving.value = true;
  try {
    const isCreatingFirstModel = editorMode.value === 'create' && instances.value.length === 0;
    const payload: ModelInstancePayload = {
      providerId: form.value.providerId,
      orgId: form.value.orgId,
      displayName: form.value.displayName.trim(),
      modelName: form.value.modelName.trim(),
      baseUrl: form.value.baseUrl.trim(),
      apiVersion: form.value.apiVersion.trim(),
      apiKey: form.value.apiKey.trim(),
      capabilities: form.value.capabilities.length ? form.value.capabilities : ['chat'],
      maxContextTokens: 0,
      status: form.value.status,
      isDefault: false,
    };
    const saved = editorMode.value === 'create'
      ? await createModelInstance(payload)
      : await updateModelInstance(form.value.id, payload);
    await reload();
    openEdit(saved);
    testResultText.value = t('模型配置已保存，可以继续测试。');
    testResultType.value = 'success';
    if (isCreatingFirstModel) {
      showFirstModelTrafficAllocationPrompt();
    } else {
      message.success(t('模型配置已保存'));
    }
  } catch (error) {
    message.error(readError(error, t('保存失败')));
  } finally {
    saving.value = false;
  }
}

function showFirstModelTrafficAllocationPrompt() {
  dialog.success({
    title: t('模型已添加'),
    content: t('已添加第一个模型。为了让用户正常使用模型，请前往流量分配页面设置企业总额度和成员额度。'),
    positiveText: t('前往分配流量'),
    negativeText: t('稍后处理'),
    onPositiveClick: () => {
      void router.push('/organizations/traffic?open=quota');
    },
  });
}

async function runTest(row: ModelInstanceItem) {
  openEdit(row);
  window.setTimeout(() => {
    void runEditorTest();
  }, 100);
}

async function runEditorTest() {
  if (!form.value.id) {
    return;
  }
  testing.value = true;
  testResultText.value = '';
  testResultType.value = 'idle';
  try {
    await streamModelInstanceTest(form.value.id, testPrompt.value, (event) => {
      if (event.type === 'start') {
        testResultText.value = event.message || t('正在连接模型...');
        return;
      }
      if (event.type === 'delta') {
        if (testResultText.value === t('正在连接模型...')) {
          testResultText.value = '';
        }
        testResultText.value += event.content || '';
        return;
      }
      if (event.type === 'error') {
        testResultText.value = event.message || t('测试失败');
        testResultType.value = 'failed';
        return;
      }
      if (event.type === 'done') {
        if (!testResultText.value) {
          testResultText.value = event.message || t('模型连接测试成功。');
        }
        testResultType.value = 'success';
      }
    });
    if (testResultType.value === 'idle') {
      testResultType.value = 'success';
    }
    await reload();
  } catch (error) {
    testResultText.value = readError(error, t('测试失败'));
    testResultType.value = 'failed';
  } finally {
    testing.value = false;
  }
}

function confirmDelete(row: ModelInstanceItem) {
  if (!window.confirm(t('确认删除「{name}」？删除后后续路由将不能再使用该模型配置。', { name: row.displayName }))) {
    return;
  }
  deleteModelInstance(row.id)
    .then(async () => {
      await reload();
    })
    .catch((error) => {
      window.alert(readError(error, t('删除失败')));
    });
}

function confirmDeleteFromEditor() {
  const row = instances.value.find((item) => item.id === form.value.id);
  if (!row) {
    return;
  }
  if (!window.confirm(t('确认删除「{name}」？删除后后续路由将不能再使用该模型配置。', { name: row.displayName }))) {
    return;
  }
  deleteModelInstance(row.id)
    .then(async () => {
      editorVisible.value = false;
      await reload();
    })
    .catch((error) => {
      window.alert(readError(error, t('删除失败')));
    });
}

async function reload() {
  loading.value = true;
  try {
    const [providerRows, instanceRows, allocationOverview] = await Promise.all([
      fetchModelProviders(),
      fetchModelInstances(),
      fetchTrafficAllocationOverview().catch(() => null),
    ]);
    providers.value = providerRows;
    instances.value = instanceRows;
    if (allocationOverview) {
      orgQuota.value = allocationOverview.orgPolicy.totalTokens;
    }
  } catch (error) {
    window.alert(readError(error, t('模型配置加载失败')));
  } finally {
    loading.value = false;
  }
}


function readError(error: unknown, fallback: string) {
  if (axios.isAxiosError(error)) {
    return String(error.response?.data?.detail || error.message || fallback);
  }
  return fallback;
}

watch(
  () => form.value.providerId,
  (providerId, previousProviderId) => {
    if (suppressProviderChange.value || !providerId || providerId === previousProviderId) {
      return;
    }
    handleProviderChange(providerId, previousProviderId);
  },
);

onMounted(reload);
</script>

<style scoped>
.model-page {
  height: calc(100vh - 92px);
  min-height: 0;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.shell-card {
  border-radius: 14px;
  border: 1px solid #e6ebf5;
  background: #fff;
  box-shadow: 0 6px 20px rgba(16, 38, 84, 0.05);
}

.metrics-row {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
  padding: 12px;
}

.metric-card,
.list-card {
  border-radius: 8px;
}

.list-card {
  width: calc(100% - 24px);
  margin: -16px 12px 0;
  flex: 1;
  min-height: 0;
  overflow: hidden;
}

.list-card :deep(.n-card__content) {
  height: 100%;
  display: flex;
  flex-direction: column;
}

.metric-card {
  border: 1px solid #e6ebf5;
  background: #fff;
  box-shadow: 0 4px 12px rgba(29, 54, 110, 0.04);
}

.metric-main {
  display: flex;
  align-items: flex-start;
  gap: 12px;
}

.metric-body {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.metric-icon {
  width: 44px;
  height: 44px;
  border-radius: 50%;
  display: grid;
  place-items: center;
  font-size: 13px;
  font-weight: 700;
}

.metric-icon :deep(svg) {
  width: 20px;
  height: 20px;
  fill: none;
  stroke: currentColor;
  stroke-width: 2;
  stroke-linecap: round;
  stroke-linejoin: round;
}

.metric-icon-total {
  color: #2d63ff;
  background: #eaf0ff;
}

.metric-icon-active {
  color: #0f9964;
  background: #e8f8ef;
}

.metric-icon-default {
  color: #d9860a;
  background: #fff2df;
}

.metric-icon-providers {
  color: #7456e0;
  background: #f0ebff;
}

.metric-label {
  color: #606f8a;
  font-size: 12px;
  line-height: 1.3;
}

.metric-value {
  color: #0f1f45;
  font-size: 24px;
  font-weight: 600;
  line-height: 1.1;
}

.metric-note {
  margin-top: 6px;
  color: #708099;
  font-size: 12px;
}

.filter-toolbar {
  align-items: center;
  display: flex;
  justify-content: space-between;
  gap: 14px;
}

.filter-left {
  flex-wrap: wrap;
}

.keyword-input {
  width: 360px;
}

.filter-right {
  flex-wrap: wrap;
}

.filter-right :deep(svg) {
  width: 15px;
  height: 15px;
  fill: none;
  stroke: currentColor;
  stroke-width: 2;
  stroke-linecap: round;
  stroke-linejoin: round;
}

.list-filter-row {
  padding: 0 44px 12px;
  margin: 0 -44px 12px;
  border-bottom: 1px solid #edf1f7;
}

.list-body {
  flex: 1;
  min-height: 0;
  overflow: auto;
}

.model-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 14px;
}

.model-config-card {
  min-height: 220px;
  padding: 16px;
  border: 1px solid rgba(28, 45, 82, 0.1);
  border-radius: 8px;
  background: #fff;
  color: inherit;
  text-align: left;
  cursor: pointer;
  display: flex;
  flex-direction: column;
  gap: 10px;
  transition:
    border-color 0.2s ease,
    box-shadow 0.2s ease,
    background-color 0.2s ease;
}

.model-config-card:hover {
  border-color: rgba(54, 106, 255, 0.36);
  box-shadow: 0 10px 28px rgba(33, 58, 126, 0.1);
}

.card-head,
.card-actions,
.card-bottom {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}

.state-tags {
  justify-content: flex-end;
}

.provider-badge {
  color: #366aff;
  font-size: 12px;
  font-weight: 700;
}

.card-body {
  min-height: 52px;
}

.card-title {
  color: #17233d;
  font-size: 16px;
  font-weight: 800;
}

.card-model-id {
  margin-top: 3px;
  color: #687789;
  font-family: "SFMono-Regular", Consolas, "Liberation Mono", monospace;
  font-size: 12px;
}

.capability-row {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  min-height: 24px;
  margin-top: 2px;
}

.capability-tag {
  background: #f1f5f9;
}

.card-footnote {
  margin-top: auto;
  color: #7a8797;
  font-size: 12px;
}

.test-summary div {
  display: grid;
  gap: 2px;
}

.test-summary span {
  color: #7a8797;
  font-size: 12px;
}

.test-summary strong {
  min-width: 0;
  overflow: hidden;
  color: #23324f;
  font-size: 12px;
  font-weight: 650;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.card-bottom {
  margin-top: 2px;
}

.card-actions {
  justify-content: flex-start;
}

.add-model-card {
  display: grid;
  min-height: 246px;
  place-content: center;
  justify-items: center;
  border-style: dashed;
  background: rgba(247, 250, 255, 0.8);
  text-align: center;
}

.add-symbol {
  display: grid;
  width: 38px;
  height: 38px;
  place-items: center;
  border-radius: 8px;
  background: #366aff;
  color: #fff;
  font-size: 26px;
  line-height: 1;
}

.add-title {
  margin-top: 12px;
  color: #17233d;
  font-weight: 800;
}

.add-copy {
  max-width: 230px;
  margin-top: 6px;
  color: #687789;
  font-size: 12px;
  line-height: 1.5;
}

.editor-layout {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 280px;
  gap: 18px;
}

.editor-layout.single-column {
  grid-template-columns: minmax(0, 1fr);
}

.test-panel {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 14px;
  border: 1px solid rgba(28, 45, 82, 0.1);
  border-radius: 8px;
  background: #f8fbff;
}

.test-title {
  color: #17233d;
  font-size: 15px;
  font-weight: 800;
}

.test-summary {
  display: grid;
  gap: 10px;
}

.test-result {
  min-height: 54px;
  padding: 10px;
  border-radius: 8px;
  background: #fff;
  color: #687789;
  font-size: 12px;
  line-height: 1.5;
}

.test-result.success {
  color: #147447;
  background: #ecfdf5;
}

.test-result.failed {
  color: #b42318;
  background: #fff1f2;
}

.form-hint {
  margin-left: 96px;
  color: #687789;
  font-size: 12px;
}
</style>
