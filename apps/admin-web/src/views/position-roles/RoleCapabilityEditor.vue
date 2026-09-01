<script setup lang="ts">
import { t } from '@/composables/i18n';
import { computed } from 'vue';
import type { AgentCapabilityKey, PositionRoleDraft, RoleResource } from '@/api/positionRoles';

const props = defineProps<{
  modelValue: PositionRoleDraft;
  tools: RoleResource[];
  skills: RoleResource[];
  disabled?: boolean;
}>();
const emit = defineEmits<{ 'update:modelValue': [value: PositionRoleDraft] }>();

const draft = computed({
  get: () => props.modelValue,
  set: (value) => emit('update:modelValue', value),
});

const capabilityOptions: Array<{ key: AgentCapabilityKey; label: string; description: string }> = [
  { key: 'content_generation', label: t('内容生成'), description: '文章、报告、方案等专业内容生产' },
  { key: 'image_generation', label: t('图片生成'), description: '直接生成图片或为内容任务生成配图' },
  { key: 'code_generation', label: t('代码生成'), description: 'Code Agent、项目、文件、终端与 Git 操作' },
  { key: 'browser_automation', label: t('浏览器自动运行'), description: '允许 Agent 操作本地浏览器完成网页任务' },
  { key: 'internal_knowledge', label: t('内部知识检索'), description: '在既有知识权限范围内检索企业资料' },
];
const impactPreview = computed(() => {
  const enabled = capabilityOptions.filter(item => draft.value.capabilities[item.key]).map(item => item.label);
  const toolText = draft.value.toolAccessMode === 'all' ? t('全部 MCP / 工具') : t('{count} 个 MCP / 工具', { count: draft.value.toolIds.length });
  const skillText = draft.value.skillAccessMode === 'all' ? t('全部 Skill') : t('{count} 个 Skill', { count: draft.value.skillIds.length });
  return t('{capabilities}；{tools}；{skills}', { capabilities: enabled.length ? enabled.join('、') : t('普通问答'), tools: toolText, skills: skillText });
});

function setCapability(key: AgentCapabilityKey, enabled: boolean) {
  draft.value = { ...draft.value, capabilities: { ...draft.value.capabilities, [key]: enabled } };
}
</script>

<template>
  <div class="capability-editor">
    <section>
      <h3>{{ t('Agent 能力') }}</h3>
      <p class="section-help">{{ t('员工端入口与运行时调用将同时遵守这些设置。') }}</p>
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

    <n-divider />
    <section>
      <h3>{{ t('MCP 与工具') }}</h3>
      <n-radio-group v-model:value="draft.toolAccessMode" :disabled="disabled">
        <n-space><n-radio value="all">{{ t('全部当前及后续工具') }}</n-radio><n-radio value="selected">{{ t('仅选择的工具') }}</n-radio></n-space>
      </n-radio-group>
      <n-select v-if="draft.toolAccessMode === 'selected'" v-model:value="draft.toolIds" multiple filterable max-tag-count="responsive" :disabled="disabled" :options="tools.map(item => ({ label: `${item.name} · ${item.type.toUpperCase()}`, value: item.id }))" :placeholder="t('选择允许使用的 MCP 或工具')" />
    </section>

    <n-divider />
    <section>
      <h3>Skill</h3>
      <n-radio-group v-model:value="draft.skillAccessMode" :disabled="disabled">
        <n-space><n-radio value="all">{{ t('全部当前及后续 Skill') }}</n-radio><n-radio value="selected">{{ t('仅选择的 Skill') }}</n-radio></n-space>
      </n-radio-group>
      <n-select v-if="draft.skillAccessMode === 'selected'" v-model:value="draft.skillIds" multiple filterable max-tag-count="responsive" :disabled="disabled" :options="skills.map(item => ({ label: item.name, value: item.id }))" :placeholder="t('选择允许使用的 Skill')" />
    </section>
    <n-alert type="info" :bordered="false"><strong>{{ t('员工端影响预览：') }}</strong>{{ impactPreview }}</n-alert>
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
@media (max-width: 760px) { .capability-grid { grid-template-columns: 1fr; } }
</style>
