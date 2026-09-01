import { createPinia } from 'pinia';
import { createApp } from 'vue';
import { create, NAvatar, NBadge, NButton, NCard, NCheckbox, NConfigProvider, NDataTable, NDescriptions, NDescriptionsItem, NDialogProvider, NDivider, NDrawer, NDrawerContent, NDropdown, NEmpty, NForm, NFormItem, NGrid, NGridItem, NIcon, NInput, NInputNumber, NLayout, NLayoutContent, NLayoutFooter, NLayoutHeader, NLayoutSider, NMenu, NMessageProvider, NModal, NNumberAnimation, NPageHeader, NPagination, NPopover, NRadio, NRadioButton, NRadioGroup, NResult, NSelect, NSpace, NSpin, NStatistic, NSwitch, NTabPane, NTabs, NTag, NThing, NTree } from 'naive-ui';
import App from './App.vue';
import { router } from './router';

export function bootstrap() {
  const app = createApp(App);
  const pinia = createPinia();
  const naive = create({
    components: [
      NButton,
      NAvatar,
      NBadge,
      NCard,
      NCheckbox,
      NConfigProvider,
      NDataTable,
      NDescriptions,
      NDescriptionsItem,
      NDialogProvider,
      NDivider,
      NDrawer,
      NDrawerContent,
      NDropdown,
      NEmpty,
      NForm,
      NFormItem,
      NGrid,
      NGridItem,
      NIcon,
      NInput,
      NInputNumber,
      NLayout,
      NLayoutContent,
      NLayoutFooter,
      NLayoutHeader,
      NLayoutSider,
      NMenu,
      NMessageProvider,
      NModal,
      NNumberAnimation,
      NPageHeader,
      NPagination,
      NPopover,
      NRadio,
      NRadioButton,
      NRadioGroup,
      NResult,
      NSelect,
      NSpace,
      NSpin,
      NStatistic,
      NSwitch,
      NTabPane,
      NTabs,
      NTag,
      NThing,
      NTree,
    ],
  });

  app.use(pinia);
  app.use(router);
  app.use(naive);
  app.mount('#app');
}
