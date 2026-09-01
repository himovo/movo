<template>
  <n-config-provider
    :theme="themeInstance"
    :theme-overrides="themeOverrides"
    :locale="naiveLocale"
    :date-locale="naiveDateLocale"
  >
    <n-dialog-provider>
      <n-message-provider>
        <router-view />
      </n-message-provider>
    </n-dialog-provider>
  </n-config-provider>
</template>

<script setup lang="ts">
import { computed, watch } from 'vue';
import { zhCN, dateZhCN, enUS, dateEnUS, darkTheme } from 'naive-ui';
import { useLocale } from '@/composables/i18n';
import { useTheme } from '@/composables/theme';

const { locale } = useLocale();
const { activeTheme } = useTheme();

const themeInstance = computed(() => {
  return activeTheme.value === 'dark' ? darkTheme : null;
});

const naiveLocale = computed(() => {
  return locale.value === 'en-US' ? enUS : zhCN;
});

const naiveDateLocale = computed(() => {
  return locale.value === 'en-US' ? dateEnUS : dateZhCN;
});

watch(
  locale,
  (value) => {
    document.documentElement.lang = value;
  },
  { immediate: true },
);

const themeOverrides = {
  common: {
    primaryColor: '#366AFF',
    primaryColorHover: '#5a84ff',
    primaryColorPressed: '#2757e6',
    borderRadius: '14px',
  },
  Card: {
    borderRadius: '18px',
  },
};
</script>
