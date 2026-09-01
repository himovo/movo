<template>
  <div class="page-stack skills-page">
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
            <n-input v-model:value="filters.keyword" clearable :placeholder="t('搜索技能名称、描述')" class="keyword-input" />
            <n-select v-model:value="filters.type" clearable :options="typeOptions" :placeholder="t('类型')" style="width: 160px" />
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
              {{ t('刷新') }}
            </n-button>
            <n-button type="primary" strong @click="openCreateModal">
              <template #icon>
                <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                  <path d="M5 12h14" />
                  <path d="M12 5v14" />
                </svg>
              </template>
              {{ t('创建 Skill') }}
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
                    {{ row.enabled ? t('已启用') : t('已禁用') }}
                  </n-tag>
                </div>
                <span class="card-time">{{ formatAdminDateTime(row.updatedAt || row.createdAt, t('刚创建')) }}</span>
              </div>

              <div class="card-title">{{ row.name }}</div>
              <div class="card-desc">{{ row.description || t('未填写技能描述') }}</div>

              <div class="card-footrow">
                <div class="card-actions">
                  <div class="card-switch" @click.stop>
                    <span class="card-switch-label">{{ row.enabled ? t('启用中') : t('已禁用') }}</span>
                    <n-switch
                      size="small"
                      :value="row.enabled"
                      :loading="switchingIds.has(row.id)"
                      @update:value="handleEnabledUpdate(row, $event)"
                    />
                  </div>
                  <n-button class="icon-only-btn" size="small" quaternary circle :title="t('编辑基础信息')" @click.stop="openEditModal(row)">
                    <svg viewBox="0 0 24 24" aria-hidden="true">
                      <path d="M12 20h9" />
                      <path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4 12.5-12.5z" />
                    </svg>
                  </n-button>
                  <n-button class="icon-only-btn delete-btn" size="small" quaternary circle :title="t('删除 Skill')" @click.stop="askDelete(row)">
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
            <div class="empty-title">{{ t('暂未创建 Skill') }}</div>
            <div class="empty-desc">{{ t('先创建基础字段，然后点击卡片进入配置页。') }}</div>
            <n-space justify="center">
              <n-button type="primary" @click="openCreateModal">{{ t('创建 Skill') }}</n-button>
            </n-space>
          </div>
        </n-spin>
      </div>
    </n-card>
  </div>

  <n-modal v-model:show="createVisible" preset="card" :title="t('创建 Skill')" style="width: 640px">
    <n-form ref="createFormRef" :model="createForm" :rules="createRules" label-placement="left" label-width="92">
      <n-form-item :label="t('技能名称')" path="name">
        <n-input v-model:value="createForm.name" maxlength="120" :placeholder="t('请输入技能名称')" />
      </n-form-item>
      <n-form-item :label="t('技能描述')" path="description">
        <n-input v-model:value="createForm.description" type="textarea" :rows="3" :placeholder="t('请输入技能描述')" />
      </n-form-item>
      <n-form-item :label="t('使用场景')" path="scenario">
        <n-input v-model:value="createForm.scenario" type="textarea" :rows="3" placeholder="例如：市场周报写作、销售复盘总结" />
      </n-form-item>
      <n-form-item :label="t('类型')" path="type">
        <n-radio-group v-model:value="createForm.type">
          <n-space>
            <n-radio value="writing_style">{{ t('写作规范') }}</n-radio>
            <n-radio value="workflow">{{ t('工作流') }}</n-radio>
          </n-space>
        </n-radio-group>
      </n-form-item>
    </n-form>

    <template #footer>
      <n-space justify="end">
        <n-button @click="createVisible = false">{{ t('取消') }}</n-button>
        <n-button type="primary" :loading="creating" @click="submitCreate">{{ t('创建') }}</n-button>
      </n-space>
    </template>
  </n-modal>

  <n-modal v-model:show="editVisible" preset="card" :title="t('编辑 Skill 基础信息')" style="width: 640px">
    <n-form ref="editFormRef" :model="editForm" :rules="editRules" label-placement="left" label-width="92">
      <n-form-item :label="t('技能名称')" path="name">
        <n-input v-model:value="editForm.name" maxlength="120" :placeholder="t('请输入技能名称')" />
      </n-form-item>
      <n-form-item :label="t('技能描述')" path="description">
        <n-input v-model:value="editForm.description" type="textarea" :rows="3" :placeholder="t('请输入技能描述')" />
      </n-form-item>
      <n-form-item :label="t('使用场景')" path="scenario">
        <n-input v-model:value="editForm.scenario" type="textarea" :rows="3" :placeholder="t('请输入使用场景')" />
      </n-form-item>
      <n-form-item :label="t('类型')">
        <div class="edit-type-value">{{ typeText(editForm.type) }}（{{ t('创建后不可修改') }}）</div>
      </n-form-item>
    </n-form>

    <template #footer>
      <n-space justify="end">
        <n-button @click="editVisible = false">{{ t('取消') }}</n-button>
        <n-button type="primary" :loading="updating" @click="submitEdit">{{ t('保存') }}</n-button>
      </n-space>
    </template>
  </n-modal>

  <n-modal
    v-model:show="deleteConfirmVisible"
    preset="dialog"
    type="warning"
    :title="t('删除 Skill')"
    :positive-text="t('删除')"
    :negative-text="t('取消')"
    :positive-button-props="{ type: 'error', loading: deleting }"
    @positive-click="confirmDelete"
  >
    {{ t('确定删除「{name}」吗？删除后不可恢复。', { name: pendingDeleteRow?.name || t('未命名 Skill') }) }}
  </n-modal>

  <n-modal
    v-model:show="enabledConfirmVisible"
    preset="dialog"
    type="warning"
    :title="pendingEnabledValue ? t('启用 Skill') : t('禁用 Skill')"
    :positive-text="pendingEnabledValue ? t('确认启用') : t('确认禁用')"
    :negative-text="t('取消')"
    :positive-button-props="{ type: pendingEnabledValue ? 'primary' : 'warning', loading: enabledConfirming }"
    @positive-click="confirmEnabledChange"
  >
    {{
      pendingEnabledValue
        ? t('确认启用 Skill「{name}」吗？启用后用户可在可用范围内使用。', { name: pendingEnabledRow?.name || t('未命名 Skill') })
        : t('确认禁用 Skill「{name}」吗？禁用后用户将无法继续使用。', { name: pendingEnabledRow?.name || t('未命名 Skill') })
    }}
  </n-modal>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';
