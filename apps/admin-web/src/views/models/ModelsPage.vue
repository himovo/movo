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
        :title="t('legacy.enterprise_quota_alert')"
        style="margin-bottom: 16px;"
      >
        {{ t('legacy.current_enterprise_total_tokens_limit_is_0_all_models') }}
        <router-link to="/organizations/traffic?open=quota" class="alert-link">
          {{ t('legacy.traffic_allocation') }}
        </router-link>
        {{ t('legacy.to_configure_enterprise_and_member_quotas') }}
      </n-alert>

      <div class="list-filter-row">

        <div class="filter-toolbar">
          <n-space align="center" :size="10" class="filter-left">
            <n-input v-model:value="filters.keyword" :placeholder="t('legacy.search_by_name_model_id_base_url')" clearable class="keyword-input" />
            <n-select
              v-model:value="filters.providerId"
              :options="providerOptions"
              :placeholder="t('legacy.provider_703c9eb')"
              clearable
              style="width: 160px"
            />
            <n-select
              v-model:value="filters.status"
              :options="statusOptions"
              :placeholder="t('legacy.status')"
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
              {{ t('legacy.refresh') }}
            </n-button>
            <n-button secondary @click="openGroupCreate">{{ t('modelGroup.create') }}</n-button>
            <n-button type="primary" strong @click="openCreate()">
              <template #icon>
                <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                  <path d="M5 12h14" />
                  <path d="M12 5v14" />
                </svg>
              </template>
              {{ t('legacy.new_model') }}
            </n-button>
          </n-space>
        </div>
      </div>

      <div class="list-body">
        <n-spin :show="loading">
          <div v-if="filteredInstances.length || filteredGroups.length" class="model-grid">
            <ModelGroupCard
              v-for="group in filteredGroups"
              :key="group.id"
              :group="group"
              :models="instances.filter((item) => item.groupId === group.id)"
              :providers="providers"
              @edit="openGroupEdit(group)"
              @add="openGroupEdit(group)"
              @edit-model="openGroupModelEdit"
            />
            <button
              v-for="model in filteredStandaloneInstances"
              :key="model.id"
              class="model-config-card"
              type="button"
              @click="openEdit(model)"
            >
              <div class="card-head">
                <span class="provider-badge">{{ providerLabel({ code: model.providerCode, name: model.providerName, providerType: model.providerType }) }}</span>
                <n-space :size="6" class="state-tags">
                  <n-tag :type="model.status === 'active' ? 'success' : 'default'" size="small" :bordered="false">
                    {{ model.status === 'active' ? t('legacy.active') : t('legacy.disabled_be70be5') }}
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
                {{ t('legacy.last_updated') }}{{ formatAdminDateTime(model.updatedAt, t('legacy.unknown')) }}
              </div>

              <div class="card-bottom">
                <div class="card-actions">
                  <n-button size="small" tertiary @click.stop="runTest(model)">{{ t('legacy.test') }}</n-button>
                  <n-button size="small" tertiary type="error" @click.stop="confirmDelete(model)">{{ t('legacy.delete') }}</n-button>
                </div>
              </div>
            </button>

            <button class="model-config-card add-model-card" type="button" @click="openCreate()">
              <div class="add-symbol">+</div>
              <div class="add-title">{{ t('legacy.new_model') }}</div>
              <div class="add-copy">{{ t('legacy.configure_openai_azure_openai_qwen_deepseek_or_custom_compatible') }}</div>
            </button>
          </div>

          <n-empty v-else :description="t('legacy.no_model_configurations')">
            <template #extra>
              <n-button type="primary" @click="openCreate()">{{ t('legacy.add_first_model') }}</n-button>
            </template>
          </n-empty>
        </n-spin>
      </div>
    </n-card>
    <ModelGroupEditor
      v-model:show="groupEditorVisible"
      :group="editingGroup"
      :providers="providers"
      :models="instances"
      :selected-model-id="selectedGroupModelId"
      @saved="onGroupSaved"
      @deleted="reload"
      @member-changed="reload"
    />
  </div>

  <n-modal v-model:show="editorVisible" preset="card" :title="editorTitle" style="width: 980px">
    <div class="editor-layout" :class="{ 'single-column': editorMode === 'create' }">
      <n-form class="editor-form" :model="form" label-placement="left" label-width="96">
        <n-grid :cols="2" :x-gap="14">
          <n-grid-item v-if="!form.groupId">
            <n-form-item :label="t('legacy.provider_703c9eb')">
              <n-select
                v-model:value="form.providerId"
                :options="providerOptions"
                :placeholder="t('legacy.select_provider')"
              />
            </n-form-item>
          </n-grid-item>
          <n-grid-item>
            <n-form-item :label="t('legacy.display_name')">
              <n-input v-model:value="form.displayName" :placeholder="t('legacy.example_openai_main_model')" />
            </n-form-item>
          </n-grid-item>
          <n-grid-item>
            <n-form-item :label="modelFieldLabel">
              <n-input v-model:value="form.modelName" :placeholder="modelFieldPlaceholder" />
            </n-form-item>
          </n-grid-item>
          <n-grid-item>
            <n-form-item :label="t('legacy.status')">
              <n-select v-model:value="form.status" :options="statusOptions" />
            </n-form-item>
          </n-grid-item>
          <n-grid-item v-if="!form.groupId" :span="2">
            <n-form-item label="Base URL">
              <n-input v-model:value="form.baseUrl" :placeholder="baseUrlPlaceholder" />
            </n-form-item>
          </n-grid-item>
          <n-grid-item v-if="isAzureProvider && !form.groupId">
            <n-form-item label="API Version">
              <n-input v-model:value="form.apiVersion" placeholder="如: 2024-10-21" />
            </n-form-item>
          </n-grid-item>
          <n-grid-item v-if="!form.groupId">
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
            <n-form-item :label="t('legacy.capabilities')">
              <n-select v-model:value="form.capabilities" multiple :options="capabilityOptions" />
            </n-form-item>
          </n-grid-item>
          <n-grid-item v-if="form.groupId" :span="2">
            <n-alert type="info" :bordered="false">{{ t('modelGroup.sharedConnection', { name: groups.find((item) => item.id === form.groupId)?.name || '' }) }}</n-alert>
          </n-grid-item>
          <n-grid-item :span="2"><ModelPricingFields v-model="form.pricing" /></n-grid-item>
          <n-grid-item v-if="hasImageCapability" :span="2">
            <ImageModelRuntimeFields
              v-model:runtimeKind="form.runtimeKind"
              v-model:imageSettings="form.imageSettings"
              :provider-type="currentProvider?.providerType || ''"
            />
          </n-grid-item>
        </n-grid>
        <ModelAccessExtensionPanel
          v-if="modelAccess.enabled && isUserSelectableModel"
          v-model="modelAccessValue"
          :loading="modelAccessLoading"
          :grouped="Boolean(form.groupId)"
          class="model-access-panel"
        />
      </n-form>

      <aside v-if="editorMode === 'edit'" class="test-panel">
        <div class="test-title">{{ t('legacy.configuration_test') }}</div>
        <div class="test-summary">
          <div>
            <span>{{ t('legacy.provider_703c9eb') }}</span>
            <strong>{{ providerLabel(currentProvider) }}</strong>
          </div>
          <div>
            <span>{{ t('legacy.model_id') }}</span>
            <strong>{{ form.modelName || t('legacy.not_filled') }}</strong>
          </div>
          <div>
            <span>Base URL</span>
            <strong>{{ form.baseUrl || currentProvider?.defaultBaseUrl || t('legacy.not_set') }}</strong>
          </div>
          <div v-if="isAzureProvider">
            <span>API Version</span>
            <strong>{{ form.apiVersion || t('legacy.not_filled_default_2024_10_21') }}</strong>
          </div>
          <div>
            <span>{{ t('legacy.key_status') }}</span>
            <strong>{{ keyStateText }}</strong>
          </div>
        </div>

        <n-input
          v-if="modelTestKind === 'chat' || modelTestKind === 'image'"
          v-model:value="testPrompt"
          type="textarea"
          :rows="4"
          :placeholder="t('legacy.test_prompt_used_to_trigger_a_light_call')"
        />
        <n-alert v-else type="info" :bordered="false">
          {{ modelTestKind === 'embedding' ? t('legacy.the_embedding_endpoint_will_be_called_and_its_vector') : t('legacy.the_rerank_endpoint_will_be_called_and_its_ranking') }}
        </n-alert>
        <n-button block type="primary" secondary :loading="testing" :disabled="!form.id" @click="runEditorTest">
          {{ t('legacy.test_configuration') }}
        </n-button>
        <div class="test-result" :class="{ success: testResultType === 'success', failed: testResultType === 'failed' }">
          {{ testResultText }}
        </div>
        <img
          v-if="testImageUrl"
          class="test-image-preview"
          :src="testImageUrl"
          :alt="t('additional.image_model_test_result')"
        />
      </aside>
    </div>

    <template #footer>
      <n-space justify="space-between" align="center">
        <n-button v-if="editorMode === 'edit'" tertiary type="error" @click="confirmDeleteFromEditor">{{ t('legacy.delete_model') }}</n-button>
        <span v-else />
        <n-space>
          <n-button @click="editorVisible = false">{{ t('legacy.cancel') }}</n-button>
          <n-button type="primary" :loading="saving" @click="saveModel">{{ t('legacy.save') }}</n-button>
        </n-space>
      </n-space>
    </template>
  </n-modal>
