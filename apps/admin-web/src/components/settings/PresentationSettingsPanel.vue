<template>
  <div class="presentation-settings">
    <header class="panel-header">
      <div>
        <div class="panel-title">{{ t('legacy.ppt_generation_settings') }}</div>
        <div class="panel-subtitle">{{ t('legacy.configure_the_models_used_for_content_planning_full_slide') }}</div>
      </div>
      <n-button type="primary" :loading="saving" :disabled="loading" @click="save">
        {{ t('legacy.save_817af18') }}
      </n-button>
    </header>

    <n-spin :show="loading">
      <section class="settings-section model-section" aria-labelledby="presentation-model-title">
        <div id="presentation-model-title" class="section-title">{{ t('legacy.ppt_model_configuration') }}</div>
        <div class="section-help">{{ t('legacy.ppt_generation_requires_content_image_generation_and_vision_models') }}</div>

        <n-form label-placement="top" :show-feedback="false">
          <n-form-item :label="t('legacy.content_layout_model')" required>
            <ModelCapabilitySelect
              v-model="form.llmModelId"
              capability="chat"
              :placeholder="t('legacy.select_a_chat_capable_model')"
            />
            <div class="field-help">{{ t('legacy.creates_the_storyline_slide_content_and_editable_layout_plan') }}</div>
          </n-form-item>

          <n-form-item :label="t('legacy.image_generation_model')" required>
            <ModelCapabilitySelect
              v-model="form.imageModelId"
              capability="image_generation"
              :placeholder="t('legacy.select_an_image_generation_model')"
            />
            <div class="field-help">{{ t('legacy.generates_complete_slide_visuals_and_required_image_assets') }}</div>
          </n-form-item>

          <n-form-item :label="t('legacy.vision_rebuild_model')" required>
            <ModelCapabilitySelect
              v-model="form.visionModelId"
              capability="vision"
              :placeholder="t('legacy.select_a_vision_capable_model')"
            />
            <div class="field-help">{{ t('legacy.understands_slide_visuals_and_rebuilds_editable_text_shapes_and') }}</div>
          </n-form-item>
        </n-form>
      </section>

      <n-alert v-if="!configured" type="info" :bordered="false" class="status-alert">
        {{ t('legacy.ppt_model_configuration_is_incomplete_configure_all_three_models') }}
      </n-alert>
      <n-alert v-else type="success" :bordered="false" class="status-alert">
        {{ t('legacy.the_configuration_is_active_if_a_selected_model_is') }}
      </n-alert>
    </n-spin>
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue';
import axios from 'axios';
import { useMessage } from 'naive-ui';
import ModelCapabilitySelect from '@/components/models/ModelCapabilitySelect.vue';
import {
  fetchPresentationSettings,
  savePresentationSettings,
} from '@/api/presentation-settings';
import { t } from '@/composables/i18n';

const message = useMessage();
const loading = ref(false);
const saving = ref(false);
const configured = ref(false);
const form = reactive({
  llmModelId: '',
  imageModelId: '',
  visionModelId: '',
});

function applySettings(settings: Awaited<ReturnType<typeof fetchPresentationSettings>>) {
  configured.value = settings.configured;
  form.llmModelId = settings.llmModelId;
  form.imageModelId = settings.imageModelId;
  form.visionModelId = settings.visionModelId;
}

function errorText(error: unknown): string {
  if (axios.isAxiosError(error)) {
    return String(error.response?.data?.detail || error.message || t('legacy.failed_to_save_configuration'));
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
  if (!form.llmModelId) {
    message.error(t('legacy.select_a_content_and_layout_model'));
    return;
  }
  if (!form.imageModelId || !form.visionModelId) {
    message.error(t('legacy.select_an_image_generation_model_and_a_vision_rebuild'));
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
  max-width: 820px;
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
  max-width: 640px;
}

.field-help {
  margin-top: 6px;
}

.status-alert {
  margin-top: 20px;
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
