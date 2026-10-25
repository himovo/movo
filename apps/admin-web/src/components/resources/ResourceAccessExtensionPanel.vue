<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'
import { useMessage } from 'naive-ui'
import { t } from '@/composables/i18n'
import type { ResourceAccessUiExtension } from '@/product/contracts'

const props = defineProps<{
  resourceId: string
  extension: ResourceAccessUiExtension
}>()

const message = useMessage()
const value = ref<unknown>(props.extension.createValue())
const loading = ref(false)
const saving = ref(false)

async function load() {
  if (!props.resourceId) return
  loading.value = true
  try {
    value.value = await props.extension.load(props.resourceId)
  } catch (error: any) {
    message.error(error?.response?.data?.detail || error?.message || t('legacy.failed_to_load_access_policy'))
  } finally {
    loading.value = false
  }
}

async function save() {
  const validation = props.extension.validate?.(value.value)
  if (validation) return message.warning(t(validation))
  saving.value = true
  try {
    await props.extension.save(props.resourceId, value.value)
    message.success(t('legacy.access_policy_saved'))
  } catch (error: any) {
    message.error(error?.response?.data?.detail || error?.message || t('legacy.failed_to_save_access_policy'))
  } finally {
    saving.value = false
  }
}

watch(() => props.resourceId, load)
onMounted(load)
</script>

<template>
  <n-spin :show="loading">
    <component
      :is="extension.component"
      :model-value="value"
      @update:model-value="value = $event"
    />
    <n-space justify="end" class="resource-access-actions">
      <n-button type="primary" :loading="saving" @click="save">{{ t('legacy.save_access') }}</n-button>
    </n-space>
  </n-spin>
</template>

<style scoped>
.resource-access-actions { margin-top: 16px; }
</style>
