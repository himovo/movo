<template>
  <n-form label-placement="top">
    <n-grid :cols="2" :x-gap="12">
      <n-grid-item :span="2">
        <n-form-item :label="t('legacy.model_provider_77d78db')">
          <n-select
            v-model:value="model.providerId"
            :options="providerOptions"
            :loading="providersLoading"
            :placeholder="t('legacy.select_a_model_provider_1fc35e6')"
          />
        </n-form-item>
      </n-grid-item>
      <n-grid-item>
        <n-form-item :label="t('legacy.configuration_name')">
          <n-input v-model:value="model.displayName" :placeholder="t('legacy.example_organization_chat_model')" />
        </n-form-item>
      </n-grid-item>
      <n-grid-item>
        <n-form-item :label="isAzure ? t('legacy.deployment_name') : t('legacy.model_id')">
          <n-input v-model:value="model.modelName" :placeholder="modelPlaceholder" />
        </n-form-item>
      </n-grid-item>
      <n-grid-item :span="isAzure ? 1 : 2">
        <n-form-item :label="isAzure ? 'Azure Endpoint' : 'Base URL'">
          <n-input v-model:value="model.baseUrl" :placeholder="baseUrlPlaceholder" />
        </n-form-item>
      </n-grid-item>
      <n-grid-item v-if="isAzure">
        <n-form-item label="API Version">
          <n-input v-model:value="model.apiVersion" placeholder="2024-10-21" />
        </n-form-item>
      </n-grid-item>
      <n-grid-item :span="2">
        <n-form-item label="API Key">
          <n-input v-model:value="model.apiKey" type="password" show-password-on="click" autocomplete="off" />
        </n-form-item>
      </n-grid-item>
    </n-grid>
  </n-form>
</template>

<script setup lang="ts">
import { computed, watch } from 'vue';
import { t } from '@/composables/i18n';
import type { SetupModelProvider } from '@/api/setup';
import { providerLabel } from '@/components/models/providerLabels';
import type { SetupModelForm } from './types';

const props = defineProps<{
  providers: SetupModelProvider[];
  providersLoading: boolean;
}>();
const model = defineModel<SetupModelForm>({ required: true });

const providerOptions = computed(() => props.providers.map((item) => ({ label: providerLabel(item), value: item.id })));
const selectedProvider = computed(() => props.providers.find((item) => item.id === model.value.providerId));
const isAzure = computed(() => selectedProvider.value?.providerType === 'azure_openai');
const modelPlaceholder = computed(() => {
  if (isAzure.value) return t('legacy.example_gpt_4o_mini_prod');
  if (model.value.capability === 'embedding') return t('additional.e_g_text_embedding_3_small_text_embedding_v3');
  if (model.value.capability === 'rerank') return t('additional.e_g_qwen3_rerank_bge_reranker_v2_m3');
  return t('legacy.example_gpt_4_1_qwen_plus_deepseek_chat');
});
const baseUrlPlaceholder = computed(() => model.value.capability === 'rerank'
  ? t('additional.enter_the_provider_base_url_for_a_custom_service')
  : 'https://api.openai.com/v1');
const capabilityName = computed(() => ({
  chat: t('legacy.chat_model'),
  embedding: t('legacy.embedding_model'),
  rerank: t('additional.rerank_model'),
  vision: t('legacy.vision_model'),
  image: t('legacy.image_generation_model_5ba964f'),
}[model.value.capability]));

watch(() => model.value.providerId, (providerId, previousId) => {
  const provider = props.providers.find((item) => item.id === providerId);
  if (!provider) return;
  if (!model.value.baseUrl || previousId) model.value.baseUrl = provider.defaultBaseUrl;
  if (!model.value.displayName || previousId) model.value.displayName = `${providerLabel(provider)} ${capabilityName.value}`;
  model.value.apiVersion = provider.providerType === 'azure_openai' ? (model.value.apiVersion || '2024-10-21') : '';
});
</script>
