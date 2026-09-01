<script setup lang="ts">
import { t } from '@/composables/i18n';
import { computed, h, onMounted, ref } from 'vue';
import { NSpace, NTag, useDialog, useMessage, type DataTableColumns } from 'naive-ui';
import PageIntro from '@/components/PageIntro.vue';
import RoleCapabilityEditor from './RoleCapabilityEditor.vue';
import {
  copyPositionRole, createPositionRole, deletePositionRole, listPositionRoles, roleResourceCatalog,
  setPositionRoleEnabled, updatePositionRole,
  type PositionRole, type PositionRoleDraft, type RoleResource,
} from '@/api/positionRoles';

const message = useMessage();
const dialog = useDialog();
const loading = ref(false);
const saving = ref(false);
const roles = ref<PositionRole[]>([]);
const tools = ref<RoleResource[]>([]);
const skills = ref<RoleResource[]>([]);
const editorVisible = ref(false);
const editing = ref<PositionRole | null>(null);

const emptyDraft = (): PositionRoleDraft => ({
  name: '', description: '', status: 'active',
  capabilities: { content_generation: true, image_generation: false, code_generation: false, browser_automation: false, internal_knowledge: true },
  toolAccessMode: 'selected', toolIds: [], skillAccessMode: 'selected', skillIds: [],
});
const draft = ref<PositionRoleDraft>(emptyDraft());

const enabledSummary = computed(() => Object.entries(draft.value.capabilities).filter(([, value]) => value).length);

async function load() {
  loading.value = true;
  try {
    const [roleRows, resources] = await Promise.all([listPositionRoles(), roleResourceCatalog()]);
    roles.value = roleRows;
    tools.value = resources.tools;
    skills.value = resources.skills;
  } finally { loading.value = false; }
}

function openCreate() { editing.value = null; draft.value = emptyDraft(); editorVisible.value = true; }
function openEdit(role: PositionRole) {
  editing.value = role;
  draft.value = { name: role.name, description: role.description, status: role.status, capabilities: { ...role.capabilities }, toolAccessMode: role.toolAccessMode, toolIds: [...role.toolIds], skillAccessMode: role.skillAccessMode, skillIds: [...role.skillIds] };
  editorVisible.value = true;
}
async function save() {
  if (!draft.value.name.trim()) return message.warning(t('请输入岗位角色名称'));
  saving.value = true;
  try {
    if (editing.value) await updatePositionRole(editing.value.id, draft.value); else await createPositionRole(draft.value);
    editorVisible.value = false; message.success(t('用户岗位角色已保存')); await load();
  } catch (error: any) { message.error(error?.response?.data?.detail || error?.message || t('保存失败')); }
  finally { saving.value = false; }
}
async function copyRole(role: PositionRole) {
  try { await copyPositionRole(role.id, t('{name} 副本', { name: role.name })); message.success(t('岗位角色已复制')); await load(); }
  catch (error: any) { message.error(error?.response?.data?.detail || t('复制失败')); }
}
function removeRole(role: PositionRole) {
  dialog.warning({ title: '删除用户岗位角色', content: `确认删除“${role.name}”吗？`, positiveText: t('删除'), negativeText: t('取消'), async onPositiveClick() { try { await deletePositionRole(role.id); message.success('已删除'); await load(); } catch (error: any) { message.error(error?.response?.data?.detail || t('删除失败')); } } });
}
async function toggle(role: PositionRole, enabled: boolean) {
  if (!enabled && role.memberCount > 0) {
    dialog.warning({
      title: t('停用用户岗位角色'),
      content: t('“{name}”仍绑定 {count} 名员工。停用后这些员工将不能继续获得该岗位能力，建议先分配替代岗位。', { name: role.name, count: role.memberCount }),
      positiveText: '仍然停用', negativeText: t('取消'),
      onPositiveClick: () => applyRoleStatus(role, enabled),
    });
    return;
  }
  await applyRoleStatus(role, enabled);
}

async function applyRoleStatus(role: PositionRole, enabled: boolean) {
  try { await setPositionRoleEnabled(role.id, enabled); await load(); }
  catch (error: any) { message.error(error?.response?.data?.detail || t('状态更新失败')); }
}