</template>

<script setup lang="ts">
import { computed, nextTick, onMounted, ref, watch } from 'vue';
import { useRouter } from 'vue-router';
import axios from 'axios';
import { NAlert, useDialog, useMessage } from 'naive-ui';
import PageIntro from '@/components/PageIntro.vue';
import { t } from '@/composables/i18n';
import { formatAdminDateTime } from '@/composables/adminTimezone';
import ImageModelRuntimeFields from '@/components/models/ImageModelRuntimeFields.vue';
import ModelPricingFields from '@/components/models/ModelPricingFields.vue';
import ModelGroupCard from '@/components/models/ModelGroupCard.vue';
import ModelGroupEditor from '@/components/models/ModelGroupEditor.vue';
import {
  createModelInstance,
  fetchModelGroups,
  deleteModelInstance,
  fetchModelInstances,
  fetchModelProviders,
  streamModelInstanceTest,
  testImageModelInstance,
  testKnowledgeModelInstance,
  updateModelInstance,
  type ModelInstanceItem,
  type ModelGroupItem,
  type ModelInstancePayload,
  type ModelProviderItem,
  type ModelStatus,
  type ImageModelSettings,
  type ImageRuntimeKind,
  type ModelPricing,
} from '@/api/models';
import { fetchTrafficAllocationOverview } from '@/api/traffic-allocations';
import { capabilityLabel } from '@/components/models/capabilityLabels';
import { providerLabel } from '@/components/models/providerLabels';
import { resolveModelTestKind } from '@/components/models/modelTestKind';
import ModelAccessExtensionPanel from '@/components/models/ModelAccessExtensionPanel.vue';
import { useModelAccessExtension } from '@/composables/useModelAccessExtension';
import { useVisionCapabilitySuggestion } from '@/composables/useVisionCapabilitySuggestion';


