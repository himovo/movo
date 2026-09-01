<template>
  <div class="page-stack skills-page">
    <header class="skills-header">
      <div class="skills-header-left">
        <n-button secondary @click="emit('back')">
          <template #icon><n-icon><ArrowBackOutline /></n-icon></template>
          {{ t('skills.back_to_chat') }}
        </n-button>
        <h1>{{ t('skills.title') }}</h1>
      </div>
    </header>

    <div class="metrics-row">
      <n-card v-for="item in metricCards" :key="item.key" class="metric-card" :bordered="false" size="small">
        <div class="metric-main">
          <span class="metric-icon" :class="`metric-icon-${item.key}`" v-html="item.icon"></span>
          <div class="metric-body">
            <div class="metric-label">{{ item.label }}</div>
            <div class="metric-value">{{ item.value }}</div>
          </div>
        </div>
        <div class="metric-note">{{ item.note }}</div>
      </n-card>
    </div>

    <n-card class="list-card shell-card" :bordered="false" size="large">
      <div class="list-filter-row">
        <div class="filter-toolbar">
          <n-space align="center" :size="10" class="filter-left">
            <n-input v-model:value="filters.keyword" clearable :placeholder="t('skills.search_placeholder')" class="keyword-input" />
            <n-select v-model:value="filters.type" clearable :options="typeOptions" :placeholder="t('ui.type')" style="width: 160px" />
          </n-space>
          <n-space :size="10" class="filter-right">
            <n-button secondary @click="loadRows">
              <template #icon>
                <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                  <path d="M21 12a9 9 0 0 0-9-9 9.75 9.75 0 0 0-6.74 2.74L3 8" />
                  <path d="M3 3v5h5" />
                  <path d="M3 12a9 9 0 0 0 9 9 9.75 9.75 0 0 0 6.74-2.74L21 16" />
                  <path d="M16 16h5v5" />
                </svg>
              </template>
              {{ t('ui.refresh') }}
            </n-button>
            <n-button type="primary" strong @click="openCreateModal">
              <template #icon>
                <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                  <path d="M5 12h14" />
                  <path d="M12 5v14" />
                </svg>
              </template>
              {{ t('skills.btn_create') }}
            </n-button>
          </n-space>
        </div>
      </div>

      <div class="list-body">
        <n-spin :show="loading">
          <div v-if="filteredRows.length" class="skill-grid">
            <button
              v-for="row in filteredRows"
              :key="row.id"
              class="skill-card"
              :class="{ 'skill-card-disabled': !row.enabled }"
              type="button"
              @click="goToConfig(row.id)"
            >
              <div class="card-head">
                <div class="card-tags">
                  <n-tag size="small" :bordered="false" :type="row.type === 'workflow' ? 'warning' : 'info'">
                    {{ typeText(row.type) }}
                  </n-tag>
                  <n-tag size="small" :bordered="false" :type="row.enabled ? 'success' : 'default'">
                    {{ row.enabled ? t('skills.enabled') : t('skills.disabled') }}
                  </n-tag>
                </div>
                <span class="card-time">{{ formatAppDateTime(row.updatedAt || row.createdAt, t('skills.just_created')) }}</span>
              </div>

              <div class="card-title">{{ row.name }}</div>
              <div class="card-desc">{{ row.description || t('skills.no_desc') }}</div>

              <div class="card-footrow">
                <div class="card-actions">
                  <div class="card-switch" @click.stop>
                    <span class="card-switch-label">{{ row.enabled ? t('skills.enabled') : t('skills.disabled') }}</span>
                    <n-switch
                      size="small"
                      :value="row.enabled"
                      :loading="switchingIds.has(row.id)"
                      @update:value="handleEnabledUpdate(row, $event)"
                    />
                  </div>
                  <n-button class="icon-only-btn" size="small" quaternary circle :title="t('skills.edit_info')" @click.stop="openEditModal(row)">
                    <svg viewBox="0 0 24 24" aria-hidden="true">
                      <path d="M12 20h9" />
                      <path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4 12.5-12.5z" />
                    </svg>
                  </n-button>
                  <n-button class="icon-only-btn delete-btn" size="small" quaternary circle :title="t('skills.delete_skill')" @click.stop="askDelete(row)">
                    <svg viewBox="0 0 24 24" aria-hidden="true">
                      <path d="M3 6h18" />
                      <path d="M8 6V4h8v2" />
                      <path d="M6 6l1 14h10l1-14" />
                      <path d="M10 11v6" />
                      <path d="M14 11v6" />
                    </svg>
                  </n-button>
                </div>
              </div>
            </button>
          </div>

          <div v-else class="empty-shell">
            <div class="empty-visual">
              <span>SKILL</span>
              <span>JSON</span>
              <span>CFG</span>
            </div>
            <div class="empty-title">{{ t('skills.no_skills') }}</div>
            <div class="empty-desc">{{ t('skills.empty_hint') }}</div>
            <n-space justify="center">
              <n-button type="primary" @click="openCreateModal">{{ t('skills.btn_create') }}</n-button>
            </n-space>
          </div>
        </n-spin>
      </div>
    </n-card>
  </div>

  <n-modal v-model:show="createVisible" preset="card" :title="t('skills.btn_create')" style="width: 640px">
    <n-form ref="createFormRef" :model="createForm" :rules="createRules" label-placement="left" label-width="92">
      <n-form-item :label="t('app.skill_form.skill_name')" path="name">
        <n-input v-model:value="createForm.name" maxlength="120" :placeholder="t('app.skill_form.skill_name_placeholder')" />
      </n-form-item>
      <n-form-item :label="t('app.skill_form.short_summary')" path="description">
        <n-input v-model:value="createForm.description" type="textarea" :rows="3" :placeholder="t('app.skill_form.short_summary_placeholder')" />
      </n-form-item>
      <n-form-item :label="t('app.skill_form.applicable_scenarios')" path="scenario">
        <n-input v-model:value="createForm.scenario" type="textarea" :rows="3" :placeholder="t('app.skill_form.scenario_placeholder')" />
      </n-form-item>
      <n-form-item :label="t('ui.type')" path="type">
        <n-radio-group v-model:value="createForm.type">
          <n-space>
            <n-radio value="writing_style">{{ t('skills.type.style') }}</n-radio>
            <n-radio value="workflow">{{ t('skills.type.workflow') }}</n-radio>
          </n-space>
        </n-radio-group>
      </n-form-item>
    </n-form>

    <template #footer>
      <n-space justify="end">
        <n-button @click="createVisible = false">{{ t('ui.cancel') }}</n-button>
        <n-button type="primary" :loading="creating" @click="submitCreate">{{ t('ui.create') }}</n-button>
      </n-space>
    </template>
  </n-modal>

  <n-modal v-model:show="editVisible" preset="card" :title="t('skills.edit_title')" style="width: 640px">
    <n-form ref="editFormRef" :model="editForm" :rules="editRules" label-placement="left" label-width="92">
      <n-form-item :label="t('app.skill_form.skill_name')" path="name">
        <n-input v-model:value="editForm.name" maxlength="120" :placeholder="t('app.skill_form.skill_name_placeholder')" />
      </n-form-item>
      <n-form-item :label="t('app.skill_form.short_summary')" path="description">
        <n-input v-model:value="editForm.description" type="textarea" :rows="3" :placeholder="t('app.skill_form.short_summary_placeholder')" />
      </n-form-item>
      <n-form-item :label="t('app.skill_form.applicable_scenarios')" path="scenario">
        <n-input v-model:value="editForm.scenario" type="textarea" :rows="3" :placeholder="t('app.skill_form.scenario_placeholder')" />
      </n-form-item>
      <n-form-item :label="t('ui.type')">
        <div class="edit-type-value">{{ typeText(editForm.type) }}{{ t('skills.immutable_after_create') }}</div>
      </n-form-item>
    </n-form>

    <template #footer>
      <n-space justify="end">
        <n-button @click="editVisible = false">{{ t('ui.cancel') }}</n-button>
        <n-button type="primary" :loading="updating" @click="submitEdit">{{ t('ui.save') }}</n-button>
      </n-space>
    </template>
  </n-modal>

  <n-modal
    v-model:show="deleteConfirmVisible"
    preset="dialog"
    type="warning"
    :title="t('skills.delete_skill')"
    :positive-text="t('ui.delete')"
    :negative-text="t('ui.cancel')"
    :positive-button-props="{ type: 'error', loading: deleting }"
    @positive-click="confirmDelete"
  >
    {{ t('skills.delete_confirm_desc', { name: pendingDeleteRow?.name || 'Skill' }) }}
  </n-modal>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue';