const labels: Record<string, string> = { content_generation: t('内容'), image_generation: t('图片'), code_generation: t('代码'), browser_automation: t('浏览器'), internal_knowledge: t('知识') };
const columns: DataTableColumns<PositionRole> = [
  { title: t('岗位角色'), key: 'name', render: row => h('div', { class: 'role-name' }, [h('strong', row.name), row.protected ? h(NTag, { size: 'small', type: 'info', bordered: false }, { default: () => t('系统保障') }) : null, h('small', row.description || t('暂无说明'))]) },
  { title: t('已启用能力'), key: 'capabilities', render: row => h(NSpace, { size: 6 }, { default: () => Object.entries(row.capabilities).filter(([, enabled]) => enabled).map(([key]) => h(NTag, { size: 'small', bordered: false }, { default: () => labels[key] })) }) },
  { title: t('资源范围'), key: 'resources', render: row => `${row.toolAccessMode === 'all' ? t('全部工具') : t('{count} 个工具', { count: row.toolIds.length })} · ${row.skillAccessMode === 'all' ? t('全部 Skill') : t('{count} 个 Skill', { count: row.skillIds.length })}` },
  { title: t('员工'), key: 'memberCount', width: 80 },
  { title: t('状态'), key: 'status', width: 100, render: row => h(NTag, { type: row.status === 'active' ? 'success' : 'default', bordered: false }, { default: () => row.status === 'active' ? t('启用') : t('停用') }) },
  { title: t('操作'), key: 'actions', width: 300, render: row => h('div', { class: 'action-row' }, [
    h('button', { class: 'action-link', disabled: row.protected, onClick: () => openEdit(row) }, t('编辑')),
    h('button', { class: 'action-link', onClick: () => copyRole(row) }, t('复制')),
    h('button', { class: row.status === 'active' ? 'action-link danger' : 'action-link', disabled: row.protected, onClick: () => toggle(row, row.status !== 'active') }, row.status === 'active' ? t('停用') : t('启用')),
    h('button', { class: 'action-link danger', disabled: row.protected, onClick: () => removeRole(row) }, t('删除')),
  ]) },
];

onMounted(load);
</script>

<template>
  <div class="page-stack position-role-page">
    <n-card class="position-role-card" :bordered="false" size="large">
      <div class="position-role-content">
        <div class="page-head"><PageIntro :title="t('用户岗位角色')" :description="t('按员工职责配置可见且可执行的 Agent 能力。')" /><n-button type="primary" @click="openCreate">创建用户岗位角色</n-button></div>
        <div class="role-table-card"><n-data-table :columns="columns" :data="roles" :loading="loading" :bordered="false" /></div>
      </div>
    </n-card>
    <n-drawer v-model:show="editorVisible" :width="720" placement="right">
      <n-drawer-content :title="editing ? `编辑 ${editing.name}` : t('创建用户岗位角色')" closable>
        <n-form :model="draft" label-placement="top">
          <n-grid :cols="2" :x-gap="14"><n-grid-item><n-form-item :label="t('用户岗位角色名称')" required><n-input v-model:value="draft.name" /></n-form-item></n-grid-item><n-grid-item><n-form-item :label="t('状态')"><n-select v-model:value="draft.status" :options="[{ label: t('启用'), value: 'active' }, { label: t('停用'), value: 'disabled' }]" /></n-form-item></n-grid-item></n-grid>
          <n-form-item :label="t('说明')"><n-input v-model:value="draft.description" type="textarea" :rows="2" /></n-form-item>
          <RoleCapabilityEditor v-model="draft" :tools="tools" :skills="skills" />
        </n-form>
        <template #footer><div class="drawer-footer"><span>{{ t('已启用 {count} 项基础能力', { count: enabledSummary }) }}</span><n-space><n-button @click="editorVisible = false">{{ t('取消') }}</n-button><n-button type="primary" :loading="saving" @click="save">{{ t('保存') }}</n-button></n-space></div></template>
      </n-drawer-content>
    </n-drawer>
  </div>
</template>

<style scoped>
.position-role-page { min-height: calc(100vh - 98px); }
.position-role-card { min-width: 0; border-radius: 8px; }
.position-role-content { display: grid; gap: 16px; min-width: 0; }
.page-head { display: flex; align-items: center; justify-content: space-between; gap: 20px; }
.role-table-card { overflow: hidden; border: 1px solid #edf0f5; border-radius: 10px; }
.role-name { display: grid; grid-template-columns: max-content max-content; align-items: center; gap: 4px 8px; }
.role-name small { grid-column: 1 / -1; color: #667085; font-weight: 400; }
.drawer-footer { min-width: 670px; display: flex; align-items: center; justify-content: space-between; color: #667085; }
@media (max-width: 860px) { .page-head { align-items: flex-start; flex-direction: column; } }
</style>