interface ModelForm extends ModelInstancePayload {
  id: string;
  apiKeyMasked: string;
  runtimeKind: ImageRuntimeKind | '';
  imageSettings: ImageModelSettings;
  pricing: ModelPricing | null;
}

const loading = ref(false);
const saving = ref(false);
const testing = ref(false);
const message = useMessage();
const dialog = useDialog();
const visionSuggestion = useVisionCapabilitySuggestion();
const router = useRouter();
const providers = ref<ModelProviderItem[]>([]);
const instances = ref<ModelInstanceItem[]>([]);
const groups = ref<ModelGroupItem[]>([]);
const groupEditorVisible = ref(false);
const editingGroup = ref<ModelGroupItem | null>(null);
const selectedGroupModelId = ref('');
const editorVisible = ref(false);
const editorMode = ref<'create' | 'edit'>('create');
const suppressProviderChange = ref(false);
const testPrompt = ref(t('legacy.reply_in_one_sentence_to_test_the_current_model'));
const testResultText = ref(t('legacy.save_the_model_configuration_before_testing'));
const testResultType = ref<'idle' | 'success' | 'failed'>('idle');
const testImageUrl = ref('');
const modelAccess = useModelAccessExtension();
const modelAccessValue = modelAccess.value;
const modelAccessLoading = modelAccess.loading;

const filters = ref({
  keyword: '',
  providerId: null as string | null,
  status: null as ModelStatus | null,
});

const defaultForm = (): ModelForm => ({
  id: '',
  groupId: '',
  providerId: '',
  orgId: '',
  displayName: '',
  modelName: '',
  baseUrl: '',
  apiVersion: '',
  apiKey: '',
  apiKeyMasked: '',
  capabilities: ['chat'],
  runtimeKind: '',
  imageSettings: {},
  pricing: null,
  status: 'active',
  isDefault: false,
});