import {
  NButton,
  NCard,
  NForm,
  NFormItem,
  NIcon,
  NInput,
  NModal,
  NRadio,
  NRadioGroup,
  NSelect,
  NSpace,
  NSpin,
  NSwitch,
  NTag,
  useMessage,
  type FormInst,
  type FormRules,
} from 'naive-ui';
import { ArrowBackOutline } from '@vicons/ionicons5';
import { createSkill, deleteSkill, fetchSkills, setSkillEnabled, updateSkill, type SkillItem, type SkillPayload, type SkillType } from '../api/skills';
import { t } from '../composables/i18n';
import { formatAppDateTime, parseAppDate } from '../composables/appTimezone';

const props = defineProps<{
  userId: string | null
  mainId: string
}>();

const emit = defineEmits<{
  back: []
  configure: [skill: SkillItem]
}>();

const message = useMessage();

const loading = ref(false);
const creating = ref(false);
const updating = ref(false);
const deleting = ref(false);
const rows = ref<SkillItem[]>([]);
const switchingIds = ref<Set<string>>(new Set());

const createVisible = ref(false);
const createFormRef = ref<FormInst | null>(null);
const createForm = ref<SkillPayload>({
  name: '',
  description: '',
  scenario: '',
  type: 'writing_style',
  config: {},
  enabled: false,
});
const editVisible = ref(false);
const editFormRef = ref<FormInst | null>(null);
const editForm = ref<{
  id: string;
  name: string;
  description: string;
  scenario: string;
  type: SkillType;
  config: Record<string, any>;
  enabled: boolean;
}>({
  id: '',
  name: '',
  description: '',
  scenario: '',
  type: 'writing_style',
  config: {},
  enabled: true,
});
const deleteConfirmVisible = ref(false);
const pendingDeleteRow = ref<SkillItem | null>(null);

