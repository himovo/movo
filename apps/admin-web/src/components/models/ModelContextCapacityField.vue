<script setup lang="ts">
import { computed } from 'vue';
import { NFormItem, NInputNumber } from 'naive-ui';
import { t } from '@/composables/i18n';

const props = defineProps<{ modelValue?: number }>();
const emit = defineEmits<{ (event: 'update:modelValue', value: number): void }>();
const capacityK = computed({
  get: () => (props.modelValue || 0) / 1000,
  set: (value: number | null) => emit('update:modelValue', Math.round((value || 0) * 1000)),
});
</script>

<template>
  <n-form-item :label="t('models.contextCapacity')">
    <n-input-number v-model:value="capacityK" :min="0" :max="5000" :precision="3" :show-button="false" style="width: 100%">
      <template #suffix>K tokens</template>
    </n-input-number>
  </n-form-item>
</template>