const form = ref<ModelForm>(defaultForm());
const orgQuota = ref<number | null>(null);


const statusOptions = computed(() => [
  { label: t('legacy.active'), value: 'active' },
  { label: t('legacy.disabled_be70be5'), value: 'disabled' },
]);

const capabilityOptions = computed(() => [
  { label: capabilityLabel('chat'), value: 'chat' },
  { label: capabilityLabel('vision'), value: 'vision' },
  { label: capabilityLabel('embedding'), value: 'embedding' },
  { label: capabilityLabel('rerank'), value: 'rerank' },
  { label: capabilityLabel('image_generation'), value: 'image_generation' },
]);

const providerOptions = computed(() =>
  providers.value
    .filter((item) => item.status === 'active')
    .map((item) => ({
      label: providerLabel(item),
      value: item.id,
    })),
);

const providerMap = computed(() => new Map(providers.value.map((item) => [item.id, item])));
const currentProvider = computed(() => providerMap.value.get(form.value.providerId));
const isAzureProvider = computed(() => currentProvider.value?.providerType === 'azure_openai');
const hasImageCapability = computed(() => form.value.capabilities.includes('image_generation'));
const modelTestKind = computed(() => resolveModelTestKind(form.value.capabilities));
const isUserSelectableModel = computed(() => form.value.capabilities.some((item) => ['chat', 'text', 'image_generation'].includes(item)));
const editorTitle = computed(() => (editorMode.value === 'create' ? t('legacy.add_model') : t('legacy.model_configuration_details')));
const apiKeyPlaceholder = computed(() =>
  editorMode.value === 'create' ? t('legacy.please_enter_api_key') : t('legacy.leave_blank_to_retain_current_key'),
);
const modelFieldLabel = computed(() => (isAzureProvider.value ? t('legacy.deployment_name') : t('legacy.model_id')));
const modelFieldPlaceholder = computed(() =>
  hasImageCapability.value
    ? (isAzureProvider.value ? t('additional.e_g_gpt_image_2_prod_azure_deployment_name') : t('additional.e_g_qwen_image_plus_gpt_image_1'))
    : (isAzureProvider.value ? t('legacy.example_gpt_4o_mini_prod_azure_deploy_name') : t('legacy.example_gpt_4_1_qwen_plus_deepseek_chat_8435735')),
);
const baseUrlPlaceholder = computed(() =>
  isAzureProvider.value ? 'https://YOUR-RESOURCE-NAME.openai.azure.com' : 'https://api.openai.com/v1',
);
const keyStateText = computed(() => {
  if (form.value.apiKey.trim()) {
    return t('legacy.new_key_entered');
  }
  if (form.value.apiKeyMasked) {
    return form.value.apiKeyMasked;
  }
  return t('legacy.not_configured');
});