const filters = ref({
  keyword: '',
  type: null as SkillType | null,
});

const typeOptions = computed(() => [
  { label: t('skills.type.style'), value: 'writing_style' },
  { label: t('skills.type.workflow'), value: 'workflow' },
]);

const createRules = computed<FormRules>(() => ({
  name: [
    { required: true, message: t('app.skill_form.skill_name_placeholder'), trigger: ['input', 'blur'] },
    { min: 1, max: 120, message: t('skills.name_length'), trigger: ['input', 'blur'] },
  ],
  type: [{ required: true, message: t('skills.select_type'), trigger: 'change' }],
}));

const editRules = computed<FormRules>(() => ({
  name: [
    { required: true, message: t('app.skill_form.skill_name_placeholder'), trigger: ['input', 'blur'] },
    { min: 1, max: 120, message: t('skills.name_length'), trigger: ['input', 'blur'] },
  ],
}));

const filteredRows = computed(() => {
  const keyword = filters.value.keyword.trim().toLowerCase();
  return rows.value.filter((row) => {
    const keywordHit = !keyword
      || row.name.toLowerCase().includes(keyword)
      || row.description.toLowerCase().includes(keyword)
      || row.scenario.toLowerCase().includes(keyword);
    const typeHit = !filters.value.type || row.type === filters.value.type;
    return keywordHit && typeHit;
  });
});

