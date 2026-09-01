<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import type { SetupServiceStatus } from '@/api/setup';
import { t } from '@/composables/i18n';

const props = defineProps<{
  ready: boolean;
  loading: boolean;
  services: SetupServiceStatus[];
}>();

defineEmits<{ refresh: [] }>();

const expanded = ref(!props.ready);
const readyCount = computed(() => props.services.filter((service) => service.ok).length);
const serviceLabels: Record<string, string> = {
  mongo: 'MongoDB',
  redis: 'Redis',
  storage: '持久化存储',
  'chat-api': 'Chat API',
  'document-processing': '文档处理与 Worker',
  weaviate: 'Weaviate',
};

watch(() => props.ready, (ready) => {
  expanded.value = !ready;
});

function serviceLabel(service: SetupServiceStatus) {
  return t(serviceLabels[service.key] || service.label);
}
</script>

<template>
  <section class="deployment-status" aria-live="polite">
    <div class="status-summary">
      <span class="summary-icon" :class="{ ready }" aria-hidden="true">
        <svg v-if="ready" viewBox="0 0 24 24"><path d="m5 12 4 4L19 6" /></svg>
        <svg v-else viewBox="0 0 24 24"><path d="M12 8v5m0 3h.01M10.3 3.8 2.4 17.5A2 2 0 0 0 4.1 20h15.8a2 2 0 0 0 1.7-2.5L13.7 3.8a2 2 0 0 0-3.4 0Z" /></svg>
      </span>
      <div class="summary-copy">
        <strong>{{ t('部署状态') }}</strong>
        <span>{{ t('{ready}/{total} 项服务已就绪', { ready: readyCount, total: services.length }) }}</span>
      </div>
      <n-tag size="small" :type="ready ? 'success' : 'warning'">
        {{ ready ? t('全部就绪') : t('正在检查') }}
      </n-tag>
      <button
        type="button"
        class="details-button"
        :aria-expanded="expanded"
        @click="expanded = !expanded"
      >
        {{ expanded ? t('收起详情') : t('查看详情') }}
        <svg viewBox="0 0 24 24" :class="{ expanded }" aria-hidden="true"><path d="m6 9 6 6 6-6" /></svg>
      </button>
    </div>

    <n-collapse-transition :show="expanded">
      <div class="status-details">
        <div class="service-list">
          <div v-for="service in services" :key="service.key" class="service-row">
            <span class="status-dot" :class="{ ready: service.ok }" aria-hidden="true"></span>
            <span>{{ serviceLabel(service) }}</span>
            <span class="service-state">{{ service.ok ? t('正常') : t('未就绪') }}</span>
          </div>
        </div>
        <n-button class="refresh-button" secondary :loading="loading" @click="$emit('refresh')">
          <template #icon>
            <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M20 6v5h-5M4 18v-5h5M6.1 9a7 7 0 0 1 11.5-2.6L20 9M4 15l2.4 2.6A7 7 0 0 0 17.9 15" /></svg>
          </template>
          {{ t('重新检查') }}
        </n-button>
      </div>
    </n-collapse-transition>
  </section>
</template>

<style scoped>
.deployment-status {
  margin-bottom: 22px;
  overflow: hidden;
  border: 1px solid #dfe7f5;
  border-radius: 14px;
  background: #f8faff;
}

.status-summary {
  display: flex;
  min-height: 68px;
  align-items: center;
  gap: 12px;
  padding: 12px 14px;
}

.summary-icon {
  display: grid;
  width: 36px;
  height: 36px;
  flex: 0 0 36px;
  place-items: center;
  border-radius: 10px;
  background: #fff3d6;
  color: #b46b08;
}

.summary-icon.ready { background: #e6f7f0; color: #168461; }
.summary-icon svg, .refresh-button svg { width: 19px; fill: none; stroke: currentColor; stroke-linecap: round; stroke-linejoin: round; stroke-width: 2; }
.summary-copy { display: grid; min-width: 0; flex: 1; gap: 2px; }
.summary-copy strong { color: #17233d; font-size: 14px; }
.summary-copy span { color: #66748f; font-size: 12px; }

.details-button {
  display: inline-flex;
  min-height: 44px;
  align-items: center;
  gap: 5px;
  border: 0;
  background: transparent;
  color: #315fc8;
  cursor: pointer;
  font: inherit;
  font-size: 13px;
  font-weight: 600;
}

.details-button:focus-visible { border-radius: 8px; outline: 3px solid rgba(53, 104, 232, .25); outline-offset: 2px; }
.details-button svg { width: 16px; fill: none; stroke: currentColor; stroke-width: 2; transition: transform .2s ease; }
.details-button svg.expanded { transform: rotate(180deg); }
.status-details { display: grid; grid-template-columns: 1fr auto; gap: 16px; padding: 4px 14px 14px 62px; border-top: 1px solid #e7edf7; }
.service-list { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 8px 22px; padding-top: 12px; }
.service-row { display: flex; min-width: 0; align-items: center; gap: 8px; color: #34425e; font-size: 13px; }
.status-dot { width: 8px; height: 8px; flex: 0 0 8px; border-radius: 50%; background: #f2a32b; }
.status-dot.ready { background: #27b386; }
.service-state { margin-left: auto; color: #748097; font-size: 12px; }
.refresh-button { align-self: end; min-height: 44px; }

@media (max-width: 600px) {
  .status-summary { flex-wrap: wrap; }
  .summary-copy { flex-basis: calc(100% - 52px); }
  .details-button { margin-left: auto; }
  .status-details { grid-template-columns: 1fr; padding-left: 14px; }
  .service-list { grid-template-columns: 1fr; }
  .refresh-button { width: 100%; }
}

@media (prefers-reduced-motion: reduce) {
  .details-button svg { transition: none; }
}
</style>
