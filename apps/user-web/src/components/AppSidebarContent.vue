<script setup lang="ts">
import AppSidebarLayout from './AppSidebarLayout.vue'
import SessionHistorySidebar from './SessionHistorySidebar.vue'
import WebFeatureNavigation from './WebFeatureNavigation.vue'
import AccountMenu from './AccountMenu.vue'
import PluginShortcutNavigation from './plugins/PluginShortcutNavigation.vue'

type LayoutProps = InstanceType<typeof AppSidebarLayout>['$props']
type HistoryProps = InstanceType<typeof SessionHistorySidebar>['$props']
type FeatureProps = InstanceType<typeof WebFeatureNavigation>['$props']
type AccountProps = InstanceType<typeof AccountMenu>['$props']

export interface AppSidebarBindings {
  visible: boolean
  layout: LayoutProps
  history: HistoryProps
  showFeatures: boolean
  pluginShortcuts: { mainId: string; userId: string; loggedIn: boolean; currentView: string }
  features: FeatureProps
  account: AccountProps
}

defineProps<{ bindings: AppSidebarBindings }>()
</script>

<template>
  <AppSidebarLayout v-show="bindings.visible" v-bind="bindings.layout">
    <template #history>
      <SessionHistorySidebar v-bind="bindings.history">
        <template #desktop-plugin-shortcuts>
          <PluginShortcutNavigation v-if="bindings.layout.desktop" v-bind="bindings.pluginShortcuts" embedded />
        </template>
      </SessionHistorySidebar>
    </template>
    <template #features>
      <PluginShortcutNavigation v-if="!bindings.layout.desktop" v-bind="bindings.pluginShortcuts" />
      <WebFeatureNavigation v-if="bindings.showFeatures" v-bind="bindings.features" />
    </template>
    <template #account-menu>
      <AccountMenu v-bind="bindings.account" />
    </template>
  </AppSidebarLayout>
</template>
