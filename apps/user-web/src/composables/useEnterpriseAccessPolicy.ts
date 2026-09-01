import { computed, type Ref } from 'vue'
import type { AgentCapabilityKey, TenantCandidate, UserProfile } from '../api/auth'

export function agentCapabilityAllowed(profile: UserProfile | null, key: AgentCapabilityKey): boolean {
  return profile?.agentPolicy ? profile.agentPolicy.capabilities[key] !== false : true
}

export function tenantAdminAllowed(tenant: TenantCandidate): boolean {
  return tenant.spaceType === 'enterprise' && tenant.canAccessAdmin === true
}

export function personalSpaceActionsAllowed(profile: UserProfile | null): boolean {
  return profile?.spaceType === 'personal'
}

export function useEnterpriseAccessPolicy(profile: Ref<UserProfile | null>) {
  const agentPolicy = computed(() => profile.value?.agentPolicy)
  const capabilityEnabled = (key: AgentCapabilityKey) => computed(() => {
    return agentCapabilityAllowed(profile.value, key)
  })
  const canUseSkills = computed(() => {
    const policy = agentPolicy.value
    return !policy || policy.skillAccessMode === 'all' || policy.skillIds.length > 0
  })
  const canUseTools = computed(() => {
    const policy = agentPolicy.value
    return !policy || policy.toolAccessMode === 'all' || policy.toolIds.length > 0
  })
  const isEnterpriseSpace = computed(() => profile.value?.spaceType === 'enterprise')
  const canCreateOrganization = computed(() => personalSpaceActionsAllowed(profile.value))
  const canUpgradePlan = computed(() => personalSpaceActionsAllowed(profile.value))

  return {
    canUseCode: capabilityEnabled('code_generation'),
    canUseBrowser: capabilityEnabled('browser_automation'),
    canUseKnowledge: capabilityEnabled('internal_knowledge'),
    canUseSkills,
    canUseTools,
    canAccessAdmin: tenantAdminAllowed,
    isEnterpriseSpace,
    canCreateOrganization,
    canUpgradePlan,
  }
}