const metricCards = computed(() => {
  const total = rows.value.length;
  const writingStyleCount = rows.value.filter((item) => item.type === 'writing_style').length;
  const workflowCount = rows.value.filter((item) => item.type === 'workflow').length;
  const configuredCount = rows.value.filter((item) => Object.keys(item.config || {}).length > 0).length;
  return [
    { key: 'total', icon: '<svg viewBox="0 0 24 24"><rect x="3" y="3" width="7" height="7" rx="1" /><rect x="14" y="3" width="7" height="7" rx="1" /><rect x="14" y="14" width="7" height="7" rx="1" /><rect x="3" y="14" width="7" height="7" rx="1" /></svg>', label: t('skills.title'), value: total, note: t('skills.list_title') },
    { key: 'writing', icon: '<svg viewBox="0 0 24 24"><path d="M12 20h9" /><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4 12.5-12.5z" /></svg>', label: t('skills.type.style'), value: writingStyleCount, note: t('skills.type.style') },
    { key: 'workflow', icon: '<svg viewBox="0 0 24 24"><circle cx="6" cy="19" r="3" /><path d="M9 19h8.5a3.5 3.5 0 0 0 0-7h-11a3.5 3.5 0 0 1 0-7H15" /><circle cx="18" cy="5" r="3" /></svg>', label: t('skills.type.workflow'), value: workflowCount, note: t('skills.type.workflow') },
    { key: 'config', icon: '<svg viewBox="0 0 24 24"><path d="M8 3H7a2 2 0 0 0-2 2v5a2 2 0 0 1-2 2 2 2 0 0 1 2 2v5a2 2 0 0 0 2 2h1" /><path d="M16 21h1a2 2 0 0 0 2-2v-5a2 2 0 0 1 2-2 2 2 0 0 1-2-2V5a2 2 0 0 0-2-2h-1" /></svg>', label: t('skills.resource.custom_tools'), value: configuredCount, note: t('skills.resource.custom_tools') },
  ];
});

function typeText(type: SkillType): string {
  return type === 'workflow' ? t('skills.type.workflow') : t('skills.type.style');
}

function resetCreateForm() {
  createForm.value = {
    name: '',
    description: '',
    scenario: '',
    type: 'writing_style',
    config: {},
    enabled: false,
  };
}

function openCreateModal() {
  resetCreateForm();
  createVisible.value = true;
}

function openEditModal(row: SkillItem) {
  editForm.value = {
    id: row.id,
    name: row.name,
    description: row.description,
    scenario: row.scenario,
    type: row.type,
    config: row.config || {},
    enabled: row.enabled !== false,
  };
  editVisible.value = true;
}

function goToConfig(skillId: string) {
  const row = rows.value.find((item) => item.id === skillId);
  if (row) emit('configure', row);
}

function askDelete(row: SkillItem) {
  pendingDeleteRow.value = row;
  deleteConfirmVisible.value = true;
}

async function loadRows() {
  if (!props.userId) {
    rows.value = [];
    return;
  }
  loading.value = true;
  try {
    const data = await fetchSkills(props.userId, props.mainId);
    rows.value = data.sort((a, b) => {
      const timeA = parseAppDate(a.createdAt || (a as any).created_at)?.getTime() || 0;
      const timeB = parseAppDate(b.createdAt || (b as any).created_at)?.getTime() || 0;
      if (timeA !== timeB) {
        return timeB - timeA;
      }
      return a.id.localeCompare(b.id);
    });
  } catch (error: any) {
    message.error(error?.response?.data?.detail || t('skills.msg_loading_failed'));
  } finally {
    loading.value = false;
  }
}

async function submitCreate() {
  await createFormRef.value?.validate();
  if (!props.userId) {
    message.warning(t('skills.msg_login_first'));
    return;
  }
  creating.value = true;
  try {
    await createSkill(props.userId, props.mainId, createForm.value);
    message.success(t('skills.msg_create_disabled_success'));
    createVisible.value = false;
    await loadRows();
  } catch (error: any) {
    message.error(error?.response?.data?.detail || t('skills.msg_create_failed'));
  } finally {
    creating.value = false;
  }
}

async function submitEdit() {
  await editFormRef.value?.validate();
  if (!editForm.value.id || !props.userId) return;
  updating.value = true;
  try {
    await updateSkill(editForm.value.id, props.userId, props.mainId, {
      name: editForm.value.name,
      description: editForm.value.description,
      scenario: editForm.value.scenario,
      type: editForm.value.type,
      config: editForm.value.config || {},
      enabled: editForm.value.enabled,
    });
    message.success(t('skills.msg_update_success'));
    editVisible.value = false;
    await loadRows();
  } catch (error: any) {
    message.error(error?.response?.data?.detail || t('skills.msg_update_failed'));
  } finally {
    updating.value = false;
  }
}

