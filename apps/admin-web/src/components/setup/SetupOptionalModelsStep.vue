<template>
  <div class="step-content">
    <div class="step-heading">
      <span class="step-kicker">{{ t('legacy.step_4_of_5') }}</span>
      <h2>{{ t('legacy.configure_other_models') }}</h2>
      <p>{{ t('legacy.these_models_extend_specialized_movo_capabilities_skip_them_now') }}</p>
    </div>

    <div class="model-cards">
      <section v-for="item in model" :key="item.capability" class="model-card" :class="{ enabled: item.enabled }">
        <div class="model-summary">
          <span class="model-icon" :class="`model-icon-${item.capability}`" aria-hidden="true" v-html="icons[item.capability]"></span>
          <div class="model-copy">
            <div class="model-title-row">
              <h3>{{ definitions[item.capability].name }}</h3>
              <n-tag size="small" :type="item.enabled ? 'success' : 'default'">
                {{ item.enabled ? t('legacy.enabled') : t('legacy.optional') }}
              </n-tag>
            </div>
            <p>{{ definitions[item.capability].description }}</p>
            <span class="model-impact">{{ definitions[item.capability].impact }}</span>
            <span v-if="item.capability === 'embedding' || item.capability === 'rerank'" class="model-recommendation">
              {{ t('legacy.qwen_is_recommended_first_but_any_compatible_provider_can') }}
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
      <n-button size="large" :disabled="submitting" @click="$emit('back')">{{ t('legacy.previous') }}</n-button>
      <n-button size="large" type="primary" :loading="submitting" @click="$emit('next')">
        {{ t('legacy.next_web_search') }}
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
    name: t('legacy.embedding_model_404347c'),
    description: t('legacy.converts_documents_and_questions_into_vectors_for_semantic_knowledge'),
    impact: t('additional.required_for_the_knowledge_base_chat_remains_available_without'),
  },
  rerank: {
    name: t('additional.rerank_model_rerank'),
    description: t('additional.rerank_vector_search_candidates_to_improve_the_relevance_and'),
    impact: t('additional.recommended_basic_search_still_works_without_it_but_ranking'),
  },
  vision: {
    name: t('legacy.vision_model_c7979d9'),
    description: t('legacy.understands_images_screenshots_scans_and_charts_for_visual_q'),
    impact: t('legacy.if_skipped_configure_a_vision_model_later_for_image'),
  },
  image: {
    name: t('legacy.image_generation_model_e90dc17'),
    description: t('legacy.generates_images_from_text_for_article_illustrations_posters_creative'),
    impact: t('legacy.if_skipped_text_chat_is_unaffected_image_generation_remains'),
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
