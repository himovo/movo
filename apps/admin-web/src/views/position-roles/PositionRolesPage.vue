<script setup lang="ts">
import { t } from '@/composables/i18n';
import { computed, h, onMounted, ref } from 'vue';
import { NSpace, NTag, useDialog, useMessage, type DataTableColumns } from 'naive-ui';
import PageIntro from '@/components/PageIntro.vue';
import RoleCapabilityEditor from './RoleCapabilityEditor.vue';
import {
  copyPositionRole, createPositionRole, deletePositionRole, listPositionRoles,
  setPositionRoleEnabled, updatePositionRole,
  type PositionRole, type PositionRoleDraft,
} from '@/api/positionRoles';

const message = useMessage();
const dialog = useDialog();
const loading = ref(false);
const saving = ref(false);
const roles = ref<PositionRole[]>([]);
const editorVisible = ref(false);
const editing = ref<PositionRole | null>(null);

const emptyDraft = (): PositionRoleDraft => ({
  name: '', description: '', status: 'active',
  capabilities: { content_generation: true, image_generation: false, code_generation: false, browser_automation: false, internal_knowledge: true },
});
const draft = ref<PositionRoleDraft>(emptyDraft());

const enabledSummary = computed(() => Object.entries(draft.value.capabilities).filter(([, value]) => value).length);

async function load() {
  loading.value = true;
  try {
    roles.value = await listPositionRoles();
  } finally { loading.value = false; }
}

function openCreate() { editing.value = null; draft.value = emptyDraft(); editorVisible.value = true; }
function openEdit(role: PositionRole) {
  editing.value = role;
  draft.value = { name: role.name, description: role.description, status: role.status, capabilities: { ...role.capabilities } };
  editorVisible.value = true;
}
async function save() {
  if (!draft.value.name.trim()) return message.warning(t('legacy.enter_a_position_role_name'));
  saving.value = true;
  try {
    if (editing.value) await updatePositionRole(editing.value.id, draft.value); else await createPositionRole(draft.value);
    editorVisible.value = false; message.success(t('legacy.position_role_saved')); await load();
  } catch (error: any) { message.error(error?.response?.data?.detail || error?.message || t('legacy.failed_to_save')); }
  finally { saving.value = false; }
}
async function copyRole(role: PositionRole) {
  try { await copyPositionRole(role.id, t('legacy.copy_9cb84a1', { name: role.name })); message.success(t('legacy.position_role_copied')); await load(); }
  catch (error: any) { message.error(error?.response?.data?.detail || t('legacy.copy_failed')); }
}
function removeRole(role: PositionRole) {
  dialog.warning({ title: t('legacy.delete_position_role'), content: t('legacy.delete_the_position_role', { name: role.name }), positiveText: t('legacy.delete'), negativeText: t('legacy.cancel'), async onPositiveClick() { try { await deletePositionRole(role.id); message.success(t('legacy.deleted')); await load(); } catch (error: any) { message.error(error?.response?.data?.detail || t('legacy.failed_to_delete')); } } });
}
async function toggle(role: PositionRole, enabled: boolean) {
  if (!enabled && role.memberCount > 0) {
    dialog.warning({
      title: t('legacy.disable_position_role'),
      content: t('legacy.is_still_assigned_to_employees_disabling_it_removes_these', { name: role.name, count: role.memberCount }),
      positiveText: t('legacy.disable_anyway'), negativeText: t('legacy.cancel'),
      onPositiveClick: () => applyRoleStatus(role, enabled),
    });
    return;
  }
  await applyRoleStatus(role, enabled);
}

async function applyRoleStatus(role: PositionRole, enabled: boolean) {
  try { await setPositionRoleEnabled(role.id, enabled); await load(); }
  catch (error: any) { message.error(error?.response?.data?.detail || t('legacy.failed_to_update_status')); }
}

