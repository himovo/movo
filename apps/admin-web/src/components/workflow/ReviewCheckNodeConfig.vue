<template>
  <section class="review-config" @click.stop>
    <header class="config-heading">
      <span class="heading-icon" aria-hidden="true">✓</span>
      <div><strong>{{ t('legacy.set_up_review') }}</strong><p>{{ t('legacy.choose_what_to_review_and_which_criteria_to_use') }}</p></div>
    </header>

    <div class="review-grid">
      <div class="review-panel subject-panel">
        <div class="panel-heading">
          <span class="panel-index">01</span>
          <div><strong>{{ t('legacy.what_to_review') }}</strong><small>{{ t('legacy.select_material_or_a_result_from_an_earlier_step') }}</small></div>
        </div>
        <n-select :value="selected('reviewSubjectNodeId', 'reviewSubject')" size="medium" clearable
          :options="sourceOptions" :aria-label="t('legacy.select_material_to_review')" :placeholder="t('legacy.select_material_to_review')"
          @update:value="(value: string | null) => selectSource('reviewSubjectNodeId', 'reviewSubject', value)" />
      </div>
      <div class="review-panel criteria-panel">
        <div class="panel-heading">
          <span class="panel-index">02</span>
          <div><strong>{{ t('legacy.review_criteria') }}</strong><small>{{ t('legacy.use_an_earlier_result_or_enter_criteria_directly') }}</small></div>
        </div>
        <div class="mode-switch" role="group" :aria-label="t('legacy.criteria_source')">
          <button type="button" :class="{ active: criteriaMode === 'upstream' }"
            :aria-pressed="criteriaMode === 'upstream'" @click="setCriteriaMode('upstream')">{{ t('legacy.earlier_result') }}</button>
          <button type="button" :class="{ active: criteriaMode === 'inline' }"
            :aria-pressed="criteriaMode === 'inline'" @click="setCriteriaMode('inline')">{{ t('legacy.enter_criteria') }}</button>
        </div>
        <n-select v-if="criteriaMode === 'upstream'"
          :value="selected('reviewCriteriaNodeId', 'reviewCriteria')" size="medium" clearable
          :options="sourceOptions" :aria-label="t('legacy.select_review_criteria')" :placeholder="t('legacy.select_a_rule_document_or_earlier_result')"
          @update:value="(value: string | null) => selectSource('reviewCriteriaNodeId', 'reviewCriteria', value)" />
        <n-input v-else :value="String(businessConfig.reviewCriteria || '')" type="textarea" :aria-label="t('legacy.enter_review_criteria')"
          :autosize="{ minRows: 2, maxRows: 5 }" :placeholder="t('legacy.example_flag_amounts_over_budget_or_missing_acceptance_terms')"
          @update:value="setInlineCriteria" />
      </div>
    </div>

    <p v-if="!sourceOptions.length" class="review-hint">{{ t('legacy.name_the_output_of_an_earlier_step_before_selecting') }}</p>
    <p v-else-if="invalidSelection" class="review-hint">{{ t('legacy.the_selected_step_is_no_longer_earlier_in_the') }}</p>

    <div class="delivery-field">
      <div class="delivery-heading"><strong>{{ t('legacy.deliver_review_results') }}</strong><small>{{ t('legacy.comments_preserve_the_uploaded_word_document_s_formatting_in') }}</small></div>
      <div class="delivery-options" role="group" :aria-label="t('legacy.review_delivery_format')">
        <button v-for="option in outputOptions" :key="option.value" type="button"
          :class="{ active: outputMode === option.value }" :aria-pressed="outputMode === option.value"
          @click="setOutputMode(option.value)">
          <strong>{{ t(option.label) }}</strong><small>{{ t(option.description) }}</small>
        </button>
      </div>
      <p v-if="outputMode !== 'report'" class="delivery-hint">{{ t('legacy.only_docx_supports_comments_in_the_original_other_formats') }}</p>
    </div>

    <div class="result-field">
      <div class="result-mark" aria-hidden="true">✓</div>
      <div class="result-copy"><strong>{{ t('legacy.name_review_output') }}</strong><small>{{ t('legacy.later_steps_can_use_this_result') }}</small></div>
      <n-input :value="outputAlias" size="medium" :aria-label="t('legacy.review_output_name')" :placeholder="t('legacy.example_review_findings')"
        @update:value="(value: string) => emit('update:outputAlias', value)" />
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import { t } from '../../composables/i18n';

