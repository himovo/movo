<template>
  <n-select
    :value="modelValue || null"
    :options="selectOptions"
    :loading="loading"
    :placeholder="placeholder"
    filterable
    clearable
    :consistent-menu-width="false"
    @update:value="updateValue"
  />
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';
import type { SelectOption } from 'naive-ui';
import { fetchModelInstances, type ModelInstanceItem } from '@/api/models';
import { t } from '@/composables/i18n';

const props = defineProps<{
  modelValue: string;
  capability: string;
  placeholder: string;
}>();

const emit = defineEmits<{
  (event: 'update:modelValue', value: string): void;
}>();

const loading = ref(false);
const instances = ref<ModelInstanceItem[]>([]);

const availableInstances = computed(() => instances.value.filter(
  item => item.status === 'active' && item.capabilities.includes(props.capability),
));

const selectOptions = computed<SelectOption[]>(() => {
  const options: SelectOption[] = availableInstances.value.map(item => ({
    label: `${item.displayName} · ${item.providerName} / ${item.modelName}`,
    value: item.id,
  }));
  if (props.modelValue && !options.some(item => item.value === props.modelValue)) {
    options.unshift({
      label: t('已配置模型不可用，请重新选择'),
      value: props.modelValue,
      disabled: true,
    });
  }
  return options;
});

function updateValue(value: string | null) {
  emit('update:modelValue', String(value || ''));
}

onMounted(async () => {
  loading.value = true;
  try {
    instances.value = await fetchModelInstances();
  } finally {
    loading.value = false;
  }
});
</script>
