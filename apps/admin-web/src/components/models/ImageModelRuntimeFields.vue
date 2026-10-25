<template>
  <div class="image-runtime-fields">
    <n-form-item :label="t('legacy.api_type')" required>
      <n-select
        :value="runtimeKind || null"
        :options="runtimeOptions"
        :placeholder="t('legacy.select_an_image_api')"
        @update:value="updateRuntimeKind"
      />
    </n-form-item>
    <n-form-item :label="t('legacy.size')">
      <n-input
        :value="imageSettings.size || ''"
        :placeholder="t('legacy.omit_when_empty')"
        @update:value="updateSetting('size', $event)"
      />
    </n-form-item>
    <n-collapse class="advanced-settings">
      <n-collapse-item name="advanced">
        <template #header>
          <div class="advanced-title">
            <span>{{ t('legacy.advanced_settings') }}</span>
            <span>{{ t('legacy.fill_in_only_when_required_by_the_model_api') }}</span>
          </div>
        </template>
        <div class="advanced-fields">
          <n-form-item :label="t('legacy.quality')">
            <n-select
              :value="imageSettings.quality || null"
              :options="qualityOptions"
              :placeholder="t('legacy.omit_when_empty')"
              filterable
              tag
              clearable
              @update:value="updateSetting('quality', $event || '')"
            />
          </n-form-item>
          <n-form-item :label="t('legacy.output_format')">
            <n-select
              :value="imageSettings.outputFormat || null"
              :options="outputFormatOptions"
              :placeholder="t('legacy.omit_when_empty')"
              filterable
              tag
              clearable
              @update:value="updateSetting('outputFormat', $event || '')"
            />
          </n-form-item>
          <n-form-item :label="t('legacy.response_format')">
            <n-select
              :value="imageSettings.responseFormat || null"
              :options="responseFormatOptions"
              :placeholder="t('legacy.omit_when_empty')"
              filterable
              tag
              clearable
              @update:value="updateSetting('responseFormat', $event || '')"
            />
          </n-form-item>
          <n-form-item :label="t('legacy.image_count')">
            <n-input-number
              :value="imageSettings.n ?? null"
              :min="1"
              :max="10"
              :placeholder="t('legacy.omit_when_empty')"
              clearable
              style="width: 100%"
              @update:value="updateSetting('n', $event)"
            />
          </n-form-item>
          <n-form-item :label="t('legacy.aspect_ratio')">
            <n-input
              :value="imageSettings.ratio || ''"
              :placeholder="t('legacy.example_16_9_omit_when_empty')"
              @update:value="updateSetting('ratio', $event)"
            />
          </n-form-item>
          <n-form-item v-if="runtimeKind === 'azure_openai_images'" :label="t('legacy.azure_image_api')">
            <n-select
              :value="imageSettings.apiStyle || 'v1'"
              :options="azureApiOptions"
              @update:value="updateSetting('apiStyle', $event)"
            />
          </n-form-item>
          <template v-if="runtimeKind === 'custom_images'">
            <n-form-item :label="t('legacy.request_path')">
              <n-input
                :value="imageSettings.requestPath || ''"
                placeholder="/images/generations"
                @update:value="updateSetting('requestPath', $event)"
              />
            </n-form-item>
            <n-form-item :label="t('legacy.image_url_response_path')">
              <n-input
                :value="imageSettings.responseUrlPath || ''"
                placeholder="data.0.url"
                @update:value="updateSetting('responseUrlPath', $event)"
              />
            </n-form-item>
            <n-form-item :label="t('legacy.base64_response_path')">
              <n-input
                :value="imageSettings.responseBase64Path || ''"
                placeholder="data.0.b64_json"
                @update:value="updateSetting('responseBase64Path', $event)"
              />
            </n-form-item>
            <n-form-item class="full-width" :label="t('legacy.extra_request_parameters_json')">
              <div class="json-editor">
                <n-input
                  :value="imageSettings.extraParamsJson || ''"
                  type="textarea"
                  :rows="5"
                  placeholder='{ "extra_body": { "response_format": "url" } }'
                  @update:value="updateSetting('extraParamsJson', $event)"
                />
                <n-button size="small" secondary @click="formatExtraParams">{{ t('legacy.format_json') }}</n-button>
              </div>
            </n-form-item>
          </template>
          <div class="runtime-help">
            <div>{{ runtimeHelp }}</div>
            <div>{{ t('legacy.only_filled_fields_are_sent_empty_fields_are_omitted') }}</div>
          </div>
        </div>
      </n-collapse-item>
    </n-collapse>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import { NCollapse, NCollapseItem, useMessage } from 'naive-ui';
import { t } from '@/composables/i18n';
import type { ImageModelSettings, ImageRuntimeKind } from '@/api/models';

