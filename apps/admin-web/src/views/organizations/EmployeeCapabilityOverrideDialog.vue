<script setup lang="ts">
import { t } from '@/composables/i18n';
import { computed, ref, watch } from 'vue';
import { useMessage } from 'naive-ui';
import {
  createCapabilityOverride,
  listCapabilityOverrides,
  revokeCapabilityOverride,
  type AgentCapabilityKey,
  type CapabilityOverride,
} from '@/api/positionRoles';
import { formatAdminDateTime } from '@/composables/adminTimezone';

const props = defineProps<{ show: boolean; userId: string; userName: string }>();
const emit = defineEmits<{ (event: 'update:show', value: boolean): void }>();
const message = useMessage();
const loading = ref(false);
const saving = ref(false);
const overrides = ref<CapabilityOverride[]>([]);
const expiresAt = ref<number | null>(Date.now() + 7 * 24 * 60 * 60 * 1000);
const reason = ref('');
const allowCapabilities = ref<AgentCapabilityKey[]>([]);
const denyCapabilities = ref<AgentCapabilityKey[]>([]);

const capabilityOptions = [
  { label: t('legacy.content_generation'), value: 'content_generation' },
  { label: t('legacy.image_generation'), value: 'image_generation' },
  { label: t('legacy.code_generation'), value: 'code_generation' },
  { label: t('legacy.browser_automation'), value: 'browser_automation' },
  { label: t('legacy.internal_knowledge_search_e7ef223'), value: 'internal_knowledge' },
];
const hasChange = computed(() => allowCapabilities.value.length + denyCapabilities.value.length > 0);

function resetDraft() {
  allowCapabilities.value = [];
  denyCapabilities.value = [];
  expiresAt.value = Date.now() + 7 * 24 * 60 * 60 * 1000;
  reason.value = '';
}

async function load() {
  if (!props.userId) return;
  loading.value = true;
  try {
    overrides.value = await listCapabilityOverrides(props.userId);
  } finally { loading.value = false; }
}

async function save() {
  if (!hasChange.value) return message.warning(t('legacy.select_at_least_one_temporary_grant_or_restriction'));
  if (!expiresAt.value || expiresAt.value <= Date.now()) return message.warning(t('legacy.select_a_future_expiration_time'));
  if (!reason.value.trim()) return message.warning(t('legacy.enter_a_reason_for_the_authorization'));
  saving.value = true;
  try {
    await createCapabilityOverride(props.userId, {
      allowCapabilities: allowCapabilities.value,
      denyCapabilities: denyCapabilities.value,
      effectiveAt: new Date().toISOString(),
      expiresAt: new Date(expiresAt.value).toISOString(),
      reason: reason.value.trim(),
    });
    message.success(t('legacy.temporary_authorization_is_active'));
    resetDraft();
    await load();
  } catch (error: any) { message.error(error?.response?.data?.detail || error?.message || t('legacy.authorization_failed')); }
  finally { saving.value = false; }
}

async function revoke(row: CapabilityOverride) {
  try {
    await revokeCapabilityOverride(row.id);
    message.success(t('legacy.temporary_authorization_revoked'));
    await load();
  } catch (error: any) { message.error(error?.response?.data?.detail || error?.message || t('legacy.failed_to_revoke_authorization')); }
}

watch(() => props.show, (visible) => { if (visible) void load(); });
</script>

<template>
  <n-modal :show="show" preset="card" :title="t('legacy.temporary_capability_authorization', { name: userName })" style="width: 720px" @update:show="(value: boolean) => emit('update:show', value)">
    <n-spin :show="loading">
      <n-alert type="info" :bordered="false">{{ t('legacy.position_roles_remain_the_long_term_permission_baseline_use') }}</n-alert>
      <n-form label-placement="top" class="override-form">
        <n-grid :cols="2" :x-gap="14">
          <n-grid-item><n-form-item :label="t('legacy.temporarily_add_capabilities')"><n-select v-model:value="allowCapabilities" multiple :options="capabilityOptions.filter(item => !denyCapabilities.includes(item.value as AgentCapabilityKey))" /></n-form-item></n-grid-item>
          <n-grid-item><n-form-item :label="t('legacy.temporarily_restrict_capabilities')"><n-select v-model:value="denyCapabilities" multiple :options="capabilityOptions.filter(item => !allowCapabilities.includes(item.value as AgentCapabilityKey))" /></n-form-item></n-grid-item>
        </n-grid>
        <n-grid :cols="2" :x-gap="14">
          <n-grid-item><n-form-item :label="t('legacy.expiration_time')" required><n-date-picker v-model:value="expiresAt" type="datetime" clearable style="width:100%" /></n-form-item></n-grid-item>
          <n-grid-item><n-form-item :label="t('legacy.authorization_reason')" required><n-input v-model:value="reason" maxlength="1000" show-count /></n-form-item></n-grid-item>
        </n-grid>
        <n-space justify="end"><n-button type="primary" :loading="saving" @click="save">{{ t('legacy.create_temporary_authorization') }}</n-button></n-space>
      </n-form>
      <n-divider>{{ t('legacy.authorization_history') }}</n-divider>
      <n-empty v-if="!overrides.length" :description="t('legacy.no_temporary_authorizations')" />
      <div v-else class="override-list">
        <div v-for="row in overrides" :key="row.id" class="override-row">
          <div><strong>{{ row.reason }}</strong><small>{{ t('legacy.created', { time: formatAdminDateTime(row.createdAt, '-') }) }} · {{ row.expiresAt ? t('legacy.expires', { time: formatAdminDateTime(row.expiresAt, '-') }) : t('legacy.no_expiration') }}</small></div>
          <n-tag :type="row.status === 'active' ? 'success' : 'default'" :bordered="false">{{ row.status === 'active' ? t('legacy.active_4de07ee') : (row.status === 'expired' ? t('legacy.expired') : t('legacy.revoked')) }}</n-tag>
          <n-button v-if="row.status === 'active'" text type="error" @click="revoke(row)">{{ t('legacy.revoke') }}</n-button>
        </div>
      </div>
    </n-spin>
  </n-modal>
</template>

<style scoped>
.override-form { margin-top: 18px; }
.override-list { display: grid; gap: 8px; }
.override-row { display: grid; grid-template-columns: minmax(0, 1fr) auto auto; align-items: center; gap: 12px; padding: 12px; border: 1px solid #e5e7eb; border-radius: 10px; }
.override-row div { display: grid; gap: 4px; }
.override-row small { color: #667085; }
</style>
