<template>
  <div class="output-sample">
    <n-button @click="showImport = true">
      <template #icon>
        <n-icon><DownloadOutline /></n-icon>
      </template>
      {{ t('toolOutput.importTitle') }}
    </n-button>
    <n-modal v-model:show="showImport" preset="card" :title="t('toolOutput.importTitle')" style="width: min(640px, calc(100vw - 32px))">
      <n-input
        v-model:value="sample"
        type="textarea"
        :aria-label="t('toolOutput.sampleLabel')"
        :placeholder="t('toolOutput.sampleLabel')"
        :autosize="{ minRows: 4, maxRows: 10 }"
      />
      <n-button size="small" :disabled="!sample.trim()" @click="importSample">
        {{ t('toolOutput.importFields') }}
      </n-button>
    </n-modal>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { DownloadOutline } from '@vicons/ionicons5'
import { NButton, NIcon, NInput, NModal, useMessage } from 'naive-ui'
import { t } from '../composables/i18n'

const emit = defineEmits<{
  import: [response: unknown]
}>()
const message = useMessage()
const sample = ref('')
const showImport = ref(false)

function importSample() {
  let response: unknown
  try {
    response = JSON.parse(sample.value)
  } catch {
    message.warning(t('toolOutput.invalidSample'))
    return
  }
  emit('import', response)
  showImport.value = false
}
</script>