const labels: Record<string, string> = { content_generation: t('legacy.content'), image_generation: t('legacy.image'), code_generation: t('legacy.code_33246dd'), browser_automation: t('legacy.browser'), internal_knowledge: t('legacy.knowledge') };
const columns: DataTableColumns<PositionRole> = [
  { title: t('legacy.position_role'), key: 'name', render: row => h('div', { class: 'role-name' }, [h('strong', row.name), row.protected ? h(NTag, { size: 'small', type: 'info', bordered: false }, { default: () => t('legacy.system_protected') }) : null, h('small', row.description || t('legacy.no_description_6dd28f4'))]) },
  { title: t('legacy.enabled_capabilities'), key: 'capabilities', render: row => h(NSpace, { size: 6 }, { default: () => Object.entries(row.capabilities).filter(([, enabled]) => enabled).map(([key]) => h(NTag, { size: 'small', bordered: false }, { default: () => labels[key] })) }) },
  { title: t('legacy.employees_9834f85'), key: 'memberCount', width: 80 },
  { title: t('legacy.status'), key: 'status', width: 100, render: row => h(NTag, { type: row.status === 'active' ? 'success' : 'default', bordered: false }, { default: () => row.status === 'active' ? t('legacy.active') : t('legacy.disabled') }) },
  { title: t('legacy.actions'), key: 'actions', width: 300, render: row => h('div', { class: 'action-row' }, [
    h('button', { class: 'action-link', disabled: row.protected, onClick: () => openEdit(row) }, t('legacy.edit')),
    h('button', { class: 'action-link', onClick: () => copyRole(row) }, t('legacy.copy')),
    h('button', { class: row.status === 'active' ? 'action-link danger' : 'action-link', disabled: row.protected, onClick: () => toggle(row, row.status !== 'active') }, row.status === 'active' ? t('legacy.disabled') : t('legacy.active')),
    h('button', { class: 'action-link danger', disabled: row.protected, onClick: () => removeRole(row) }, t('legacy.delete')),
  ]) },
];

onMounted(load);
</script>

<template>
  <div class="page-stack position-role-page">
    <n-card class="position-role-card" :bordered="false" size="large">
      <div class="position-role-content">
        <div class="page-head"><PageIntro :title="t('legacy.position_roles')" :description="t('legacy.configure_visible_and_executable_agent_capabilities_by_employee_responsibili')" /><n-button type="primary" @click="openCreate">{{ t('legacy.create_position_role') }}</n-button></div>
        <div class="role-table-card"><n-data-table :columns="columns" :data="roles" :loading="loading" :bordered="false" /></div>
      </div>
    </n-card>
    <n-drawer v-model:show="editorVisible" :width="720" placement="right">
      <n-drawer-content :title="editing ? t('legacy.edit_feaeda3', { name: editing.name }) : t('legacy.create_position_role')" closable>
        <n-form :model="draft" label-placement="top">
          <n-grid :cols="2" :x-gap="14"><n-grid-item><n-form-item :label="t('legacy.position_role_name')" required><n-input v-model:value="draft.name" /></n-form-item></n-grid-item><n-grid-item><n-form-item :label="t('legacy.status')"><n-select v-model:value="draft.status" :options="[{ label: t('legacy.active'), value: 'active' }, { label: t('legacy.disabled'), value: 'disabled' }]" /></n-form-item></n-grid-item></n-grid>
          <n-form-item :label="t('legacy.description')"><n-input v-model:value="draft.description" type="textarea" :rows="2" /></n-form-item>
          <RoleCapabilityEditor v-model="draft" />
        </n-form>
        <template #footer><div class="drawer-footer"><span>{{ t('legacy.base_capabilities_enabled', { count: enabledSummary }) }}</span><n-space><n-button @click="editorVisible = false">{{ t('legacy.cancel') }}</n-button><n-button type="primary" :loading="saving" @click="save">{{ t('legacy.save') }}</n-button></n-space></div></template>
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
