<script setup lang="ts">
import { t } from '@/composables/i18n';
import { computed } from 'vue';
import type { AgentCapabilityKey, PositionRoleDraft } from '@/api/positionRoles';

const props = defineProps<{
  modelValue: PositionRoleDraft;
  disabled?: boolean;
}>();
const emit = defineEmits<{ 'update:modelValue': [value: PositionRoleDraft] }>();

const draft = computed({
  get: () => props.modelValue,
  set: (value) => emit('update:modelValue', value),
});

const capabilityOptions: Array<{ key: AgentCapabilityKey; label: string; description: string }> = [
  { key: 'content_generation', label: t('legacy.content_generation'), description: t('legacy.create_professional_articles_reports_and_plans') },
  { key: 'image_generation', label: t('legacy.image_generation'), description: t('legacy.generate_images_directly_or_for_content_tasks') },
  { key: 'code_generation', label: t('legacy.code_generation'), description: t('legacy.code_agent_project_file_terminal_and_git_operations') },
  { key: 'browser_automation', label: t('legacy.browser_automation'), description: t('legacy.allow_the_agent_to_use_the_local_browser_for') },
  { key: 'internal_knowledge', label: t('legacy.internal_knowledge_search_e7ef223'), description: t('legacy.search_enterprise_material_within_existing_knowledge_permissions') },
];
const impactPreview = computed(() => {
  const enabled = capabilityOptions.filter(item => draft.value.capabilities[item.key]).map(item => item.label);
  return enabled.length ? enabled.join(t('legacy.message')) : t('legacy.general_q_a');
});

function setCapability(key: AgentCapabilityKey, enabled: boolean) {
  draft.value = { ...draft.value, capabilities: { ...draft.value.capabilities, [key]: enabled } };
}
</script>

<template>
  <div class="capability-editor">
    <section>
      <h3>{{ t('legacy.agent_capabilities') }}</h3>
      <p class="section-help">{{ t('legacy.employee_entry_points_and_runtime_calls_both_follow_these') }}</p>
      <div class="capability-grid">
        <button
          v-for="item in capabilityOptions"
          :key="item.key"
          type="button"
          class="capability-card"
          :class="{ active: draft.capabilities[item.key] }"
          :disabled="disabled"
          @click="setCapability(item.key, !draft.capabilities[item.key])"
        >
          <span class="capability-card__copy"><strong>{{ item.label }}</strong><small>{{ item.description }}</small></span>
          <n-switch :value="draft.capabilities[item.key]" :disabled="disabled" @update:value="setCapability(item.key, $event)" @click.stop />
        </button>
      </div>
    </section>

    <n-alert type="info" :bordered="false">
      <strong>{{ t('legacy.employee_impact_preview') }}</strong>{{ impactPreview }}
      <div class="resource-note">{{ t('legacy.configure_the_audience_for_each_skill_mcp_server_or') }}</div>
    </n-alert>
  </div>
</template>

<style scoped>
.capability-editor { display: grid; gap: 4px; }
h3 { margin: 0 0 6px; color: #172033; font-size: 15px; }
.section-help { margin: 0 0 14px; color: #667085; font-size: 13px; }
.capability-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; }
.capability-card { min-height: 76px; display: flex; align-items: center; justify-content: space-between; gap: 16px; border: 1px solid #e4e7ec; border-radius: 10px; background: #fff; padding: 14px; text-align: left; cursor: pointer; transition: border-color .2s, background-color .2s; }
.capability-card:hover { border-color: #9bbcff; }
.capability-card.active { border-color: #7aa2ff; background: #f6f9ff; }
.capability-card__copy { display: grid; gap: 5px; }
.capability-card small { color: #667085; line-height: 1.45; }
section :deep(.n-select) { margin-top: 12px; }
.resource-note { margin-top: 5px; color: #667085; font-size: 12px; }
@media (max-width: 760px) { .capability-grid { grid-template-columns: 1fr; } }
</style>
