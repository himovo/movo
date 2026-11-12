import type { Component } from 'vue'
import type { RouteRecordRaw } from 'vue-router'

export interface AdminProductMenuGroup {
  key: string
  label: string
  icon?: Component
}

export interface AdminProductSettingsLink {
  path: string
  label: { zh: string; en: string }
  icon?: Component
}

export interface ModelAccessUiExtension {
  component: Component
  createValue: (grouped?: boolean) => unknown
  load: (modelId: string) => Promise<unknown>
  save: (modelId: string, value: unknown) => Promise<void>
  validate?: (value: unknown) => string | null
}

export interface ResourceAccessUiExtension {
  component: Component
  createValue: () => unknown
  load: (resourceId: string) => Promise<unknown>
  save: (resourceId: string, value: unknown) => Promise<void>
  validate?: (value: unknown) => string | null
}

export interface TopicRuleAudienceUiExtension {
  component: Component
  createValue: () => unknown
  load: (ruleId: string) => Promise<unknown>
  save: (ruleId: string, value: unknown) => Promise<void>
  validate?: (value: unknown) => string | null
  loadSummaries?: (ruleIds: string[]) => Promise<Record<string, unknown>>
  summarize?: (value: unknown) => { key: string; count?: number }
}

export interface AdminProductUiExtension {
  extensionId: string
  productEditionLabel?: string
  productEditionTagType?: 'default' | 'error' | 'info' | 'success' | 'warning'
  dashboardEditionBadge?: Component
  dashboardBillingActions?: Component
  knowledgeDirectoryPermissions?: Component
  knowledgeDocumentPermissions?: Component
  shortcutSettingsExtension?: Component
  runtimeSettingsExtension?: Component
  topicRuleAudience?: TopicRuleAudienceUiExtension
  topicRuleAudienceBadge?: Component
  modelAccess?: ModelAccessUiExtension
  modelGroupAccess?: ModelAccessUiExtension
  skillAccess?: ResourceAccessUiExtension
  toolAccess?: ResourceAccessUiExtension
  pluginAccess?: ResourceAccessUiExtension
  menuGroups?: AdminProductMenuGroup[]
  routes?: RouteRecordRaw[]
  settingsLinks?: AdminProductSettingsLink[]
}
