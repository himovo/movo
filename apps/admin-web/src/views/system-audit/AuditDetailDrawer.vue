<script setup lang="ts">
import { computed } from 'vue';
import type { SystemAuditLog } from '@/api/systemAudit';
import { formatAdminDateTime } from '@/composables/adminTimezone';
import { t } from '@/composables/i18n';

const props = defineProps<{ show: boolean; record: SystemAuditLog | null }>();
const emit = defineEmits<{ 'update:show': [value: boolean] }>();
const detailRows = computed(() => Object.entries(props.record?.details || {}).filter(([, value]) => value !== '' && value != null));
</script>

<template>
  <n-drawer :show="show" :width="520" placement="right" @update:show="emit('update:show', $event)">
    <n-drawer-content :title="t('legacy.audit_details')" closable>
      <n-descriptions v-if="record" :column="1" label-placement="left" bordered>
        <n-descriptions-item :label="t('legacy.time')">{{ formatAdminDateTime(record.occurredAt, '-') }}</n-descriptions-item>
        <n-descriptions-item :label="t('legacy.module')">{{ record.module }}</n-descriptions-item>
        <n-descriptions-item :label="t('legacy.actions')">{{ record.action }}</n-descriptions-item>
        <n-descriptions-item :label="t('legacy.actor')">{{ record.actor || '-' }}</n-descriptions-item>
        <n-descriptions-item :label="t('legacy.object')">{{ record.target || '-' }}</n-descriptions-item>
        <n-descriptions-item :label="t('legacy.result')">
          <n-tag :type="record.result === 'success' ? 'success' : 'error'" :bordered="false">{{ record.result === 'success' ? t('legacy.success_51991a5') : t('legacy.failed') }}</n-tag>
        </n-descriptions-item>
        <n-descriptions-item v-for="([key, value]) in detailRows" :key="key" :label="key">
          <span class="detail-value">{{ typeof value === 'object' ? JSON.stringify(value, null, 2) : value }}</span>
        </n-descriptions-item>
      </n-descriptions>
    </n-drawer-content>
  </n-drawer>
</template>

<style scoped>
.detail-value { color: #475467; font-family: ui-monospace, SFMono-Regular, Menlo, monospace; white-space: pre-wrap; overflow-wrap: anywhere; }
</style>
