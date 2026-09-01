<template>
  <div class="step-content">
    <div class="step-heading">
      <span class="step-kicker">{{ t('步骤 4 / 5') }}</span>
      <h2>{{ t('配置其他模型') }}</h2>
      <p>{{ t('这些模型用于扩展 MOVO 的专项能力，可以跳过并在管理后台随时补充。') }}</p>
    </div>

    <div class="model-cards">
      <section v-for="item in model" :key="item.capability" class="model-card" :class="{ enabled: item.enabled }">
        <div class="model-summary">
          <span class="model-icon" :class="`model-icon-${item.capability}`" aria-hidden="true" v-html="icons[item.capability]"></span>
          <div class="model-copy">
            <div class="model-title-row">
              <h3>{{ definitions[item.capability].name }}</h3>
              <n-tag size="small" :type="item.enabled ? 'success' : 'default'">
                {{ item.enabled ? t('已启用配置') : t('可选') }}
              </n-tag>
            </div>
            <p>{{ definitions[item.capability].description }}</p>
            <span class="model-impact">{{ definitions[item.capability].impact }}</span>
            <span v-if="item.capability === 'embedding' || item.capability === 'rerank'" class="model-recommendation">
              {{ t('推荐优先使用通义千问，也可以选择其他兼容供应商。') }}
            </span>
          </div>
          <n-switch
            :value="item.enabled"
            :aria-label="definitions[item.capability].name"
            @update:value="(enabled: boolean) => toggleModel(item, enabled)"
          />
        </div>
        <div v-if="item.enabled" class="model-form">
          <SetupModelFields
            v-model="item.model"
            :providers="providersFor(item.capability)"
            :providers-loading="providersLoading"
          />
        </div>
      </section>
    </div>

    <div class="actions">
      <n-button size="large" :disabled="submitting" @click="$emit('back')">{{ t('上一步') }}</n-button>
      <n-button size="large" type="primary" :loading="submitting" @click="$emit('next')">
        {{ t('下一步：联网搜索') }}
      </n-button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import { t } from '@/composables/i18n';
import type { SetupModelProvider } from '@/api/setup';
import type { SetupOptionalModelForm } from './types';
import SetupModelFields from './SetupModelFields.vue';

const props = defineProps<{
  providers: SetupModelProvider[];
  providersLoading: boolean;
  submitting: boolean;
}>();
const model = defineModel<SetupOptionalModelForm[]>({ required: true });
defineEmits<{ back: []; next: [] }>();

function toggleModel(item: SetupOptionalModelForm, enabled: boolean) {
  item.enabled = enabled;
  if (enabled && !item.model.providerId && props.providers.length) {
    const recommended = (item.capability === 'embedding' || item.capability === 'rerank')
      ? props.providers.find((provider) => provider.code === 'qwen')
      : undefined;
    item.model.providerId = (recommended || props.providers[0]).id;
  }
}

function providersFor(capability: SetupOptionalModelForm['capability']) {
  if (capability !== 'embedding' && capability !== 'rerank') return props.providers;
  return [...props.providers].sort((left, right) => {
    if (left.code === 'qwen') return -1;
    if (right.code === 'qwen') return 1;
    return 0;
  });
}
const definitions = computed(() => ({
  embedding: {
    name: t('向量模型（Embedding）'),
    description: t('把文档和问题转换为向量，用于知识库语义检索、文档问答和 RAG。'),
    impact: t('知识库必需：未配置时仍可对话，但文档无法完成向量学习与检索。'),
  },
  rerank: {
    name: t('重排模型（Rerank）'),
    description: t('对向量检索候选内容再次排序，提高知识库答案的相关性与准确度。'),
    impact: t('推荐配置：未配置不影响基础检索，但复杂问题的召回排序可能不够准确。'),
  },
  vision: {
    name: t('视觉模型（Vision）'),
    description: t('理解图片、截图、扫描件和图表内容，用于视觉问答与图片信息提取。'),
    impact: t('未配置时：图片理解类任务需稍后配置视觉模型。'),
  },
  image: {
    name: t('文生图模型（Image）'),
    description: t('根据文字生成图片，用于文章配图、海报、创意素材和视觉草图。'),
    impact: t('未配置时：不影响文字对话，图片生成能力暂不可用。'),
  },
}));

