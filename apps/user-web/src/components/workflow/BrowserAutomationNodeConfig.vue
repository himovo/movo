<script setup lang="ts">
import { computed } from 'vue'
import { NInput } from 'naive-ui'
import { t } from '../../composables/i18n'

const props = defineProps<{
  text: string
  businessConfig: Record<string, any>
}>()

const emit = defineEmits<{
  'update:text': [value: string]
  'update:businessConfig': [value: Record<string, any>]
}>()

const targetName = computed({
  get: () => String(props.businessConfig?.targetName || ''),
  set: (value: string) => emit('update:businessConfig', { ...props.businessConfig, targetName: value }),
})

const targetUrl = computed({
  get: () => String(props.businessConfig?.targetUrl || ''),
  set: (value: string) => emit('update:businessConfig', { ...props.businessConfig, targetUrl: value }),
})
</script>

<template>
  <div class="browser-node-config" @click.stop>
    <label class="field-label">{{ t('workflow.browser.target_name') }}</label>
    <n-input
      v-model:value="targetName"
      clearable
      :placeholder="t('workflow.browser.target_name_placeholder')"
    />
    <label class="field-label">{{ t('workflow.browser.target_url') }}</label>
    <n-input
      v-model:value="targetUrl"
      clearable
      :placeholder="t('workflow.browser.target_url_placeholder')"
    />
    <label class="field-label">{{ t('节点要求') }}</label>
    <n-input
      :value="text"
      type="textarea"
      :autosize="{ minRows: 3, maxRows: 10 }"
      :placeholder="t('workflow.preset.browser_automation.placeholder')"
      @update:value="(value) => emit('update:text', value)"
    />
  </div>
</template>

<style scoped>
.browser-node-config {
  display: grid;
  gap: 8px;
}

.field-label {
  color: #334155;
  font-size: 12px;
  font-weight: 600;
}

.field-label:not(:first-child) {
  margin-top: 4px;
}
</style>
