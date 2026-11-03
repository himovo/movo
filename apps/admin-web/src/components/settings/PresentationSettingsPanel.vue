<template>
  <div class="presentation-settings">
    <header class="panel-header">
      <div>
        <div class="panel-title">{{ t('legacy.ppt_generation_settings') }}</div>
        <div class="panel-subtitle">{{ t('presentation.description') }}</div>
      </div>
      <n-button type="primary" :loading="saving" :disabled="loading" @click="save">
        {{ t('legacy.save_817af18') }}
      </n-button>
    </header>

    <n-spin :show="loading">
      <section class="settings-section">
        <n-space justify="space-between" align="center">
          <div class="section-title">{{ t('presentation.enable') }}</div>
          <n-switch v-model:value="form.enabled" :disabled="!modelsReady && !form.enabled" />
        </n-space>
        <div class="section-help">{{ t(modelsReady ? 'presentation.help' : 'presentation.unavailable') }}</div>
      </section>
      <section class="settings-section model-section" aria-labelledby="presentation-model-title">
        <div id="presentation-model-title" class="section-title">{{ t('legacy.ppt_model_configuration') }}</div>
        <n-alert type="info" :bordered="false" class="section-help">{{ t('presentation.modelHelp') }}</n-alert>

        <n-form label-placement="top" :show-feedback="false">
          <n-form-item :label="t('legacy.content_layout_model')" required>
            <div class="model-field">
              <ModelCapabilitySelect
                v-model="form.llmModelId"
                @availability="modelAvailability.llm = $event"
                capability="chat"
                :placeholder="t('legacy.select_a_chat_capable_model')"
              />
              <div class="field-help">{{ t('presentation.contentHelp') }}</div>
            </div>
          </n-form-item>

          <n-form-item :label="t('legacy.image_generation_model')" required>
            <div class="model-field">
              <ModelCapabilitySelect
                v-model="form.imageModelId"
                @availability="modelAvailability.image = $event"
                capability="image_generation"
                :placeholder="t('legacy.select_an_image_generation_model')"
              />
              <div class="field-help">{{ t('presentation.imageHelp') }}</div>
            </div>
          </n-form-item>
        </n-form>
      </section>
    </n-spin>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue';
import axios from 'axios';
import { useMessage } from 'naive-ui';
import ModelCapabilitySelect from '@/components/models/ModelCapabilitySelect.vue';
import {
  fetchPresentationSettings,
  savePresentationSettings,
} from '@/api/presentation-settings';
import { t } from '@/composables/i18n';
import { localizedServerText } from '@/utils/serverText';

const message = useMessage();
const loading = ref(false);
const saving = ref(false);
const modelAvailability = reactive({ llm: false, image: false });
const modelsReady = computed(() => Object.values(modelAvailability).every(Boolean));
const form = reactive({
  enabled: false,
  llmModelId: '',
  imageModelId: '',
});

function applySettings(settings: Awaited<ReturnType<typeof fetchPresentationSettings>>) {
  form.enabled = settings.enabled;
  form.llmModelId = settings.llmModelId;
  form.imageModelId = settings.imageModelId;
}

function errorText(error: unknown): string {
  if (axios.isAxiosError(error)) {
    if (String(error.response?.data?.detail || '').startsWith('Presentation model unavailable:')) {
      return t('presentation.unavailable');
    }
    return localizedServerText(error.response?.data?.detail || error.message, t('legacy.failed_to_save_configuration'));
  }
  return error instanceof Error ? error.message : String(error || t('legacy.failed_to_save_configuration'));
}

async function load() {
  loading.value = true;
  try {
    applySettings(await fetchPresentationSettings());
  } catch (error) {
    message.error(errorText(error));
  } finally {
    loading.value = false;
  }
}

async function save() {
  if (form.enabled && !form.llmModelId) {
    message.error(t('legacy.select_a_content_and_layout_model'));
    return;
  }
  if (form.enabled && !form.imageModelId) {
    message.error(t('presentation.selectImage'));
    return;
  }
  saving.value = true;
  try {
    applySettings(await savePresentationSettings({ ...form }));
    message.success(t('legacy.ppt_generation_settings_saved'));
  } catch (error) {
    message.error(errorText(error));
  } finally {
    saving.value = false;
  }
}

onMounted(load);
</script>

<style scoped>
.presentation-settings {
  width: 100%;
  min-width: 0;
}

.panel-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 20px;
  padding-bottom: 18px;
  border-bottom: 1px solid #eef1f6;
}

.panel-title {
  color: #172033;
  font-size: 22px;
  font-weight: 700;
}

.panel-subtitle,
.section-help,
.field-help {
  color: #667085;
  font-size: 13px;
  line-height: 1.6;
}

.panel-subtitle {
  margin-top: 4px;
}

.settings-section {
  padding: 24px 0;
  border-bottom: 1px solid #eef1f6;
}

.section-title {
  color: #172033;
  font-size: 16px;
  font-weight: 700;
}

.section-help {
  margin: 5px 0 16px;
}

.model-section :deep(.n-form) {
  max-width: 760px;
}

.model-field { width:100%; min-width:0; }

.field-help {
  margin-top: 6px;
}

:global(html.dark) .panel-title,
:global(html.dark) .section-title {
  color: #f4f4f5;
}

:global(html.dark) .panel-header,
:global(html.dark) .settings-section {
  border-color: #263044;
}

@media (max-width: 760px) {
  .panel-header {
    flex-direction: column;
  }
}
</style>