type UpstreamOutput = { id: string; alias: string };
const props = defineProps<{ businessConfig: Record<string, any>; upstreamOutputs: UpstreamOutput[]; outputAlias: string }>();
const emit = defineEmits<{
  'update:businessConfig': [value: Record<string, any>];
  'update:outputAlias': [value: string];
}>();
const sourceOptions = computed(() => props.upstreamOutputs.map(item => ({ label: item.alias, value: item.id })));
const outputOptions = [
  { value: 'report', label: 'legacy.separate_report', description: 'legacy.list_findings_and_suggestions' },
  { value: 'annotated_docx', label: 'legacy.comments_in_original', description: 'legacy.comment_on_a_copy_of_the_word_document' },
  { value: 'both', label: 'legacy.both', description: 'legacy.commented_copy_and_full_report' },
] as const;
const outputMode = computed(() => String(props.businessConfig.outputMode || 'report'));
const criteriaMode = computed(() => {
  const mode = String(props.businessConfig.reviewCriteriaMode || '');
  if (mode === 'upstream' || mode === 'inline') return mode;
  const legacy = String(props.businessConfig.reviewCriteria || '');
  return props.businessConfig.reviewCriteriaNodeId || !legacy
    || props.upstreamOutputs.some(item => item.alias === legacy) ? 'upstream' : 'inline';
});
const invalidSelection = computed(() => ['reviewSubjectNodeId', 'reviewCriteriaNodeId'].some(key => {
  if (key === 'reviewCriteriaNodeId' && criteriaMode.value === 'inline') return false;
  const id = String(props.businessConfig[key] || '');
  return id && !props.upstreamOutputs.some(item => item.id === id);
}));
function selected(idKey: string, legacyKey: string): string | null {
  const id = String(props.businessConfig[idKey] || '');
  if (id) return id;
  return props.upstreamOutputs.find(item => item.alias === props.businessConfig[legacyKey])?.id || null;
}
function selectSource(idKey: string, legacyKey: string, id: string | null) {
  const alias = props.upstreamOutputs.find(item => item.id === id)?.alias || '';
  emit('update:businessConfig', cleanConfig({ ...props.businessConfig, [idKey]: id || '', [legacyKey]: alias }));
}
function cleanConfig(config: Record<string, any>) {
  delete config.evidenceRequirement;
  delete config.failurePolicy;
  return config;
}
function setCriteriaMode(mode: string) {
  if (mode === criteriaMode.value) return;
  emit('update:businessConfig', cleanConfig({ ...props.businessConfig,
    reviewCriteriaMode: mode, reviewCriteriaNodeId: '', reviewCriteria: '',
  }));
}
function setInlineCriteria(value: string) {
  emit('update:businessConfig', cleanConfig({ ...props.businessConfig,
    reviewCriteriaMode: 'inline', reviewCriteriaNodeId: '', reviewCriteria: value,
  }));
}
function setOutputMode(value: string) {
  emit('update:businessConfig', cleanConfig({ ...props.businessConfig, outputMode: value }));
}
</script>