async function confirmDelete() {
  if (!pendingDeleteRow.value || !props.userId) return false;
  deleting.value = true;
  try {
    await deleteSkill(pendingDeleteRow.value.id, props.userId, props.mainId);
    message.success(t('skills.msg_delete_success'));
    deleteConfirmVisible.value = false;
    pendingDeleteRow.value = null;
    await loadRows();
  } catch (error: any) {
    message.error(error?.response?.data?.detail || t('skills.msg_delete_failed'));
    return false;
  } finally {
    deleting.value = false;
  }
  return true;
}

async function toggleEnabled(row: SkillItem, enabled: boolean) {
  if (row.enabled === enabled || switchingIds.value.has(row.id) || !props.userId) return;
  const next = new Set(switchingIds.value);
  next.add(row.id);
  switchingIds.value = next;
  try {
    const updated = await setSkillEnabled(row.id, props.userId, props.mainId, enabled);
    rows.value = rows.value.map((item) => (item.id === row.id ? updated : item));
    message.success(enabled ? t('skills.msg_enabled_success') : t('skills.msg_disabled_success'));
  } catch (error: any) {
    message.error(
      error?.response?.data?.detail
      || (enabled ? t('skills.msg_enable_failed') : t('skills.msg_disable_failed')),
    );
  } finally {
    const current = new Set(switchingIds.value);
    current.delete(row.id);
    switchingIds.value = current;
  }
}

function handleEnabledUpdate(row: SkillItem, value: boolean) {
  void toggleEnabled(row, value);
}

onMounted(loadRows);
watch(() => [props.userId, props.mainId], () => {
  void loadRows();
});
</script>

<style scoped>
.skills-page {
  height: 100%;
  min-height: 0;
  display: flex;
  flex-direction: column;
  gap: 16px;
  background: #f6f8fc;
  padding: 12px;
}

.skills-header {
  width: 100%;
  padding: 14px 18px;
  border: 1px solid #e6ebf5;
  border-radius: 8px;
  background: #fff;
  box-shadow: 0 4px 12px rgba(29, 54, 110, 0.04);
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}

.skills-header h1 {
  margin: 0;
  color: #101c3d;
  font-size: 20px;
  line-height: 1.2;
  font-weight: 800;
}

.skills-header-left {
  display: flex;
  align-items: center;
  gap: 12px;
}

.shell-card {
  border-radius: 14px;
  border: 1px solid #e6ebf5;
  background: #fff;
  box-shadow: 0 6px 20px rgba(16, 38, 84, 0.05);
}

.metrics-row {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
}

.metric-card,
.list-card {
  border-radius: 8px;
}

.list-card {
  width: 100%;
  margin: 0;
  flex: 1;
  min-height: 0;
  overflow: hidden;
}

.list-card :deep(.n-card__content) {
  height: 100%;
  display: flex;
  flex-direction: column;
}

.metric-card {
  border: 1px solid #e6ebf5;
  background: #fff;
  box-shadow: 0 4px 12px rgba(29, 54, 110, 0.04);
}

.metric-main {
  display: flex;
  align-items: flex-start;
  gap: 12px;
}

.metric-body {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.metric-icon {
  width: 44px;
  height: 44px;
  border-radius: 50%;
  display: grid;
  place-items: center;
  font-size: 13px;
  font-weight: 700;
}

.metric-icon :deep(svg) {
  width: 20px;
  height: 20px;
  fill: none;
  stroke: currentColor;
  stroke-width: 2;
  stroke-linecap: round;
  stroke-linejoin: round;
}

.metric-icon-total {
  color: #2d63ff;
  background: #eaf0ff;
}

.metric-icon-writing {
  color: #0f9964;
  background: #e8f8ef;
}

.metric-icon-workflow {
  color: #d9860a;
  background: #fff2df;
}

.metric-icon-config {
  color: #7456e0;
  background: #f0ebff;
}

.metric-label {
  color: #606f8a;
  font-size: 12px;
  line-height: 1.3;
}

.metric-value {
  color: #0f1f45;
  font-size: 24px;
  font-weight: 600;
  line-height: 1.1;
}

.metric-note {
  margin-top: 6px;
  color: #708099;
  font-size: 12px;
}

.filter-toolbar {
  align-items: center;
  display: flex;
  justify-content: space-between;
  gap: 14px;
}

.filter-left {
  flex-wrap: wrap;
}

.keyword-input {
  width: 360px;
}

.filter-right {
  flex-wrap: wrap;
}

.list-filter-row {
  padding: 0 44px 12px;
  margin: 0 -44px 12px;
  border-bottom: 1px solid #edf1f7;
}

.list-body {
  flex: 1;
  min-height: 0;
  overflow: auto;
}

.skill-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
  gap: 12px;
}

