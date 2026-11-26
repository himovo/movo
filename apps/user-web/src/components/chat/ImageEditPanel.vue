<script setup lang="ts">
import { ref, watch } from 'vue'
import { t } from '../../composables/i18n'
import { editMessageImage } from '../../api/imageEdits'
import { fetchImageModels, type ChatModelOption } from '../../api/models'
import type { ImageEditingContext } from './imageEditingContext'
import type { DocumentInfo } from './types'
import CutOutline from '@vicons/ionicons5/es/CutOutline'
import LayersOutline from '@vicons/ionicons5/es/LayersOutline'
import SparklesOutline from '@vicons/ionicons5/es/SparklesOutline'
import ArrowUpOutline from '@vicons/ionicons5/es/ArrowUpOutline'

const props = defineProps<{ src: string; context: ImageEditingContext; objectPath?: string }>()
const emit = defineEmits<{ (event: 'edited', document: DocumentInfo): void }>()
const prompt = ref('')
const busy = ref(false)
const error = ref('')
const needsModel = ref(false)
const selectedModel = ref('')
const models = ref<ChatModelOption[]>([])
const modelsLoading = ref(false)
watch(() => props.src, () => { needsModel.value = false; selectedModel.value = ''; error.value = '' })

async function chooseLegacyModel() {
  needsModel.value = true
  modelsLoading.value = true
  try { models.value = await fetchImageModels() }
  catch { error.value = t('imageEdit.modelsUnavailable') }
  finally { modelsLoading.value = false }
}
const presets = ['removeBackground', 'replaceBackground', 'enhance'] as const
const presetIcons = { removeBackground: CutOutline, replaceBackground: LayersOutline, enhance: SparklesOutline }

async function submit() {
  if (busy.value || !prompt.value.trim() || (needsModel.value && !selectedModel.value)) return
  busy.value = true
  error.value = ''
  const context = props.context
  try {
    const result = await editMessageImage(context.sessionId, context.messageId, {
      prompt: prompt.value.trim(), source_url: props.src, object_path: props.objectPath,
      image_model_id: selectedModel.value || undefined,
    })
    context.onEdited(result)
    emit('edited', result)
    prompt.value = ''
  } catch (failure) {
    const detail = (failure as { response?: { data?: { detail?: string } } }).response?.data?.detail
    if (detail === 'image_edit_model_required') {
      error.value = t('imageEdit.modelRequired')
      await chooseLegacyModel()
      return
    }
    error.value = t(detail === 'image_source_unavailable' ? 'imageEdit.sourceUnavailable'
      : detail === 'image_message_running' ? 'imageEdit.busy'
      : detail === 'image_edit_model_unavailable' || detail === 'image_edit_model_mismatch' ? 'imageEdit.modelUnavailable' : 'imageEdit.failed')
  } finally { busy.value = false }
}
</script>

<template>
  <form class="image-edit-panel" :aria-busy="busy" @submit.prevent="submit">
    <label v-if="needsModel" class="image-edit-model">
      <span>{{ t('imageEdit.selectModel') }}</span>
      <select v-model="selectedModel" :disabled="busy || modelsLoading" :aria-label="t('imageEdit.selectModel')">
        <option disabled value="">{{ t(modelsLoading ? 'imageEdit.modelsLoading' : 'imageEdit.selectModel') }}</option>
        <option v-for="model in models" :key="model.id" :value="model.id">{{ model.displayName || model.modelName }} · {{ model.providerName }}</option>
      </select>
    </label>
    <div class="image-edit-presets">
      <button v-for="preset in presets" :key="preset" type="button" :disabled="busy" :class="{ 'is-selected': prompt === t(`imageEdit.${preset}Prompt`) }" @click="prompt = t(`imageEdit.${preset}Prompt`)"><component :is="presetIcons[preset]" aria-hidden="true" />{{ t(`imageEdit.${preset}`) }}</button>
    </div>
    <div class="image-edit-input">
      <textarea v-model="prompt" :disabled="busy" :aria-label="t('imageEdit.placeholder')" :placeholder="t('imageEdit.placeholder')" rows="2" maxlength="4000" @keydown.ctrl.enter.prevent="submit" @keydown.meta.enter.prevent="submit" />
      <button type="submit" :aria-label="t(busy ? 'imageEdit.working' : 'imageEdit.submit')" :disabled="busy || !prompt.trim() || (needsModel && !selectedModel)"><span v-if="busy" class="image-edit-spinner" aria-hidden="true" /><ArrowUpOutline v-else aria-hidden="true" /><span>{{ t(busy ? 'imageEdit.working' : 'imageEdit.submit') }}</span></button>
    </div>
    <p v-if="error" role="alert">{{ error }}</p>
  </form>