const metricCards = computed(() => {
  const enabled = instances.value.filter((item) => item.status === 'active').length;
  const chatModels = instances.value.filter((item) => item.status === 'active' && item.capabilities.includes('chat')).length;
  const configuredProviders = new Set(instances.value.map((item) => item.providerId)).size;
  return [
    { key: 'total', icon: '<svg viewBox="0 0 24 24"><rect x="4" y="4" width="16" height="16" rx="2" /><rect x="9" y="9" width="6" height="6" /><line x1="9" y1="1" x2="9" y2="4" /><line x1="15" y1="1" x2="15" y2="4" /><line x1="9" y1="20" x2="9" y2="23" /><line x1="15" y1="20" x2="15" y2="23" /><line x1="20" y1="9" x2="23" y2="9" /><line x1="20" y1="15" x2="23" y2="15" /><line x1="1" y1="9" x2="4" y2="9" /><line x1="1" y1="15" x2="4" y2="15" /></svg>', label: t('legacy.models_configured'), value: instances.value.length, note: t('legacy.model_instances_under_current_master_account') },
    { key: 'active', icon: '<svg viewBox="0 0 24 24"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2" /></svg>', label: t('legacy.active_25d2843'), value: enabled, note: t('legacy.can_be_routed_by_runtime') },
    { key: 'chat', icon: '<svg viewBox="0 0 24 24"><path d="M21 15a4 4 0 0 1-4 4H8l-5 3V7a4 4 0 0 1 4-4h10a4 4 0 0 1 4 4z" /><path d="M8 9h8M8 13h5" /></svg>', label: t('legacy.chat_model'), value: chatModels, note: t('legacy.only_organization_configured_models_are_used') },
    { key: 'providers', icon: '<svg viewBox="0 0 24 24"><rect width="20" height="8" x="2" y="2" rx="2" ry="2" /><rect width="20" height="8" x="2" y="14" rx="2" ry="2" /><line x1="6" x2="6.01" y1="6" y2="6" /><line x1="6" x2="6.01" y1="18" y2="18" /></svg>', label: t('legacy.provider_703c9eb'), value: configuredProviders, note: t('legacy.openai_azure_qwen_deepseek_etc') },
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
const filteredStandaloneInstances = computed(() => filteredInstances.value.filter((item) => !item.groupId));
const filteredGroups = computed(() => {
  const keyword = filters.value.keyword.trim().toLowerCase();
  return groups.value.filter((group) => {
    const children = filteredInstances.value.filter((item) => item.groupId === group.id);
    const groupMatches = (!keyword || [group.name, group.baseUrl].some((value) => value.toLowerCase().includes(keyword)))
      && (!filters.value.providerId || group.providerId === filters.value.providerId)
      && (!filters.value.status || group.status === filters.value.status);
    return groupMatches || children.length > 0;
  });
});

function openGroupCreate() { selectedGroupModelId.value = ''; editingGroup.value = null; groupEditorVisible.value = true; }
function openGroupEdit(group: ModelGroupItem) { selectedGroupModelId.value = ''; editingGroup.value = group; groupEditorVisible.value = true; }
function openGroupModelEdit(model: ModelInstanceItem) {
  const group = groups.value.find((item) => item.id === model.groupId);
  if (!group) return;
  selectedGroupModelId.value = model.id;
  editingGroup.value = group;
  groupEditorVisible.value = true;
}
async function onGroupSaved(group: ModelGroupItem) {
  editingGroup.value = group;
  await reload();
}

function providerInitial(name: string) {
  return (name || 'M').slice(0, 1).toUpperCase();
}

function resetTestState(text = t('legacy.available_to_test_after_saving_configuration')) {
  testResultText.value = text;
  testResultType.value = 'idle';
  testImageUrl.value = '';
}

function recommendedImageRuntime(provider?: ModelProviderItem): ImageRuntimeKind {
  if (provider?.providerType === 'azure_openai') return 'azure_openai_images';
  return 'openai_images';
}

function defaultProviderDisplayName(provider: ModelProviderItem) {
  return `${provider.name} ${t('legacy.model')}`;
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
  if (hasImageCapability.value) {
    form.value.runtimeKind = recommendedImageRuntime(provider);
    form.value.imageSettings = {};
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

function openCreate(group?: ModelGroupItem) {
  editorMode.value = 'create';
  suppressNextProviderChangeTick();
  form.value = defaultForm();
  const firstProvider = group ? providerMap.value.get(group.providerId) : providers.value.find((item) => item.status === 'active');
  if (firstProvider) {
    form.value.groupId = group?.id || '';
    form.value.providerId = firstProvider.id;
    form.value.baseUrl = group?.baseUrl || firstProvider.defaultBaseUrl;
    form.value.apiVersion = group?.apiVersion || '';
    form.value.displayName = group ? '' : defaultProviderDisplayName(firstProvider);
  }
  resetTestState(t('legacy.available_to_test_after_saving_new_configuration'));
  modelAccess.reset(Boolean(group));
  editorVisible.value = true;
}

function openEdit(row: ModelInstanceItem) {
  editorMode.value = 'edit';
  suppressNextProviderChangeTick();
  form.value = {
    id: row.id,
    groupId: row.groupId || '',
    providerId: row.providerId,
    orgId: row.orgId,
    displayName: row.displayName,
    modelName: row.modelName,
    baseUrl: row.baseUrl,
    apiVersion: row.apiVersion || '',
    apiKey: '',
    apiKeyMasked: row.apiKeyMasked,
    capabilities: [...row.capabilities],
    runtimeKind: row.runtimeKind || recommendedImageRuntime(providerMap.value.get(row.providerId)),
    imageSettings: { ...(row.imageSettings || {}) },
    pricing: row.pricing ? { ...row.pricing } : null,
    status: row.status,
    isDefault: false,
  };
  resetTestState(t('legacy.you_can_test_the_saved_configuration_on_the_right'));
  if (row.capabilities.some((item) => ['chat', 'text', 'image_generation'].includes(item))) {
    void modelAccess.load(row.id).catch((error) => {
      message.error(readError(error, t('additional.failed_to_load')));
    });
  }
  editorVisible.value = true;
}

async function saveModel() {
  const accessValidation = isUserSelectableModel.value ? modelAccess.validate() : null;
  if (accessValidation) {
    message.warning(t(accessValidation));
    return;
  }
  if (!form.value.providerId || (!form.value.groupId && !form.value.displayName.trim()) || !form.value.modelName.trim()) {
    message.warning(t('legacy.please_complete_provider_display_name_and_model_id'));
    return;
  }
  if (editorMode.value === 'create' && !form.value.groupId && !form.value.apiKey.trim()) {
    message.warning(t('legacy.api_key_is_required_for_new_models'));
    return;
  }
  if (isAzureProvider.value && !form.value.apiVersion.trim()) {
    message.warning(t('legacy.api_version_is_required_for_azure_openai'));
    return;
  }
  if (hasImageCapability.value && form.value.runtimeKind === 'custom_images') {
    try {
      const parsed = JSON.parse(String(form.value.imageSettings.extraParamsJson || '{}').trim() || '{}');
      if (!parsed || Array.isArray(parsed) || typeof parsed !== 'object') throw new Error();
    } catch {
      message.warning(t('legacy.enter_a_valid_json_object'));
      return;
    }
  }
  saving.value = true;
  try {
    const isCreatingFirstModel = editorMode.value === 'create' && instances.value.length === 0;
    const payload: ModelInstancePayload = {
      providerId: form.value.providerId,
      groupId: form.value.groupId,
      orgId: form.value.orgId,
      displayName: form.value.displayName.trim() || form.value.modelName.trim(),
      modelName: form.value.modelName.trim(),
      baseUrl: form.value.baseUrl.trim(),
      apiVersion: form.value.apiVersion.trim(),
      apiKey: form.value.apiKey.trim(),
      capabilities: form.value.capabilities.length ? form.value.capabilities : ['chat'],
      runtimeKind: hasImageCapability.value ? form.value.runtimeKind || recommendedImageRuntime(currentProvider.value) : '',
      imageSettings: hasImageCapability.value ? { ...form.value.imageSettings } : {},
      pricing: form.value.pricing,
      maxContextTokens: 0,
      status: form.value.status,
      isDefault: false,
    };
    const saved = editorMode.value === 'create'
      ? await createModelInstance(payload)
      : await updateModelInstance(form.value.id, payload);
    try {
      if (isUserSelectableModel.value) {
        await modelAccess.save(saved.id);
      }
    } catch (error) {
      editorMode.value = 'edit';
      form.value.id = saved.id;
      form.value.apiKey = '';
      form.value.apiKeyMasked = saved.apiKeyMasked;
      await reload();
      message.error(`${t('legacy.the_model_was_saved_but_its_access_policy_could')}：${readError(error, t('legacy.failed_to_save'))}`);
      return;
    }
    await reload();
    openEdit(saved);
    testResultText.value = t('legacy.configuration_saved_you_can_continue_testing');
    testResultType.value = 'success';
    if (isCreatingFirstModel) {
      showFirstModelTrafficAllocationPrompt();
    } else {
      message.success(t('additional.model_configuration_saved'));
    }
  } catch (error) {
    message.error(readError(error, t('legacy.failed_to_save')));
  } finally {
    saving.value = false;
  }
}

function showFirstModelTrafficAllocationPrompt() {
  dialog.success({
    title: t('legacy.model_added'),
    content: t('legacy.the_first_model_has_been_added_to_let_users'),
    positiveText: t('legacy.go_to_traffic_allocation'),
    negativeText: t('legacy.later'),
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
  testImageUrl.value = '';
  try {
    if (modelTestKind.value === 'image') {
      const result = await testImageModelInstance(form.value.id, testPrompt.value);
      testResultText.value = result.message || (result.success ? t('additional.image_generation_test_succeeded') : t('additional.image_generation_test_failed'));
      testResultType.value = result.success ? 'success' : 'failed';
      testImageUrl.value = result.imageUrl || '';
      await reload();
      return;
    }
    if (modelTestKind.value === 'embedding' || modelTestKind.value === 'rerank') {
      const result = await testKnowledgeModelInstance(form.value.id, modelTestKind.value);
      testResultText.value = result.message || (result.success ? t('legacy.model_connection_tested_successfully') : t('legacy.test_failed'));
      testResultType.value = result.success ? 'success' : 'failed';
      await reload();
      return;
    }
    await streamModelInstanceTest(form.value.id, testPrompt.value, (event) => {
      if (event.type === 'start') {
        testResultText.value = event.message || t('legacy.connecting_to_model');
        return;
      }
      if (event.type === 'delta') {
        if (testResultText.value === t('legacy.connecting_to_model')) {
          testResultText.value = '';
        }
        testResultText.value += event.content || '';
        return;
      }
      if (event.type === 'error') {
        testResultText.value = event.message || t('legacy.test_failed');
        testResultType.value = 'failed';
        return;
      }
      if (event.type === 'done') {
        if (!testResultText.value) {
          testResultText.value = event.message || t('legacy.model_connection_tested_successfully');
        }
        testResultType.value = 'success';
      }
    });
    if (testResultType.value === 'idle') {
      testResultType.value = 'success';
    }
    await reload();
    if (testResultType.value === 'success') {
      await visionSuggestion.check(instances.value.find((item) => item.id === form.value.id), async () => {
        form.value.capabilities = [...new Set([...form.value.capabilities, 'vision'])];
        await reload();
      });
    }
  } catch (error) {
    testResultText.value = readError(error, t('legacy.test_failed'));
    testResultType.value = 'failed';
  } finally {
    testing.value = false;
  }
}

function confirmDelete(row: ModelInstanceItem) {
  if (!window.confirm(t('legacy.are_you_sure_to_delete_routing_will_no_longer', { name: row.displayName }))) {
    return;
  }
  deleteModelInstance(row.id)
    .then(async () => {
      await reload();
    })
    .catch((error) => {
      window.alert(readError(error, t('legacy.failed_to_delete')));
    });
}

function confirmDeleteFromEditor() {
  const row = instances.value.find((item) => item.id === form.value.id);
  if (!row) {
    return;
  }
  if (!window.confirm(t('legacy.are_you_sure_to_delete_routing_will_no_longer', { name: row.displayName }))) {
    return;
  }
  deleteModelInstance(row.id)
    .then(async () => {
      editorVisible.value = false;
      await reload();
    })
    .catch((error) => {
      window.alert(readError(error, t('legacy.failed_to_delete')));
    });
}

async function reload() {
  loading.value = true;
  try {
    const [providerRows, instanceRows, groupRows, allocationOverview] = await Promise.all([
      fetchModelProviders(),
      fetchModelInstances(),
      fetchModelGroups(),
      fetchTrafficAllocationOverview().catch(() => null),
    ]);
    providers.value = providerRows;
    instances.value = instanceRows;
    groups.value = groupRows;
    if (allocationOverview) {
      orgQuota.value = allocationOverview.orgPolicy.totalTokens;
    }
  } catch (error) {
    window.alert(readError(error, t('legacy.failed_to_load_model_configurations')));
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

watch(
  () => hasImageCapability.value,
  (enabled) => {
    if (enabled) {
      form.value.runtimeKind = form.value.runtimeKind || recommendedImageRuntime(currentProvider.value);
      if (testPrompt.value === t('legacy.reply_in_one_sentence_to_test_the_current_model')) {
        testPrompt.value = t('legacy.generate_a_clean_futuristic_presentation_cover_image_without_text');
      }
    } else if (testPrompt.value === t('legacy.generate_a_clean_futuristic_presentation_cover_image_without_text')) {
      testPrompt.value = t('legacy.reply_in_one_sentence_to_test_the_current_model');
    }
    resetTestState(editorMode.value === 'edit' ? t('legacy.you_can_test_the_saved_configuration_on_the_right') : t('legacy.available_to_test_after_saving_configuration'));
  },
);

onMounted(reload);
</script>

<style scoped>
.alert-link {
  color: #2563eb;
  font-weight: 600;
  text-decoration: underline;
}
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

.test-image-preview {
  width: 100%;
  max-height: 260px;
  border: 1px solid #e6ebf5;
  border-radius: 8px;
  object-fit: contain;
  background: #f8fafc;
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

</style>
