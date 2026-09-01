<template>
  <div class="presentation-settings">
    <header class="panel-header">
      <div>
        <div class="panel-title">{{ t('PPT 生成设置') }}</div>
        <div class="panel-subtitle">{{ t('固定企业的 PPT 生成路线与模型，不再根据环境自动切换。') }}</div>
      </div>
      <n-button type="primary" :loading="saving" :disabled="loading" @click="save">
        {{ t('保存配置') }}
      </n-button>
    </header>

    <n-spin :show="loading">
      <section class="settings-section" aria-labelledby="presentation-mode-title">
        <div id="presentation-mode-title" class="section-title">{{ t('生成方式') }}</div>
        <div class="section-help">{{ t('企业内所有新建 PPT 都使用这里选择的路线。') }}</div>

        <div class="mode-grid" role="radiogroup" :aria-label="t('生成方式')">
          <button
            v-for="option in modeOptions"
            :key="option.value"
            type="button"
            class="mode-card"
            :class="{ selected: form.generationMode === option.value }"
            role="radio"
            :aria-checked="form.generationMode === option.value"
            @click="form.generationMode = option.value"
          >
            <span class="mode-radio" aria-hidden="true"><span /></span>
            <span class="mode-copy">
              <strong>{{ option.label }}</strong>
              <span>{{ option.description }}</span>
            </span>
            <n-tag v-if="option.value === 'llm'" size="small" :bordered="false">{{ t('稳定') }}</n-tag>
            <n-tag v-else size="small" type="info" :bordered="false">{{ t('视觉增强') }}</n-tag>
          </button>
        </div>
      </section>

      <section class="settings-section model-section" aria-labelledby="presentation-model-title">
        <div id="presentation-model-title" class="section-title">{{ t('PPT 模型配置') }}</div>
        <div class="section-help">{{ activeModelHelp }}</div>

        <n-form label-placement="top" :show-feedback="false">
          <n-form-item :label="t('内容与布局模型')" required>
            <ModelCapabilitySelect
              v-model="form.llmModelId"
              capability="chat"
              :placeholder="t('选择支持对话能力的模型')"
            />
            <div class="field-help">{{ t('负责故事线、页面内容与可编辑布局规划。') }}</div>
          </n-form-item>

          <template v-if="form.generationMode === 'image_rebuild'">
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
          </template>
        </n-form>
      </section>

      <n-alert v-if="!configured" type="info" :bordered="false" class="status-alert">
        {{ t('尚未保存企业 PPT 设置。保存前，系统继续使用 LLM 模式和企业默认对话模型。') }}
      </n-alert>
      <n-alert v-else type="success" :bordered="false" class="status-alert">
        {{ t('当前配置已生效。模型被禁用或删除后，PPT 生成会停止并提示管理员修复配置。') }}
      </n-alert>
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
  type PresentationGenerationMode,
} from '@/api/presentation-settings';
import { t } from '@/composables/i18n';

const message = useMessage();
const loading = ref(false);
const saving = ref(false);
const configured = ref(false);
const form = reactive({
  generationMode: 'llm' as PresentationGenerationMode,
  llmModelId: '',
  imageModelId: '',
  visionModelId: '',
});

const modeOptions = computed(() => [
  {
    value: 'llm' as const,
    label: t('LLM 自由布局'),
    description: t('由大模型直接生成内容和可编辑页面布局，速度更快、依赖更少。'),
  },
  {
    value: 'image_rebuild' as const,
    label: t('图片重建'),
    description: t('先生成整页视觉稿，再识别并重建为可编辑元素，视觉表现更强。'),
  },
]);

const activeModelHelp = computed(() => form.generationMode === 'image_rebuild'
  ? t('图片重建需要内容、图片生成和视觉理解三类模型，保存时会逐项校验。')
  : t('LLM 自由布局只需要一个已启用的对话模型。'));

function applySettings(settings: Awaited<ReturnType<typeof fetchPresentationSettings>>) {
  configured.value = settings.configured;
  form.generationMode = settings.generationMode;
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
  if (form.generationMode === 'image_rebuild' && (!form.imageModelId || !form.visionModelId)) {
    message.error(t('图片重建模式需要选择图片生成模型和视觉重建模型'));
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

.mode-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}

.mode-card {
  min-height: 112px;
  display: grid;
  grid-template-columns: 18px minmax(0, 1fr) auto;
  align-items: flex-start;
  gap: 12px;
  padding: 18px;
  border: 1px solid #dfe4ec;
  border-radius: 10px;
  background: #fff;
  color: inherit;
  cursor: pointer;
  text-align: left;
  transition: border-color 180ms ease, box-shadow 180ms ease, background 180ms ease;
}

.mode-card:hover {
  border-color: #8eabff;
}

.mode-card:focus-visible {
  outline: 3px solid rgba(47, 107, 255, 0.24);
  outline-offset: 2px;
}

.mode-card.selected {
  border-color: #2f6bff;
  background: #f7f9ff;
  box-shadow: 0 0 0 3px rgba(47, 107, 255, 0.1);
}

.mode-radio {
  width: 16px;
  height: 16px;
  margin-top: 2px;
  display: grid;
  place-items: center;
  border: 1.5px solid #9aa4b2;
  border-radius: 50%;
}

.mode-card.selected .mode-radio {
  border-color: #2f6bff;
}

.mode-card.selected .mode-radio span {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #2f6bff;
}

.mode-copy {
  display: flex;
  flex-direction: column;
  gap: 7px;
}

.mode-copy strong {
  color: #172033;
  font-size: 15px;
}

.mode-copy span {
  color: #667085;
  font-size: 13px;
  line-height: 1.55;
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
:global(html.dark) .section-title,
:global(html.dark) .mode-copy strong {
  color: #f4f4f5;
}

:global(html.dark) .panel-header,
:global(html.dark) .settings-section {
  border-color: #263044;
}

:global(html.dark) .mode-card {
  border-color: #334155;
  background: #111827;
}

:global(html.dark) .mode-card.selected {
  border-color: #60a5fa;
  background: rgba(59, 130, 246, 0.1);
}

@media (max-width: 760px) {
  .panel-header {
    flex-direction: column;
  }

  .mode-grid {
    grid-template-columns: 1fr;
  }
}
</style>
