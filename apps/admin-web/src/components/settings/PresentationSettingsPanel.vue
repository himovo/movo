<template>
  <div class="presentation-settings">
    <header class="panel-header">
      <div>
        <div class="panel-title">{{ t('PPT 生成设置') }}</div>
        <div class="panel-subtitle">{{ t('配置内容规划、整页视觉生成与可编辑重建所使用的模型。') }}</div>
      </div>
      <n-button type="primary" :loading="saving" :disabled="loading" @click="save">
        {{ t('保存配置') }}
      </n-button>
    </header>

    <n-spin :show="loading">
      <section class="settings-section model-section" aria-labelledby="presentation-model-title">
        <div id="presentation-model-title" class="section-title">{{ t('PPT 模型配置') }}</div>
        <div class="section-help">{{ t('PPT 生成需要内容、图片生成和视觉理解三类模型，保存时会逐项校验。') }}</div>

        <n-form label-placement="top" :show-feedback="false">
          <n-form-item :label="t('内容与布局模型')" required>
            <ModelCapabilitySelect
              v-model="form.llmModelId"
              capability="chat"
              :placeholder="t('选择支持对话能力的模型')"
            />
            <div class="field-help">{{ t('负责故事线、页面内容与可编辑布局规划。') }}</div>
          </n-form-item>

          <n-form-item :label="t('图片生成模型')" required>
            <ModelCapabilitySelect
              v-model="form.imageModelId"
              capability="image_generation"
              :placeholder="t('选择支持图片生成能力的模型')"
            />
            <div class="field-help">{{ t('负责生成每页完整视觉稿和必要的图片素材。') }}</div>
          </n-form-item>

          <n-form-item :label="t('视觉重建模型')" required>
            <ModelCapabilitySelect
              v-model="form.visionModelId"
              capability="vision"
              :placeholder="t('选择支持视觉理解能力的模型')"
            />
            <div class="field-help">{{ t('负责理解视觉稿并重建为可编辑的文字、图形和图片元素。') }}</div>
          </n-form-item>
        </n-form>
      </section>

      <n-alert v-if="!configured" type="info" :bordered="false" class="status-alert">
        {{ t('尚未完成企业 PPT 模型配置。请配置三类模型后再生成 PPT。') }}
      </n-alert>
      <n-alert v-else type="success" :bordered="false" class="status-alert">
        {{ t('当前配置已生效。模型被禁用或删除后，PPT 生成会停止并提示管理员修复配置。') }}
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
    return String(error.response?.data?.detail || error.message || t('配置保存失败'));
  }
  return error instanceof Error ? error.message : String(error || t('配置保存失败'));
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
    message.error(t('请选择内容与布局模型'));
    return;
  }
  if (!form.imageModelId || !form.visionModelId) {
    message.error(t('请选择图片生成模型和视觉重建模型'));
    return;
  }
  saving.value = true;
  try {
    applySettings(await savePresentationSettings({ ...form }));
    message.success(t('PPT 生成配置已保存'));
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
