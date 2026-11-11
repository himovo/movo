<script setup lang="ts">
import { ref, watch } from 'vue';
import axios from 'axios';
import { useMessage } from 'naive-ui';
import { t } from '@/composables/i18n';
import { commitDepartmentImport, downloadDepartmentImportTemplate, previewDepartmentImport, type DepartmentImportPreview } from '@/api/directory';

const props = defineProps<{ open: boolean }>();
const emit = defineEmits<{ close: []; imported: [] }>();
const message = useMessage();
const file = ref<File | null>(null);
const preview = ref<DepartmentImportPreview | null>(null);
const busy = ref(false);

watch(() => props.open, (open) => {
  if (!open) {
    file.value = null;
    preview.value = null;
  }
});

function errorText(error: unknown): string {
  const code = axios.isAxiosError(error) ? String(error.response?.data?.detail || '') : '';
  return t(code ? `departmentImport.${code}` : 'departmentImport.failed');
}

function selectFile(event: Event) {
  file.value = (event.target as HTMLInputElement).files?.[0] || null;
  preview.value = null;
}

async function downloadTemplate() {
  try {
    const blob = await downloadDepartmentImportTemplate();
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = 'department-import-template.xlsx';
    anchor.click();
    URL.revokeObjectURL(url);
  } catch (error) {
    message.error(errorText(error));
  }
}

async function runPreview() {
  if (!file.value) return;
  busy.value = true;
  try {
    preview.value = await previewDepartmentImport(file.value);
  } catch (error) {
    preview.value = null;
    message.error(errorText(error));
  } finally {
    busy.value = false;
  }
}

async function commit() {
  if (!file.value || !preview.value || preview.value.errors.length) return;
  busy.value = true;
  try {
    const result = await commitDepartmentImport(file.value, preview.value.digest);
    message.success(t('departmentImport.done', { count: result.created }));
    emit('imported');
    emit('close');
  } catch (error) {
    preview.value = null;
    message.error(errorText(error));
  } finally {
    busy.value = false;
  }
}
</script>

<template>
  <n-modal :show="open" preset="card" :title="t('departmentImport.title')" style="width: min(720px, 95vw)" @close="emit('close')">
    <p class="import-help">{{ t('departmentImport.help') }}</p>
    <n-space align="center">
      <n-button @click="downloadTemplate">{{ t('departmentImport.template') }}</n-button>
      <label class="file-picker">
        {{ t('departmentImport.choose') }}
        <input type="file" accept=".xlsx" @change="selectFile" />
      </label>
      <span v-if="file">{{ file.name }}</span>
      <n-button type="primary" :loading="busy" :disabled="!file" @click="runPreview">{{ t('departmentImport.preview') }}</n-button>
    </n-space>
    <div v-if="preview" class="preview-area">
      <strong>{{ t('departmentImport.summary', { create: preview.createCount, skip: preview.skipCount, errors: preview.errors.length }) }}</strong>
      <div class="preview-list">
        <div v-for="item in preview.errors" :key="`error-${item.row}`" class="preview-error">
          {{ t('departmentImport.row', { row: item.row }) }} · {{ item.path }} · {{ t(`departmentImport.${item.code}`) }}
        </div>
        <div v-for="item in preview.items" :key="`item-${item.row}`">
          {{ t('departmentImport.row', { row: item.row }) }} · {{ item.path }} · {{ t(`departmentImport.${item.action}`) }}
        </div>
      </div>
    </div>
    <template #footer>
      <n-space justify="end">
        <n-button @click="emit('close')">{{ t('departmentImport.close') }}</n-button>
        <n-button type="primary" :loading="busy" :disabled="!preview || !!preview.errors.length || !preview.createCount" @click="commit">{{ t('departmentImport.commit') }}</n-button>
      </n-space>
    </template>
  </n-modal>
</template>

<style scoped>
.import-help { margin: 0 0 16px; color: #64748b; }
.file-picker { padding: 6px 12px; border: 1px solid #d5dbe5; border-radius: 4px; cursor: pointer; }
.file-picker input { display: none; }
.preview-area { margin-top: 18px; }
.preview-list { max-height: 320px; overflow: auto; margin-top: 10px; line-height: 2; }
.preview-error { color: #d03050; }
</style>