const props = defineProps<{
  runtimeKind: ImageRuntimeKind | '';
  imageSettings: ImageModelSettings;
  providerType: string;
}>();

const emit = defineEmits<{
  (event: 'update:runtimeKind', value: ImageRuntimeKind): void;
  (event: 'update:imageSettings', value: ImageModelSettings): void;
}>();
const message = useMessage();

const allRuntimeOptions = computed(() => [
  { label: 'OpenAI Images API', value: 'openai_images' },
  { label: 'Azure OpenAI Images API', value: 'azure_openai_images' },
  { label: t('legacy.alibaba_cloud_dashscope_image_api'), value: 'dashscope_image' },
  { label: t('legacy.custom_image_api'), value: 'custom_images' },
]);

const runtimeOptions = computed(() => {
  if (props.providerType === 'azure_openai') {
    return allRuntimeOptions.value.filter(item => ['azure_openai_images', 'custom_images'].includes(item.value));
  }
  return allRuntimeOptions.value.filter(item => item.value !== 'azure_openai_images');
});

const qualityOptions = computed(() => [
  { label: t('legacy.low_faster'), value: 'low' },
  { label: t('legacy.medium'), value: 'medium' },
  { label: t('legacy.high_quality_first'), value: 'high' },
  { label: t('legacy.auto'), value: 'auto' },
]);

const outputFormatOptions = ['png', 'jpeg', 'webp'].map(value => ({ label: value, value }));
const responseFormatOptions = ['url', 'b64_json'].map(value => ({ label: value, value }));

const azureApiOptions = computed(() => [
  { label: 'OpenAI v1 · /openai/v1/images/generations', value: 'v1' },
  { label: t('legacy.azure_deployment_path'), value: 'deployment' },
]);

const runtimeHelp = computed(() => {
  if (props.runtimeKind === 'dashscope_image') {
    return t('legacy.uses_the_native_dashscope_image_api_qwen_image_max');
  }
  if (props.runtimeKind === 'azure_openai_images') {
    return t('legacy.use_the_azure_deployment_name_as_the_model_id');
  }
  if (props.runtimeKind === 'custom_images') {
    return t('legacy.the_system_sends_model_and_prompt_automatically_and_parses');
  }
  return t('legacy.for_openai_compatible_image_services_implementing_images_generations');
});

function updateRuntimeKind(value: ImageRuntimeKind) {
  emit('update:runtimeKind', value);
  if (value === 'custom_images') {
    emit('update:imageSettings', {
      ...props.imageSettings,
      requestPath: props.imageSettings.requestPath || '/images/generations',
      responseUrlPath: props.imageSettings.responseUrlPath || 'data.0.url',
      responseBase64Path: props.imageSettings.responseBase64Path || 'data.0.b64_json',
      extraParamsJson: props.imageSettings.extraParamsJson || '{}',
    });
  }
}

function updateSetting(key: keyof ImageModelSettings, value: string | number | null) {
  emit('update:imageSettings', { ...props.imageSettings, [key]: value });
}

function formatExtraParams() {
  try {
    const parsed = JSON.parse(imageSettingsJson());
    if (!parsed || Array.isArray(parsed) || typeof parsed !== 'object') throw new Error();
    updateSetting('extraParamsJson', JSON.stringify(parsed, null, 2));
  } catch {
    message.error(t('legacy.enter_a_valid_json_object'));
  }
}

function imageSettingsJson() {
  return String(props.imageSettings.extraParamsJson || '{}').trim() || '{}';
}
</script>

<style scoped>
.image-runtime-fields {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 0 14px;
  padding: 14px 14px 4px;
  border: 1px solid #e6ebf5;
  border-radius: 8px;
  background: #f8faff;
}

.runtime-help {
  grid-column: 1 / -1;
  margin: -2px 0 10px;
  color: #667085;
  font-size: 12px;
  line-height: 1.6;
}

.advanced-settings {
  grid-column: 1 / -1;
  margin-bottom: 12px;
  padding: 0 2px;
}

.advanced-title {
  display: flex;
  align-items: baseline;
  gap: 10px;
}

.advanced-title span:last-child {
  color: #98a2b3;
  font-size: 12px;
  font-weight: 400;
}

.advanced-fields {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 0 14px;
  padding-top: 8px;
}

.full-width {
  grid-column: 1 / -1;
}

.json-editor {
  display: flex;
  width: 100%;
  align-items: flex-start;
  gap: 8px;
}

.json-editor :deep(.n-input) {
  flex: 1;
}

:global(html.dark) .image-runtime-fields {
  border-color: #263044;
  background: #151c2b;
}

@media (max-width: 700px) {
  .image-runtime-fields {
    grid-template-columns: 1fr;
  }

  .advanced-fields {
    grid-template-columns: 1fr;
  }
}
</style>
