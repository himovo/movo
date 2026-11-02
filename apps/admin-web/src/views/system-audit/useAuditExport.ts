import { ref } from 'vue';
import axios from 'axios';
import { useMessage } from 'naive-ui';
import { exportSystemAuditLogs, type AuditFilters } from '@/api/systemAudit';
import { t } from '@/composables/i18n';

export function useAuditExport(filters: () => AuditFilters) {
  const exporting = ref(false);
  const message = useMessage();
  async function exportExcel() {
    if (exporting.value) return;
    exporting.value = true;
    try {
      const blob = await exportSystemAuditLogs(filters());
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement('a');
      anchor.href = url;
      anchor.download = `system-audit-${new Date().toISOString().replace(/[:.]/g, '-')}.xlsx`;
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      window.setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (error) {
      if (axios.isAxiosError(error) && error.response?.status === 413) message.warning(t('audit.exportLimit'));
      else message.error(t('audit.exportFailed'));
    } finally { exporting.value = false; }
  }
  return { exporting, exportExcel };
}
