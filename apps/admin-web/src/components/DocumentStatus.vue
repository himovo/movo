<template>
  <button
    v-if="state.retryable"
    type="button"
    class="doc-status-wrapper doc-status-button"
    :style="{ color: displayColor }"
    :title="t('additional.click_to_relearn')"
    @click.stop="emit('retry')"
  >
    <span class="status-icon-box" v-html="state.icon"></span>
    <span class="status-label">{{ state.label }}</span>
    <span class="retry-icon" aria-hidden="true">
      <svg viewBox="0 0 24 24"><path d="M21 12a9 9 0 0 0-15.3-6.4" /><path d="M3 3v5h5" /><path d="M3 12a9 9 0 0 0 15.3 6.4" /><path d="M21 21v-5h-5" /></svg>
    </span>
  </button>
  <div v-else class="doc-status-wrapper" :style="{ color: displayColor }">
    <!-- SVG icon -->
    <span class="status-icon-box" v-html="state.icon"></span>
    <!-- Status text -->
    <span class="status-label">{{ state.label }}</span>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import { t } from '@/composables/i18n';
import { useTheme } from '@/composables/theme';
import type { KnowledgeDocumentItem } from '@/api/knowledge-documents';
import { knowledgeDocumentRetryStage } from '@/utils/knowledgeDocumentRetry';

const props = defineProps<{
  row: KnowledgeDocumentItem;
}>();

const emit = defineEmits<{
  retry: [];
}>();

const { activeTheme } = useTheme();
const displayColor = computed(() => {
  if (activeTheme.value !== 'dark') return state.value.color;
  const color = state.value.color.toLowerCase();
  if (color === '#d32f2f' || color === '#ff4d4f') return '#ff9ba8';
  if (color === '#52c41a') return '#75d6ae';
  if (color === '#2f80ed' || color === '#1890ff') return '#9ab9ff';
  return '#aebdd1';
});

const state = computed(() => {
  const row = props.row;

  // 1. Learning failed.
  // Upload succeeded, but parsing or indexing failed later.
  if (row.parseStatus === 'failed' || row.indexStatus === 'failed') {
    return {
      label: t('legacy.learning_failed'),
      color: '#D32F2F',
      retryable: knowledgeDocumentRetryStage(row) !== null,
      icon: `<svg class="status-svg" viewBox="0 0 16 16" fill="none" xmlns="http://www.w3.org/2000/svg">
        <circle cx="8" cy="8" r="7" fill="#FFF1F0" stroke="#D32F2F" stroke-width="1.2"/>
        <path d="M8 4.5V9M8 11.5V11" stroke="#D32F2F" stroke-width="1.6" stroke-linecap="round"/>
      </svg>`
    };
  }

  // 2. Upload failed.
  // Treat a failed file that never entered learning as an upload failure.
  if (row.status === 'failed') {
    return {
      label: t('legacy.upload_failed'),
      color: '#FF4D4F',
      retryable: false,
      icon: `<svg class="status-svg" viewBox="0 0 16 16" fill="none" xmlns="http://www.w3.org/2000/svg">
        <circle cx="8" cy="8" r="7" fill="#FFF1F0" stroke="#FF4D4F" stroke-width="1.2"/>
        <path d="M5.5 5.5L10.5 10.5M10.5 5.5L5.5 10.5" stroke="#FF4D4F" stroke-width="1.2" stroke-linecap="round"/>
      </svg>`
    };
  }

  // 3. Learning has not started.
  // Both substatuses are not_started.
  if (row.parseStatus === 'not_started' && row.indexStatus === 'not_started') {
    return {
      label: t('legacy.learning_not_started'),
      color: '#90A4AE',
      retryable: false,
      icon: `<svg class="status-svg" viewBox="0 0 16 16" fill="none" xmlns="http://www.w3.org/2000/svg">
        <circle cx="8" cy="8" r="7" fill="#F5F5F5" stroke="#90A4AE" stroke-width="1.2"/>
        <path d="M8 4V8L10.5 9.5" stroke="#90A4AE" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round"/>
      </svg>`
    };
  }

  // 4. Learning completed.
  // Both parsing and indexing succeeded.
  if (row.parseStatus === 'succeeded' && row.indexStatus === 'succeeded') {
    return {
      label: t('legacy.learning_complete'),
      color: '#52C41A',
      retryable: false,
      icon: `<svg class="status-svg" viewBox="0 0 16 16" fill="none" xmlns="http://www.w3.org/2000/svg">
        <circle cx="8" cy="8" r="7" fill="#F6FFED" stroke="#52C41A" stroke-width="1.2"/>
        <path d="M5 8L7 10L11 6" stroke="#52C41A" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
      </svg>`
    };
  }

  if (row.parseStatus === 'succeeded' && row.chunkStatus === 'succeeded' && row.indexStatus === 'not_started') {
    return {
      label: t('additional.parsing_completed'),
      color: '#2F80ED',
      retryable: false,
      icon: `<svg class="status-svg" viewBox="0 0 16 16" fill="none" xmlns="http://www.w3.org/2000/svg">
        <circle cx="8" cy="8" r="7" fill="#EAF3FF" stroke="#2F80ED" stroke-width="1.2"/>
        <path d="M5 8L7 10L11 6" stroke="#2F80ED" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
      </svg>`
    };
  }

  // 5. Learning in progress.
  // Any other processing status, such as queued or running.
  return {
    label: t('legacy.learning'),
    color: '#1890FF',
    retryable: false,
    icon: `<svg class="status-svg spin-icon" viewBox="0 0 16 16" fill="none" xmlns="http://www.w3.org/2000/svg">
      <circle cx="8" cy="8" r="7" stroke="#E6F7FF" stroke-width="1.2"/>
      <path d="M8 1a7 7 0 0 1 7 7" stroke="#1890FF" stroke-width="1.5" stroke-linecap="round"/>
    </svg>`
  };
});
</script>

<style scoped>
.doc-status-wrapper {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  font-weight: 550;
  line-height: 1.4;
  vertical-align: middle;
}

.doc-status-button {
  padding: 0;
  border: 0;
  background: transparent;
  cursor: pointer;
}

.doc-status-button:hover .status-label {
  text-decoration: underline;
  text-underline-offset: 2px;
}

.status-icon-box {
  display: inline-flex;
  width: 14px;
  height: 14px;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.status-icon-box :deep(.status-svg) {
  width: 14px;
  height: 14px;
  display: block;
}

.status-icon-box :deep(.spin-icon) {
  animation: spin 1.2s linear infinite;
}

@keyframes spin {
  from {
    transform: rotate(0deg);
  }
  to {
    transform: rotate(360deg);
  }
}

.status-label {
  letter-spacing: 0.2px;
}

.retry-icon {
  display: inline-flex;
  width: 13px;
  height: 13px;
  opacity: 0.78;
}

.retry-icon svg {
  width: 13px;
  height: 13px;
  fill: none;
  stroke: currentColor;
  stroke-width: 2;
  stroke-linecap: round;
  stroke-linejoin: round;
}
</style>