</template>

<style scoped>
.image-edit-panel { flex: none; width: min(720px, 100%); margin: 0 auto; padding: 16px; border: 1px solid #ffffff14; border-radius: 22px; background: linear-gradient(155deg, #242830, #1c2027); box-shadow: 0 16px 48px #00000038, inset 0 1px 0 #ffffff05; color: #eef1f5; transition: border-color 160ms, box-shadow 160ms; }
.image-edit-panel:focus-within { border-color: #7398d94d; box-shadow: 0 16px 48px #00000038, 0 0 0 3px #7398d908; }
.image-edit-model { display: grid; gap: 6px; margin-bottom: 14px; color: #aeb8c7; font-size: 12px; }
.image-edit-model select { width: 100%; padding: 9px; border: 1px solid #ffffff20; border-radius: 8px; background: #20242c; color: #edf2f8; }
.image-edit-presets { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 14px; }
.image-edit-presets button { display: inline-flex; align-items: center; gap: 6px; min-height: 32px; padding: 5px 11px; border: 1px solid #ffffff09; border-radius: 9px; background: #ffffff05; color: #aeb8c7; font-size: 12px; transition: background 150ms, color 150ms, border-color 150ms; }
.image-edit-presets svg { width: 14px; height: 14px; opacity: .75; }
.image-edit-presets button:hover:not(:disabled), .image-edit-presets button.is-selected { border-color: #ffffff20; background: #ffffff0d; color: #edf2fa; }
.image-edit-input { display: flex; align-items: flex-end; gap: 16px; }
textarea { flex: 1; min-width: 0; min-height: 58px; padding: 2px 2px 6px; resize: none; background: transparent; color: #edf2f8; outline: none; font-size: 14px; line-height: 1.65; }
textarea::placeholder { color: #858f9f; }
.image-edit-input button { display: inline-flex; flex: none; align-items: center; justify-content: center; gap: 7px; min-height: 42px; padding: 9px 14px; border: 1px solid #92b7ff26; border-radius: 12px; background: #dce9ff; color: #192d4c; font-size: 12px; font-weight: 600; box-shadow: 0 2px 8px #00000020; transition: background 150ms; }
.image-edit-input button:hover:not(:disabled) { background: #eff5ff; }
.image-edit-input button svg { width: 17px; height: 17px; }
button:disabled { opacity: .35; cursor: not-allowed; box-shadow: none; }
button:focus-visible { outline: 2px solid #a5c6ff; outline-offset: 3px; }
.image-edit-spinner { width: 14px; height: 14px; border: 1.5px solid currentColor; border-right-color: transparent; border-radius: 50%; animation: image-edit-spin .8s linear infinite; }
p { color: #fca5a5; margin-top: 10px; font-size: 12px; }
@keyframes image-edit-spin { to { transform: rotate(360deg); } }
@media (max-width: 600px) {
  .image-edit-panel { padding: 13px; border-radius: 18px; }
  .image-edit-presets { gap: 6px; margin-bottom: 12px; }
  .image-edit-presets button { padding: 5px 8px; font-size: 11px; }
  .image-edit-input { gap: 10px; }
  .image-edit-input button { min-width: 42px; padding: 9px; }
  .image-edit-input button > span:not(.image-edit-spinner) { display: none; }
}
@media (prefers-reduced-motion: reduce) {
  .image-edit-panel, button { transition: none !important; }
  .image-edit-spinner { animation: none; }
}
</style>
