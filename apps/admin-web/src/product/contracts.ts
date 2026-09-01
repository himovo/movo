import type { Component } from 'vue'

export interface AdminProductUiExtension {
  extensionId: string
  dashboardBillingActions?: Component
}
