import { useDialog, useMessage } from 'naive-ui';
import { enableModelVision, testModelVision, type ModelInstanceItem } from '@/api/models';
import { t } from '@/composables/i18n';

/** Suggest an additive setting only after the saved model passes a real image challenge. */
export function useVisionCapabilitySuggestion() {
  const dialog = useDialog();
  const message = useMessage();

  async function check(model: ModelInstanceItem | undefined, onEnabled: () => void | Promise<void>) {
    if (!model || model.capabilities.includes('vision')) return;
    const supported = await testModelVision(model.id).catch(() => false);
    if (!supported) return;
    dialog.info({
      title: t('modelVision.detectedTitle'),
      content: t('modelVision.detectedDescription'),
      positiveText: t('modelVision.enable'),
      negativeText: t('modelVision.later'),
      onPositiveClick: async () => {
        try {
          await enableModelVision(model.id);
          await onEnabled();
          message.success(t('modelVision.enabled'));
        } catch {
          message.error(t('modelVision.enableFailed'));
          return false;
        }
      },
    });
  }

  return { check };
}
