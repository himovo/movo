<template>
  <div class="image-runtime-fields">
    <n-form-item :label="t('图片接口类型')" required>
      <n-select
        :value="runtimeKind || null"
        :options="runtimeOptions"
        :placeholder="t('选择图片生成接口')"
        @update:value="updateRuntimeKind"
      />
    </n-form-item>
    <n-form-item :label="t('生成尺寸')">
      <n-input
        :value="imageSettings.size || ''"
        :placeholder="sizePlaceholder"
        @update:value="updateSetting('size', $event)"
      />
    </n-form-item>
    <n-form-item v-if="runtimeKind !== 'dashscope_image'" :label="t('生成质量')">
      <n-select
        :value="imageSettings.quality || null"
        :options="qualityOptions"
        :placeholder="t('默认使用低质量以兼顾速度')"
        clearable
        @update:value="updateSetting('quality', $event || '')"
      />
    </n-form-item>
    <n-form-item v-if="runtimeKind === 'azure_openai_images'" :label="t('Azure 图片 API')">
      <n-select
        :value="imageSettings.apiStyle || 'v1'"
        :options="azureApiOptions"
        @update:value="updateSetting('apiStyle', $event)"
      />
    </n-form-item>
    <div class="runtime-help">{{ runtimeHelp }}</div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import { t } from '@/composables/i18n';
import type { ImageModelSettings, ImageRuntimeKind } from '@/api/models';

const props = defineProps<{
  runtimeKind: ImageRuntimeKind | '';
  imageSettings: ImageModelSettings;
  providerCode: string;
  providerType: string;
}>();

const emit = defineEmits<{
  (event: 'update:runtimeKind', value: ImageRuntimeKind): void;
  (event: 'update:imageSettings', value: ImageModelSettings): void;
}>();

const allRuntimeOptions = [
  { label: 'OpenAI Images API', value: 'openai_images' },
  { label: 'Azure OpenAI Images API', value: 'azure_openai_images' },
  { label: t('阿里云百炼 DashScope 图片 API'), value: 'dashscope_image' },
];

const runtimeOptions = computed(() => {
  if (props.providerType === 'azure_openai') {
    return allRuntimeOptions.filter(item => item.value === 'azure_openai_images');
  }
  if (props.providerCode === 'qwen') {
    return allRuntimeOptions.filter(item => item.value === 'dashscope_image');
  }
  return allRuntimeOptions;
});

const qualityOptions = [
  { label: t('低（速度优先）'), value: 'low' },
  { label: t('中'), value: 'medium' },
  { label: t('高（质量优先）'), value: 'high' },
  { label: t('自动'), value: 'auto' },
];

const azureApiOptions = [
  { label: 'OpenAI v1 · /openai/v1/images/generations', value: 'v1' },
  { label: t('Azure Deployment 路径'), value: 'deployment' },
];

const sizePlaceholder = computed(() => {
  if (props.runtimeKind === 'dashscope_image') return '如: 1664*928';
  if (props.runtimeKind === 'azure_openai_images') return '如: 1536x1024 / 1536x864';
  return '如: 1536x1024';
});

const runtimeHelp = computed(() => {
  if (props.runtimeKind === 'dashscope_image') {
    return t('通义千问图片模型使用 DashScope 原生接口；qwen-image-max/plus 推荐 1664*928（16:9）。');
  }
  if (props.runtimeKind === 'azure_openai_images') {
    return t('模型 ID 请填写 Azure Deployment 名称；GPT Image 1 系列推荐 1536x1024，GPT Image 2 可使用 1536x864。');
  }
  return t('适用于实现 /images/generations 的 OpenAI 兼容图片服务。');
});

function updateRuntimeKind(value: ImageRuntimeKind) {
  emit('update:runtimeKind', value);
}

function updateSetting(key: keyof ImageModelSettings, value: string) {
  emit('update:imageSettings', { ...props.imageSettings, [key]: value });
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

:global(html.dark) .image-runtime-fields {
  border-color: #263044;
  background: #151c2b;
}

@media (max-width: 700px) {
  .image-runtime-fields {
    grid-template-columns: 1fr;
  }
}
</style>