.skill-card {
  min-height: 188px;
  padding: 14px;
  border: 1px solid rgba(28, 45, 82, 0.08);
  border-radius: 8px;
  background: #fff;
  box-shadow:
    0 8px 18px rgba(15, 31, 69, 0.06),
    0 1px 2px rgba(15, 31, 69, 0.04);
  display: flex;
  flex-direction: column;
  gap: 10px;
  text-align: left;
  cursor: pointer;
  transition:
    border-color 0.2s ease,
    box-shadow 0.2s ease,
    transform 0.2s ease;
}

.skill-card:hover {
  border-color: rgba(54, 106, 255, 0.36);
  box-shadow:
    0 14px 34px rgba(33, 58, 126, 0.14),
    0 4px 10px rgba(33, 58, 126, 0.08);
  transform: translateY(-2px);
}

.card-head,
.card-footrow {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}

.card-tags {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}

.card-time {
  color: #7a8797;
  font-size: 12px;
}

.card-title {
  color: #17233d;
  font-size: 16px;
  font-weight: 800;
}

.card-desc {
  color: #5f6f85;
  font-size: 13px;
  line-height: 1.55;
  display: -webkit-box;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 3;
  overflow: hidden;
}

.card-footrow {
  margin-top: auto;
  display: flex;
  justify-content: flex-end;
}

.card-actions {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  margin-left: auto;
}

.card-switch {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 4px 10px;
  border-radius: 999px;
  background: #f6f9ff;
  border: 1px solid #e3ebfb;
}

.card-switch-label {
  color: #4a5d7c;
  font-size: 12px;
  line-height: 1;
}

.icon-only-btn :deep(svg) {
  width: 15px;
  height: 15px;
  fill: none;
  stroke: currentColor;
  stroke-width: 2;
  stroke-linecap: round;
  stroke-linejoin: round;
}

.delete-btn:hover {
  color: #d03050;
}

.skill-card-disabled {
  background: linear-gradient(180deg, #fbfcfe, #f6f8fc);
  border-color: rgba(28, 45, 82, 0.06);
}

.skill-card-disabled .card-title,
.skill-card-disabled .card-desc,
.skill-card-disabled .card-time {
  opacity: 0.72;
}

.empty-shell {
  min-height: 320px;
  border: 1px dashed #d8e2f2;
  border-radius: 12px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  text-align: center;
  background: linear-gradient(180deg, #fbfdff, #fff);
}

.empty-visual {
  display: flex;
  gap: 8px;
}

.empty-visual span {
  width: 54px;
  height: 36px;
  border-radius: 10px;
  border: 1px solid #d8e2f2;
  background: #fff;
  color: #2d63ff;
  display: grid;
  place-items: center;
  font-size: 11px;
  font-weight: 700;
  box-shadow: 0 4px 10px rgba(45, 99, 255, 0.06);
}

.empty-visual span:nth-child(2) {
  transform: translateY(-4px);
  border-color: #cbd8ef;
  color: #7456e0;
}

.empty-title {
  color: #1a2744;
  font-size: 15px;
  font-weight: 700;
}

.empty-desc {
  color: #6c7c94;
  font-size: 13px;
  margin-bottom: 4px;
}

.edit-type-value {
  color: #738096;
  font-size: 13px;
}

@media (max-width: 1200px) {
  .metrics-row,
  .skill-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 768px) {
  .metrics-row,
  .skill-grid {
    grid-template-columns: minmax(0, 1fr);
  }

  .filter-toolbar {
    flex-direction: column;
    align-items: stretch;
  }

  .keyword-input {
    width: 100%;
  }
}
</style>