<style scoped>
.review-config { margin: 14px 0 4px; padding: 18px; border: 1px solid #e2e9f4; border-radius: 16px; background: #fbfcff; }
.config-heading { display: flex; align-items: center; gap: 11px; margin-bottom: 15px; }
.heading-icon { display: grid; place-items: center; flex: 0 0 34px; height: 34px; border-radius: 10px; background: #fff1df; color: #bf7416; font-size: 18px; font-weight: 700; }
.config-heading strong { display: block; color: #1e2d46; font-size: 14px; }
.config-heading p { margin: 2px 0 0; color: #718098; font-size: 12px; }
.review-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; }
.review-panel { min-width: 0; padding: 15px; border: 1px solid #e0e7f1; border-radius: 12px; background: #fff; }
.subject-panel { border-top: 3px solid #7c9df2; }
.criteria-panel { border-top: 3px solid #e8aa58; }
.panel-heading { display: flex; align-items: center; gap: 9px; margin-bottom: 13px; }
.panel-index { display: grid; place-items: center; flex: 0 0 27px; height: 27px; border-radius: 8px; background: #eaf1ff; color: #3d6ed8; font-size: 11px; font-weight: 800; }
.criteria-panel .panel-index { background: #fff2df; color: #b87720; }
.panel-heading strong { display: block; color: #283850; font-size: 13px; }
.panel-heading small { display: block; margin-top: 2px; color: #66768c; font-size: 12px; }
.mode-switch { display: flex; gap: 3px; width: max-content; max-width: 100%; margin-bottom: 10px; padding: 3px; border: 1px solid #e5eaf1; border-radius: 9px; background: #f3f6fa; }
.mode-switch button { min-height: 29px; padding: 3px 12px; border: 0; border-radius: 6px; background: transparent; color: #65758c; font-size: 12px; font-weight: 600; cursor: pointer; }
.mode-switch button.active { background: #fff; color: #a56414; box-shadow: 0 1px 4px #22314c1a; }
.mode-switch button:focus-visible { outline: 2px solid #4678ed; outline-offset: 2px; }
.review-hint { margin: 10px 2px 0; color: #b45309; font-size: 11px; }
.delivery-field { margin-top: 13px; padding: 15px; border: 1px solid #e0e7f1; border-radius: 12px; background: #fff; }
.delivery-heading strong { display: block; color: #283850; font-size: 13px; }
.delivery-heading small { display: block; margin-top: 3px; color: #718098; font-size: 12px; }
.delivery-options { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 8px; margin-top: 12px; }
.delivery-options button { text-align: left; min-width: 0; padding: 10px 12px; border: 1px solid #dce4ef; border-radius: 10px; background: #fff; cursor: pointer; }
.delivery-options button.active { border-color: #5d82e8; background: #f3f6ff; box-shadow: 0 0 0 1px #5d82e8; }
.delivery-options button:focus-visible { outline: 2px solid #4678ed; outline-offset: 2px; }
.delivery-options strong { display: block; color: #2b3c56; font-size: 12px; }
.delivery-options small { display: block; margin-top: 3px; color: #738199; font-size: 11px; }
.delivery-hint { margin: 10px 0 0; color: #856322; font-size: 11px; }
.result-field { display: flex; align-items: center; gap: 10px; margin-top: 13px; padding: 12px 14px; border: 1px solid #dbe8e5; border-radius: 11px; background: #f7fcfa; }
.result-mark { display: grid; place-items: center; flex: 0 0 27px; height: 27px; border-radius: 50%; background: #dff3eb; color: #258260; font-size: 13px; font-weight: 700; }
.result-copy { min-width: 130px; }
.result-copy strong { display: block; color: #2b5145; font-size: 12px; }
.result-copy small { display: block; margin-top: 2px; color: #728e83; font-size: 11px; }
.result-field :deep(.n-input) { flex: 1; min-width: 140px; max-width: 320px; margin-left: auto; }
@media (max-width: 760px) { .review-config { padding: 14px; } .review-grid { grid-template-columns: 1fr; } }
@media (max-width: 520px) { .result-field { flex-wrap: wrap; } .result-field :deep(.n-input) { flex-basis: 100%; max-width: none; } }
@media (max-width: 520px) { .delivery-options { grid-template-columns: 1fr; } }
</style>