import { useRouter } from 'vue-router';
import { useMessage, type FormInst, type FormRules } from 'naive-ui';
import { t } from '@/composables/i18n';
import { formatAdminDateTime, parseAdminDate } from '@/composables/adminTimezone';
import { createSkill, deleteSkill, fetchSkills, setSkillEnabled, updateSkill, type SkillItem, type SkillPayload, type SkillType } from '@/api/skills';

const router = useRouter();
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
const enabledConfirmVisible = ref(false);
const enabledConfirming = ref(false);
const pendingEnabledRow = ref<SkillItem | null>(null);
const pendingEnabledValue = ref(false);

const filters = ref({
  keyword: '',
  type: null as SkillType | null,
});

const typeOptions = computed(() => [
  { label: t('写作规范'), value: 'writing_style' },
  { label: t('工作流'), value: 'workflow' },
]);

const createRules: FormRules = {
  name: [
    { required: true, message: t('请输入技能名称'), trigger: ['input', 'blur'] },
    { min: 1, max: 120, message: t('技能名称长度需在 1-120 字符'), trigger: ['input', 'blur'] },
  ],
  type: [{ required: true, message: t('请选择技能类型'), trigger: 'change' }],
};
const editRules: FormRules = {
  name: [
    { required: true, message: t('请输入技能名称'), trigger: ['input', 'blur'] },
    { min: 1, max: 120, message: t('技能名称长度需在 1-120 字符'), trigger: ['input', 'blur'] },
  ],
};

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
    { key: 'total', icon: '<svg viewBox="0 0 24 24"><rect x="3" y="3" width="7" height="7" rx="1" /><rect x="14" y="3" width="7" height="7" rx="1" /><rect x="14" y="14" width="7" height="7" rx="1" /><rect x="3" y="14" width="7" height="7" rx="1" /></svg>', label: t('Skill 总数'), value: total, note: t('当前组织下的全部技能') },
    { key: 'writing', icon: '<svg viewBox="0 0 24 24"><path d="M12 20h9" /><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4 12.5-12.5z" /></svg>', label: t('写作规范'), value: writingStyleCount, note: t('类型为写作规范的技能') },
    { key: 'workflow', icon: '<svg viewBox="0 0 24 24"><circle cx="6" cy="19" r="3" /><path d="M9 19h8.5a3.5 3.5 0 0 0 0-7h-11a3.5 3.5 0 0 1 0-7H15" /><circle cx="18" cy="5" r="3" /></svg>', label: t('工作流'), value: workflowCount, note: t('类型为工作流的技能') },
    { key: 'config', icon: '<svg viewBox="0 0 24 24"><path d="M8 3H7a2 2 0 0 0-2 2v5a2 2 0 0 1-2 2 2 2 0 0 1 2 2v5a2 2 0 0 0 2 2h1" /><path d="M16 21h1a2 2 0 0 0 2-2v-5a2 2 0 0 1 2-2 2 2 0 0 1-2-2V5a2 2 0 0 0-2-2h-1" /></svg>', label: t('已配置 JSON'), value: configuredCount, note: t('config 非空的技能数量') },
  ];
});