const icons: Record<SetupOptionalModelForm['capability'], string> = {
  embedding: '<svg viewBox="0 0 24 24" fill="none"><circle cx="7" cy="7" r="3"/><circle cx="17" cy="7" r="3"/><circle cx="12" cy="17" r="3"/><path d="m9.5 8.5 1.5 5.5m3.5-5.5L13 14M10 7h4"/></svg>',
  rerank: '<svg viewBox="0 0 24 24" fill="none"><path d="M8 6h12M8 12h9M8 18h6"/><path d="m3 7 1.5-1.5L6 7M3 13l1.5-1.5L6 13M3 19l1.5-1.5L6 19"/></svg>',
  vision: '<svg viewBox="0 0 24 24" fill="none"><path d="M2.5 12s3.5-6 9.5-6 9.5 6 9.5 6-3.5 6-9.5 6-9.5-6-9.5-6Z"/><circle cx="12" cy="12" r="2.5"/></svg>',
  image: '<svg viewBox="0 0 24 24" fill="none"><rect x="3" y="4" width="18" height="16" rx="2"/><circle cx="9" cy="9" r="2"/><path d="m4 17 4-4 3 3 3-3 6 5"/></svg>',
};
</script>

<style scoped>
.step-content { display: grid; gap: 16px; }
.step-heading { margin-bottom: 2px; }
.step-kicker { color: #3568e8; font-size: 12px; font-weight: 700; letter-spacing: .08em; text-transform: uppercase; }
.step-heading h2 { margin: 6px 0; color: #10204a; font-size: 24px; }
.step-heading p { margin: 0; color: #64748b; line-height: 1.6; }
.model-cards { display: grid; gap: 12px; }
.model-card { overflow: hidden; border: 1px solid #e0e7f1; border-radius: 14px; background: #fafcff; transition: border-color .2s ease, box-shadow .2s ease; }
.model-card.enabled { border-color: #a9c0f7; box-shadow: 0 8px 24px rgba(53, 104, 232, .08); }
.model-summary { display: grid; grid-template-columns: auto minmax(0, 1fr) auto; align-items: start; gap: 14px; padding: 16px; }
.model-icon { display: grid; width: 42px; height: 42px; place-items: center; border-radius: 12px; background: #eaf0ff; color: #315fc8; }
.model-icon :deep(svg) { width: 22px; stroke: currentColor; stroke-linecap: round; stroke-linejoin: round; stroke-width: 1.8; }
.model-icon-embedding { background: #e8f7f2; color: #168461; }
.model-icon-rerank { background: #fff4df; color: #b66a00; }
.model-icon-image { background: #f4ecff; color: #7b43c7; }
.model-copy { min-width: 0; }
.model-title-row { display: flex; align-items: center; gap: 8px; }
.model-title-row h3 { margin: 0; color: #17233d; font-size: 15px; }
.model-copy p { margin: 5px 0 3px; color: #53617b; font-size: 13px; line-height: 1.55; }
.model-impact { color: #7b879c; font-size: 12px; line-height: 1.5; }
.model-recommendation { display: block; margin-top: 4px; color: #3568e8; font-size: 12px; line-height: 1.5; }
.model-form { padding: 18px 16px 2px; border-top: 1px solid #e6ecf5; background: #fff; }
.actions { display: grid; grid-template-columns: auto minmax(220px, 1fr); gap: 10px; margin-top: 2px; }
@media (max-width: 600px) { .model-summary { grid-template-columns: auto minmax(0, 1fr); } .model-summary :deep(.n-switch) { grid-column: 2; } .actions { grid-template-columns: 1fr; } }
@media (prefers-reduced-motion: reduce) { .model-card { transition: none; } }
</style>
