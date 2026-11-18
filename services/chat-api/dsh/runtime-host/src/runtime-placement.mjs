import { ASKAI_ENTERPRISE_PRESET_ID } from './official-host/overlay.mjs'

export function usesEnterpriseHost(profile) {
  return profile?.runtimePlacement === 'enterprise-host' &&
    Boolean(profile.subjectUserId) && (profile.plugins === undefined ||
      (Array.isArray(profile.plugins) && profile.plugins.length === 0))
}

export function requiresIsolatedRuntime(profile) {
  return !usesEnterpriseHost(profile) && Boolean(profile?.subjectUserId || profile?.plugins?.length)
}

export function requireEnterprisePreset(presetId, workspaceId, cwd) {
  if (presetId !== ASKAI_ENTERPRISE_PRESET_ID || workspaceId !== undefined || cwd !== undefined) {
    throw new Error('enterprise Host Runtime requires the enterprise preset without a local workspace')
  }
}
