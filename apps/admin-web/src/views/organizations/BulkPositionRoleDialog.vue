<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import { useMessage } from 'naive-ui';
import { bulkAssignUserRoles, type PositionRole } from '@/api/positionRoles';
import { t } from '@/composables/i18n';

const props = defineProps<{ show: boolean; userIds: string[]; roles: PositionRole[] }>();
const emit = defineEmits<{ (event: 'update:show', value: boolean): void; (event: 'saved'): void }>();
const message = useMessage();
const saving = ref(false);
const primaryRoleId = ref('');
const roleIds = ref<string[]>([]);
const options = computed(() => props.roles.filter(role => role.status === 'active').map(role => ({ label: role.name, value: role.id })));

function syncPrimary(value: string) {
  roleIds.value = Array.from(new Set([value, ...roleIds.value.filter(Boolean)]));
}

async function save() {
  if (!primaryRoleId.value) return message.warning(t('legacy.select_a_primary_position_role'));
  if (!props.userIds.length) return;
  saving.value = true;
  try {
    await bulkAssignUserRoles(props.userIds, primaryRoleId.value, roleIds.value);
    message.success(t('legacy.updated_position_roles_for_employees', { count: props.userIds.length }));
    emit('update:show', false);
    emit('saved');
  } catch (error: any) { message.error(error?.response?.data?.detail || error?.message || t('legacy.bulk_assignment_failed')); }
  finally { saving.value = false; }
}

watch(() => props.show, (visible) => {
  if (!visible) return;
  primaryRoleId.value = options.value.find(option => !props.roles.find(role => role.id === option.value)?.protected)?.value || options.value[0]?.value || '';
  roleIds.value = primaryRoleId.value ? [primaryRoleId.value] : [];
});
</script>

<template>
  <n-modal :show="show" preset="card" :title="t('legacy.assign_position_roles_in_bulk')" style="width: 560px" @update:show="(value: boolean) => emit('update:show', value)">
    <n-alert type="info" :bordered="false">{{ t('legacy.replace_position_roles_for_the_selected_employees', { count: userIds.length }) }}</n-alert>
    <n-form label-placement="top" style="margin-top: 18px">
      <n-form-item :label="t('legacy.primary_position_role')" required><n-select v-model:value="primaryRoleId" :options="options" @update:value="syncPrimary" /></n-form-item>
      <n-form-item :label="t('legacy.additional_position_roles')"><n-select v-model:value="roleIds" multiple max-tag-count="responsive" :options="options" /></n-form-item>
    </n-form>
    <template #footer><n-space justify="end"><n-button @click="emit('update:show', false)">{{ t('legacy.cancel') }}</n-button><n-button type="primary" :loading="saving" @click="save">{{ t('legacy.assign') }}</n-button></n-space></template>
  </n-modal>
</template>
