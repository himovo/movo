<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import { useMessage } from 'naive-ui';
import { t } from '@/composables/i18n';
import { createModelInstance, deleteModelInstance, updateModelInstance, type ImageModelSettings, type ImageRuntimeKind, type ModelGroupItem, type ModelInstanceItem, type ModelInstancePayload, type ModelProviderItem, type ModelStatus, type ModelPricing } from '@/api/models';
import adminProductUiExtension from '@movo-admin-product-extension';
import ImageModelRuntimeFields from './ImageModelRuntimeFields.vue';
import ModelPricingFields from './ModelPricingFields.vue';
import ModelAccessExtensionPanel from './ModelAccessExtensionPanel.vue';
import { capabilityLabel } from './capabilityLabels';
import { modelApiErrorText } from './modelApiError';
import CubeOutline from '@vicons/ionicons5/es/CubeOutline';
import PlayOutline from '@vicons/ionicons5/es/PlayOutline';
import ChevronDownOutline from '@vicons/ionicons5/es/ChevronDownOutline';
import ChevronUpOutline from '@vicons/ionicons5/es/ChevronUpOutline';
import SaveOutline from '@vicons/ionicons5/es/SaveOutline';
import TrashOutline from '@vicons/ionicons5/es/TrashOutline';

const props = defineProps<{ group: ModelGroupItem; provider?: ModelProviderItem; model?: ModelInstanceItem; expanded?: boolean }>();
const emit = defineEmits<{ (event: 'saved', model: ModelInstanceItem): void; (event: 'deleted', id: string): void; (event: 'cancel'): void; (event: 'select', id: string): void }>();
const message = useMessage();
const extension = adminProductUiExtension.modelAccess;
const open = ref(Boolean(props.expanded || !props.model));
const saving = ref(false);
const accessLoading = ref(false);
const access = ref<unknown>(extension?.createValue(true));
const form = ref({ displayName: '', modelName: '', capabilities: ['chat'] as string[], status: 'active' as ModelStatus, runtimeKind: '' as ImageRuntimeKind | '', imageSettings: {} as ImageModelSettings, pricing: null as ModelPricing | null });
const imageModel = computed(() => form.value.capabilities.includes('image_generation'));
const selectable = computed(() => form.value.capabilities.some((item) => ['chat', 'text', 'image_generation'].includes(item)));
const capabilityOptions = computed(() => ['chat', 'vision', 'embedding', 'rerank', 'image_generation'].map((value) => ({ label: capabilityLabel(value), value })));
const runtimeDefault = computed<ImageRuntimeKind>(() => props.provider?.providerType === 'azure_openai' ? 'azure_openai_images' : 'openai_images');

watch(() => props.model?.id, async () => {
  const model = props.model;
  form.value = model
    ? { displayName: model.displayName, modelName: model.modelName, capabilities: [...model.capabilities], status: model.status, runtimeKind: model.runtimeKind || runtimeDefault.value, imageSettings: { ...model.imageSettings }, pricing: model.pricing ? { ...model.pricing } : null }
    : { displayName: '', modelName: '', capabilities: ['chat'], status: 'active', runtimeKind: runtimeDefault.value, imageSettings: {}, pricing: null };
  access.value = extension?.createValue(true);
  if (model && extension && model.capabilities.some((item) => ['chat', 'text', 'image_generation'].includes(item))) {
    accessLoading.value = true;
    try { access.value = await extension.load(model.id); }
    catch (error) { message.error(modelApiErrorText(error)); }
    finally { accessLoading.value = false; }
  }
}, { immediate: true });
watch(() => props.expanded, (value) => { if (value) open.value = true; });
watch(() => props.model?.capabilities, (capabilities) => {
  if (capabilities?.includes('vision') && !form.value.capabilities.includes('vision')) {
    form.value.capabilities = [...form.value.capabilities, 'vision'];
  }
});

async function save() {
  const warning = selectable.value ? extension?.validate?.(access.value) : null;
  if (warning) { message.warning(t(warning)); return; }
  if (!form.value.modelName.trim() || !form.value.capabilities.length) { message.warning(t('modelGroup.memberRequired')); return; }
  if (imageModel.value && form.value.runtimeKind === 'custom_images') {
    try {
      const parsed = JSON.parse(String(form.value.imageSettings.extraParamsJson || '{}').trim() || '{}');
      if (!parsed || Array.isArray(parsed) || typeof parsed !== 'object') throw new Error();
    } catch { message.warning(t('legacy.enter_a_valid_json_object')); return; }
  }
  saving.value = true;
  try {
    const payload: ModelInstancePayload = {
      providerId: props.group.providerId, groupId: props.group.id, orgId: props.model?.orgId || '',
      displayName: form.value.displayName.trim() || form.value.modelName.trim(), modelName: form.value.modelName.trim(),
      baseUrl: props.group.baseUrl, apiVersion: props.group.apiVersion, apiKey: '',
      capabilities: [...form.value.capabilities],
      runtimeKind: imageModel.value ? form.value.runtimeKind : '', imageSettings: imageModel.value ? { ...form.value.imageSettings } : {},
      maxContextTokens: props.model?.maxContextTokens || 0, status: form.value.status,
      isDefault: props.model?.isDefault || false, priority: props.model?.priority || 100,
      pricing: form.value.pricing,
    };
    const saved = props.model ? await updateModelInstance(props.model.id, payload) : await createModelInstance(payload);
    if (selectable.value && extension) {
      try { await extension.save(saved.id, access.value); }
      catch (error) { message.error(`${t('modelGroup.memberSavedAccessFailed')}: ${modelApiErrorText(error)}`); emit('saved', saved); return; }
    }
    emit('saved', saved);
    message.success(t('modelGroup.memberSaved'));
  } catch (error) { message.error(modelApiErrorText(error)); }
  finally { saving.value = false; }
}