function typeText(type: SkillType): string {
  return type === 'workflow' ? t('工作流') : t('写作规范');
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
  router.push(`/skills/${skillId}/config`);
}

function askDelete(row: SkillItem) {
  pendingDeleteRow.value = row;
  deleteConfirmVisible.value = true;
}

async function loadRows() {
  loading.value = true;
  try {
    const data = await fetchSkills();
    rows.value = data.sort((a, b) => {
      const timeA = parseAdminDate(a.createdAt || (a as any).created_at)?.getTime() || 0;
      const timeB = parseAdminDate(b.createdAt || (b as any).created_at)?.getTime() || 0;
      if (timeA !== timeB) {
        return timeB - timeA;
      }
      return a.id.localeCompare(b.id);
    });
  } catch (error: any) {
    message.error(error?.response?.data?.detail || t('加载 Skill 失败'));
  } finally {
    loading.value = false;
  }
}

async function submitCreate() {
  await createFormRef.value?.validate();
  creating.value = true;
  try {
    await createSkill({ ...createForm.value, enabled: false });
    message.success(t('Skill 创建成功，默认已禁用'));
    createVisible.value = false;
    await loadRows();
  } catch (error: any) {
    message.error(error?.response?.data?.detail || t('Skill 创建失败'));
  } finally {
    creating.value = false;
  }
}

async function submitEdit() {
  await editFormRef.value?.validate();
  if (!editForm.value.id) return;
  updating.value = true;
  try {
    await updateSkill(editForm.value.id, {
      name: editForm.value.name,
      description: editForm.value.description,
      scenario: editForm.value.scenario,
      type: editForm.value.type,
      config: editForm.value.config || {},
      enabled: editForm.value.enabled,
    });
    message.success(t('Skill 基础信息已更新'));
    editVisible.value = false;
    await loadRows();
  } catch (error: any) {
    message.error(error?.response?.data?.detail || t('Skill 更新失败'));
  } finally {
    updating.value = false;
  }
}

async function confirmDelete() {
  if (!pendingDeleteRow.value) return false;
  deleting.value = true;
  try {
    await deleteSkill(pendingDeleteRow.value.id);
    message.success(t('Skill 已删除'));
    deleteConfirmVisible.value = false;
    pendingDeleteRow.value = null;
    await loadRows();
  } catch (error: any) {
    message.error(error?.response?.data?.detail || t('删除失败'));
    return false;
  } finally {
    deleting.value = false;
  }
  return true;
}

async function toggleEnabled(row: SkillItem, enabled: boolean): Promise<boolean> {
  if (row.enabled === enabled || switchingIds.value.has(row.id)) return false;
  const next = new Set(switchingIds.value);
  next.add(row.id);
  switchingIds.value = next;
  try {
    const updated = await setSkillEnabled(row.id, enabled);
    rows.value = rows.value.map((item) => (item.id === row.id ? updated : item));
    message.success(enabled ? t('Skill 已启用') : t('Skill 已禁用'));
    return true;
  } catch (error: any) {
    message.error(error?.response?.data?.detail || t('状态更新失败'));
    return false;
  } finally {
    const current = new Set(switchingIds.value);
    current.delete(row.id);
    switchingIds.value = current;
  }
}

function handleEnabledUpdate(row: SkillItem, value: boolean) {
  if (row.enabled === value || switchingIds.value.has(row.id)) return;
  pendingEnabledRow.value = row;
  pendingEnabledValue.value = value;
  enabledConfirmVisible.value = true;
}

async function confirmEnabledChange() {
  if (!pendingEnabledRow.value) return false;
  enabledConfirming.value = true;
  try {
    const ok = await toggleEnabled(pendingEnabledRow.value, pendingEnabledValue.value);
    if (!ok) return false;
    enabledConfirmVisible.value = false;
    pendingEnabledRow.value = null;
  } catch {
    return false;
  } finally {
    enabledConfirming.value = false;
  }
  return true;
}

onMounted(loadRows);
</script>

<style scoped>
.skills-page {
  height: calc(100vh - 92px);
  min-height: 0;
  display: flex;
  flex-direction: column;
  gap: 16px;
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
  padding: 12px;
}

.metric-card,
.list-card {
  border-radius: 8px;
}

.list-card {
  width: calc(100% - 24px);
  margin: -16px 12px 0;
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
  font-weight: 700;
  font-size: 12px;
}

.empty-title {
  color: #101c3d;
  font-size: 24px;
  line-height: 1.2;
  font-weight: 800;
}

.empty-desc {
  color: #65748c;
  font-size: 14px;
}

.edit-type-value {
  width: 100%;
  min-height: 34px;
  border: 1px solid #dbe4f4;
  border-radius: 8px;
  background: #f7faff;
  color: #51617e;
  display: flex;
  align-items: center;
  padding: 0 12px;
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
