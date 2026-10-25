<template>
  <section class="material-config" @click.stop>
    <header class="config-heading">
      <span class="heading-icon" aria-hidden="true">▤</span>
      <div><strong>{{ t('legacy.where_does_the_material_come_from') }}</strong><p>{{ t('legacy.choose_the_material_this_step_reads_for_later_steps') }}</p></div>
    </header>

    <div class="source-choices" role="group" :aria-label="t('legacy.material_source')">
      <button type="button" class="source-choice" :class="{ selected: sourceType === 'upload' }"
        :aria-pressed="sourceType === 'upload'" @click="setSourceType('upload')">
        <span class="choice-icon upload-icon" aria-hidden="true">↑</span>
        <span class="choice-copy"><strong>{{ t('legacy.user_upload') }}</strong><small>{{ t('legacy.the_user_provides_a_file_when_running_the_skill') }}</small></span>
        <span class="choice-check" aria-hidden="true">✓</span>
      </button>
      <button type="button" class="source-choice" :class="{ selected: sourceType === 'knowledge_document' }"
        :aria-pressed="sourceType === 'knowledge_document'" @click="setSourceType('knowledge_document')">
        <span class="choice-icon knowledge-icon" aria-hidden="true">▤</span>
        <span class="choice-copy"><strong>{{ t('legacy.knowledge_document') }}</strong><small>{{ t('legacy.read_a_selected_parsed_document') }}</small></span>
        <span class="choice-check" aria-hidden="true">✓</span>
      </button>
    </div>

    <div v-if="sourceType === 'knowledge_document'" class="source-detail">
      <div class="field-heading"><strong>{{ t('legacy.select_document') }}</strong><span>{{ t('legacy.parsed_organization_knowledge_documents') }}</span></div>
      <OrganizationKnowledgeDocumentPicker :value="String(businessConfig.knowledgeSourceId || '')"
        @update:value="setDocument" />
      <p class="field-hint">{{ t('legacy.filter_by_folder_search_by_name_and_browse_pages') }}</p>
    </div>
    <div v-else class="source-detail upload-detail">
      <span class="detail-dot" aria-hidden="true"></span>
      <span>{{ t('legacy.the_user_uploads_a_file_when_starting_the_task') }}</span>
    </div>

    <div class="output-field">
      <div class="field-heading"><strong>{{ t('legacy.name_this_material') }}</strong><span>{{ t('legacy.later_steps_use_this_name_to_refer_to_it') }}</span></div>
      <n-input :value="outputAlias" size="medium" :aria-label="t('legacy.material_output_name')" :placeholder="t('legacy.example_contract_to_review_review_criteria')"
        @update:value="(value: string) => emit('update:outputAlias', value)" />
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import { t } from '../../composables/i18n';
import OrganizationKnowledgeDocumentPicker from './OrganizationKnowledgeDocumentPicker.vue';

const props = defineProps<{ businessConfig: Record<string, any>; outputAlias: string }>();
const emit = defineEmits<{
  'update:businessConfig': [value: Record<string, any>];
  'update:outputAlias': [value: string];
}>();
const sourceType = computed(() => String(props.businessConfig.sourceType || 'upload'));

function patch(value: Record<string, any>) {
  const config = { ...props.businessConfig, ...value };
  delete config.sourceRole;
  emit('update:businessConfig', config);
}
function setSourceType(value: string) {
  if (value === sourceType.value) return;
  patch({ sourceType: value, knowledgeScope: value === 'knowledge_document' ? 'organization' : '', knowledgeSourceId: '' });
}
function setDocument(value: string) {
  patch({ knowledgeScope: 'organization', knowledgeSourceId: value });
}
</script>

<style scoped>
.material-config { margin: 14px 0 4px; padding: 18px; border: 1px solid #e2e9f4; border-radius: 16px; background: #fbfcff; }
.config-heading { display: flex; align-items: center; gap: 11px; margin-bottom: 15px; }
.heading-icon { display: grid; place-items: center; flex: 0 0 34px; height: 34px; border-radius: 10px; background: #eaf1ff; color: #3768dc; font-size: 19px; }
.config-heading strong { display: block; color: #1e2d46; font-size: 14px; }
.config-heading p { margin: 2px 0 0; color: #718098; font-size: 12px; }
.source-choices { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; }
.source-choice { display: flex; align-items: center; gap: 11px; min-width: 0; min-height: 72px; padding: 12px 14px; border: 1px solid #e0e6ef; border-radius: 12px; background: #fff; text-align: left; cursor: pointer; transition: border-color .16s, box-shadow .16s, background .16s; }
.source-choice:hover { border-color: #9db7f5; }
.source-choice:focus-visible { outline: 2px solid #4678ed; outline-offset: 2px; }
.source-choice.selected { border-color: #6d94f5; background: #f4f7ff; box-shadow: 0 0 0 2px #e6edff inset; }
.choice-icon { display: grid; place-items: center; flex: 0 0 36px; height: 36px; border-radius: 10px; font-size: 20px; font-weight: 600; }
.upload-icon { color: #3768dc; background: #eaf1ff; }
.knowledge-icon { color: #6976cb; background: #eff0ff; }
.choice-copy { display: grid; gap: 3px; min-width: 0; }
.choice-copy strong { color: #25344c; font-size: 13px; }
.choice-copy small { color: #65758c; font-size: 12px; }
.choice-check { display: grid; place-items: center; flex: 0 0 18px; height: 18px; margin-left: auto; border: 1px solid #cbd5e1; border-radius: 50%; color: transparent; font-size: 11px; }
.selected .choice-check { border-color: #4775e7; background: #4775e7; color: #fff; }
.source-detail { margin-top: 13px; padding: 14px; border: 1px solid #e8edf5; border-radius: 11px; background: #fff; }
.upload-detail { display: flex; align-items: center; gap: 9px; color: #53647c; font-size: 12px; }
.detail-dot { flex: 0 0 7px; height: 7px; border-radius: 50%; background: #4f7fec; }
.field-heading { display: flex; flex-wrap: wrap; align-items: baseline; gap: 4px 10px; margin-bottom: 8px; }
.field-heading strong { color: #2c3c55; font-size: 12px; font-weight: 700; }
.field-heading span { color: #66768c; font-size: 12px; }
.field-hint { margin: 7px 0 0; font-size: 11px; }
.field-hint { color: #8090a6; }
.output-field { margin-top: 15px; }
@media (max-width: 680px) { .material-config { padding: 14px; } .source-choices { grid-template-columns: 1fr; } }
</style>