async function remove() {
  if (!props.model || !window.confirm(t('modelGroup.deleteMemberConfirm', { name: props.model.displayName }))) return;
  saving.value = true;
  try { await deleteModelInstance(props.model.id); emit('deleted', props.model.id); }
  catch (error) { message.error(modelApiErrorText(error)); }
  finally { saving.value = false; }
}
</script>

<template>
  <section class="member-row">
    <div class="member-head">
      <button type="button" class="member-toggle" @click="open = !open">
        <n-icon size="19" class="member-icon"><CubeOutline /></n-icon>
        <span><strong>{{ model?.displayName || t('modelGroup.newMember') }}</strong><small>{{ model?.modelName || t('modelGroup.unsaved') }}</small></span>
      </button>
      <n-button v-if="model" size="small" quaternary @click="emit('select', model.id)"><template #icon><n-icon><PlayOutline /></n-icon></template>{{ t('modelGroup.testThisModel') }}</n-button>
      <n-button size="small" quaternary @click="open = !open"><template #icon><n-icon><ChevronUpOutline v-if="open" /><ChevronDownOutline v-else /></n-icon></template>{{ open ? t('modelGroup.collapse') : t('modelGroup.expand') }}</n-button>
    </div>
    <div v-if="open" class="member-fields">
      <n-form label-placement="top">
        <div class="field-grid">
          <n-form-item :label="t('legacy.model_id')"><n-input v-model:value="form.modelName" :placeholder="t('modelGroup.modelIdPlaceholder')" /></n-form-item>
          <n-form-item :label="t('legacy.display_name')"><n-input v-model:value="form.displayName" :placeholder="t('modelGroup.nameDefaultsToId')" /></n-form-item>
          <n-form-item :label="t('legacy.capabilities')"><n-select v-model:value="form.capabilities" multiple :options="capabilityOptions" /></n-form-item>
          <n-form-item :label="t('legacy.status')"><n-select v-model:value="form.status" :options="[{ label: t('modelGroup.active'), value: 'active' }, { label: t('modelGroup.disabled'), value: 'disabled' }]" /></n-form-item>
        </div>
        <ModelPricingFields v-model="form.pricing" />
        <n-collapse v-if="imageModel"><n-collapse-item :title="t('modelGroup.imageSettings')" name="image"><ImageModelRuntimeFields v-model:runtimeKind="form.runtimeKind" v-model:imageSettings="form.imageSettings" :provider-type="provider?.providerType || ''" /></n-collapse-item></n-collapse>
        <n-collapse v-if="extension && selectable"><n-collapse-item :title="t('modelGroup.memberAccess')" name="access"><ModelAccessExtensionPanel v-model="access" :loading="accessLoading" grouped /></n-collapse-item></n-collapse>
      </n-form>
      <div class="member-actions">
        <n-button v-if="model" size="small" tertiary type="error" :disabled="saving" @click="remove"><template #icon><n-icon><TrashOutline /></n-icon></template>{{ t('legacy.delete_model') }}</n-button>
        <n-button v-else size="small" @click="emit('cancel')">{{ t('legacy.cancel') }}</n-button>
        <n-button size="small" type="primary" :loading="saving || accessLoading" @click="save"><template #icon><n-icon><SaveOutline /></n-icon></template>{{ t('modelGroup.saveMember') }}</n-button>
      </div>
    </div>
  </section>
</template>

<style scoped>
.member-row { border: 1px solid #e3e9f2; border-radius: 9px; background: #fff; }
.member-head, .member-actions { display: flex; align-items: center; gap: 8px; padding: 10px 12px; }
.member-toggle { display: flex; align-items: center; gap: 10px; flex: 1; min-width: 0; border: 0; background: none; text-align: left; cursor: pointer; }
.member-toggle > span { min-width: 0; }
.member-icon { flex: none; color: #6384c5; }
.member-toggle strong, .member-toggle small { display: block; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.member-toggle small { color: #728097; }
.member-fields { padding: 4px 14px 14px; border-top: 1px solid #edf0f5; }
.field-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); column-gap: 12px; }
.member-actions { justify-content: flex-end; padding: 8px 0 0; }
@media (max-width: 720px) { .field-grid { grid-template-columns: 1fr; } }
</style>
