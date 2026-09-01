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
  if (!primaryRoleId.value) return message.warning(t('请选择主要岗位角色'));
  if (!props.userIds.length) return;
  saving.value = true;
  try {
    await bulkAssignUserRoles(props.userIds, primaryRoleId.value, roleIds.value);
    message.success(t('已更新 {count} 名员工的岗位角色', { count: props.userIds.length }));
    emit('update:show', false);
    emit('saved');
  } catch (error: any) { message.error(error?.response?.data?.detail || error?.message || t('批量分配失败')); }
  finally { saving.value = false; }
}

watch(() => props.show, (visible) => {
  if (!visible) return;
  primaryRoleId.value = options.value.find(option => !props.roles.find(role => role.id === option.value)?.protected)?.value || options.value[0]?.value || '';
  roleIds.value = primaryRoleId.value ? [primaryRoleId.value] : [];
});
</script>

<template>
  <n-modal :show="show" preset="card" :title="t('批量分配岗位角色')" style="width: 560px" @update:show="(value: boolean) => emit('update:show', value)">
    <n-alert type="info" :bordered="false">{{ t('将为已选择的 {count} 名员工统一替换岗位角色。', { count: userIds.length }) }}</n-alert>
    <n-form label-placement="top" style="margin-top: 18px">
      <n-form-item :label="t('主要岗位角色')" required><n-select v-model:value="primaryRoleId" :options="options" @update:value="syncPrimary" /></n-form-item>
      <n-form-item :label="t('其他岗位角色')"><n-select v-model:value="roleIds" multiple max-tag-count="responsive" :options="options" /></n-form-item>
    </n-form>
    <template #footer><n-space justify="end"><n-button @click="emit('update:show', false)">{{ t('取消') }}</n-button><n-button type="primary" :loading="saving" @click="save">{{ t('确认分配') }}</n-button></n-space></template>
  </n-modal>
</template>
