<template>
  <div class="skill-details">
    <section class="summary-card">
      <div class="summary-row">
        <span class="summary-label">{{ t('名称') }}</span>
        <strong>{{ skill.name || t('未命名 Skill') }}</strong>
      </div>
      <div class="summary-row">
        <span class="summary-label">{{ t('技能描述') }}</span>
        <p>{{ skill.description || t('未填写技能描述') }}</p>
      </div>
      <div v-if="skill.scenario" class="summary-row">
        <span class="summary-label">{{ t('使用场景') }}</span>
        <p>{{ skill.scenario }}</p>
      </div>
    </section>

    <n-descriptions bordered :column="1" label-placement="left">
      <n-descriptions-item :label="t('类型')">{{ typeLabel }}</n-descriptions-item>
      <template v-if="skill.package">
        <n-descriptions-item label="Slug">{{ skill.package.slug }}</n-descriptions-item>
        <n-descriptions-item :label="t('版本')">{{ skill.package.version }}</n-descriptions-item>
        <n-descriptions-item :label="t('文件数量')">{{ skill.package.files.length }}</n-descriptions-item>
        <n-descriptions-item label="SHA-256"><span class="digest">{{ skill.package.digest }}</span></n-descriptions-item>
      </template>
    </n-descriptions>

    <section v-if="skill.package?.children?.length" class="children-section">
      <h3>{{ t('内部 Skill（{count}）', { count: skill.package.children.length }) }}</h3>
      <article v-for="child in skill.package.children" :key="child.slug" class="child-card">
        <div class="child-head">
          <strong>{{ child.name || child.slug }}</strong>
          <n-tag size="small" :bordered="false">{{ child.version }}</n-tag>
        </div>
        <p>{{ child.description || t('未填写技能描述') }}</p>
        <span>{{ child.slug }}</span>
      </article>
    </section>

    <n-alert
      v-for="warning in skill.package?.warnings || []"
      :key="warning.code + (warning.tool || '')"
      type="warning"
    >
      {{ localizeSkillInstallWarning(warning) }}
    </n-alert>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import { NAlert, NDescriptions, NDescriptionsItem, NTag } from 'naive-ui';
import type { SkillItem } from '@/api/skills';
import { t } from '@/composables/i18n';
import { localizeSkillInstallWarning } from './skillInstallError';

const props = defineProps<{ skill: SkillItem }>();

const typeLabel = computed(() => {
  if (props.skill.type === 'expert_package') return t('skills.type.expert_package');
  if (props.skill.type === 'ordinary') return t('普通 Skill');
  if (props.skill.type === 'workflow') return t('工作流');
  return t('写作规范');
});
</script>

<style scoped>
.skill-details { display: flex; flex-direction: column; gap: 16px; }
.summary-card { display: grid; gap: 14px; padding: 16px; border: 1px solid #e4eaf4; border-radius: 12px; background: #f8faff; }
.summary-row { display: grid; grid-template-columns: 88px minmax(0, 1fr); gap: 14px; color: #17233d; }
.summary-row p { margin: 0; white-space: pre-wrap; overflow-wrap: anywhere; line-height: 1.7; color: #52627d; }
.summary-label { color: #8491a7; }
.digest { overflow-wrap: anywhere; font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 12px; }
.children-section h3 { margin: 0 0 10px; color: #17233d; font-size: 15px; }
.child-card { margin-top: 10px; padding: 12px 14px; border: 1px solid #e4eaf4; border-radius: 10px; }
.child-head { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
.child-card p { margin: 8px 0 4px; color: #52627d; line-height: 1.6; }
.child-card > span { color: #9aa5b8; font-size: 12px; }
</style>
