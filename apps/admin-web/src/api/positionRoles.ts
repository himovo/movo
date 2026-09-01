import { apiClient } from './client';

export type AgentCapabilityKey =
  | 'content_generation'
  | 'image_generation'
  | 'code_generation'
  | 'browser_automation'
  | 'internal_knowledge';

export type PositionRole = {
  id: string;
  name: string;
  description: string;
  status: 'active' | 'disabled';
  protected: boolean;
  systemKey: string;
  capabilities: Record<AgentCapabilityKey, boolean>;
  toolAccessMode: 'all' | 'selected';
  toolIds: string[];
  skillAccessMode: 'all' | 'selected';
  skillIds: string[];
  memberCount: number;
  updatedAt: string;
};

export type PositionRoleDraft = Omit<PositionRole, 'id' | 'protected' | 'systemKey' | 'memberCount' | 'updatedAt'>;
export type RoleResource = { id: string; name: string; type: string };
export type CapabilityOverride = {
  id: string;
  status: 'active' | 'revoked' | 'expired';
  allowCapabilities: AgentCapabilityKey[];
  denyCapabilities: AgentCapabilityKey[];
  allowToolIds: string[];
  denyToolIds: string[];
  allowSkillIds: string[];
  denySkillIds: string[];
  effectiveAt: string;
  expiresAt: string;
  reason: string;
  createdBy: string;
  createdAt: string;
};

export type CapabilityOverrideDraft = Omit<CapabilityOverride, 'id' | 'status' | 'createdBy' | 'createdAt'>;
export async function listPositionRoles(): Promise<PositionRole[]> {
  return (await apiClient.get('/api/position-roles')).data;
}

export async function roleResourceCatalog(): Promise<{ tools: RoleResource[]; skills: RoleResource[] }> {
  return (await apiClient.get('/api/position-roles/catalog/resources')).data;
}

export async function createPositionRole(payload: PositionRoleDraft): Promise<PositionRole> {
  return (await apiClient.post('/api/position-roles', payload)).data;
}

export async function updatePositionRole(id: string, payload: PositionRoleDraft): Promise<PositionRole> {
  return (await apiClient.put(`/api/position-roles/${id}`, payload)).data;
}

export async function copyPositionRole(id: string, name: string): Promise<PositionRole> {
  return (await apiClient.post(`/api/position-roles/${id}/copy`, { name })).data;
}

export async function setPositionRoleEnabled(id: string, enabled: boolean): Promise<void> {
  await apiClient.patch(`/api/position-roles/${id}/status`, { enabled });
}

export async function deletePositionRole(id: string): Promise<void> {
  await apiClient.delete(`/api/position-roles/${id}`);
}

export async function pendingRoleAssignments(): Promise<{ count: number; migrationStatus: 'pending' | 'complete'; users: Array<{ id: string; name: string; loginName: string }> }> {
  return (await apiClient.get('/api/position-roles/assignments/pending')).data;
}

export async function completeRoleMigration(): Promise<void> {
  await apiClient.post('/api/position-roles/assignments/migration/complete');
}

export async function assignUserRoles(userId: string, primaryRoleId: string, roleIds: string[]): Promise<void> {
  await apiClient.put(`/api/position-roles/assignments/users/${userId}`, { primaryRoleId, roleIds });
}

export async function bulkAssignUserRoles(userIds: string[], primaryRoleId: string, roleIds: string[]): Promise<void> {
  await apiClient.post('/api/position-roles/assignments/bulk', { userIds, primaryRoleId, roleIds });
}

export async function listCapabilityOverrides(userId: string): Promise<CapabilityOverride[]> {
  return (await apiClient.get(`/api/position-roles/assignments/users/${userId}/overrides`)).data;
}

export async function createCapabilityOverride(userId: string, payload: CapabilityOverrideDraft): Promise<{ id: string }> {
  return (await apiClient.post(`/api/position-roles/assignments/users/${userId}/overrides`, payload)).data;
}

export async function revokeCapabilityOverride(id: string): Promise<void> {
  await apiClient.delete(`/api/position-roles/assignments/overrides/${id}`);
}
