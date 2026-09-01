import { apiClient } from './client';

export interface DepartmentNode {
  id: string;
  name: string;
  code: string;
  status: 'active' | 'disabled';
  parentId: string | null;
  userCount: number;
  children: DepartmentNode[];
}

export interface DirectoryUserItem {
  id: string;
  name: string;
  mobile: string;
  email: string;
  status: 'active' | 'disabled';
  source: 'local' | 'dingtalk' | 'wecom' | 'feishu';
  sourceUserId: string;
  loginName: string;
  primaryDepartmentId: string;
  primaryDepartmentName: string;
  customFields: Record<string, unknown>;
  updatedAt: string;
  positionRoles: Array<{ id: string; name: string; isPrimary: boolean }>;
  pendingPositionRole: boolean;
}

export interface UserFieldDef {
  id: string;
  fieldKey: string;
  label: string;
  fieldType: 'text' | 'textarea' | 'select' | 'multiselect';
  required: boolean;
  options: string[];
  rows: number;
  masked: boolean;
  enabled: boolean;
  sort: number;
  updatedAt: string;
}

export interface UserIdentity {
  id: string;
  provider: 'dingtalk' | 'wecom' | 'feishu';
  providerUserId: string;
  unionId: string;
  corpId: string;
  tenantKey: string;
  isPrimary: boolean;
  bindStatus: 'bound' | 'pending' | 'conflict';
  lastSyncAt: string;
}

export interface UserInviteLinkResult {
  inviteUrl: string;
  token: string;
  purpose: 'register' | 'set_password';
  expiresAt: string;
}

export interface InviteLinkDetail {
  purpose: 'register' | 'set_password';
  expiresAt: string;
  orgName?: string;
  defaultDepartmentId?: string | null;
  primaryRoleId?: string;
  roleIds?: string[];
  user: {
    name: string;
    mobile: string;
    email: string;
    loginName: string;
  };
}

export async function fetchDepartmentTree() {
  const { data } = await apiClient.get<DepartmentNode[]>('/api/directory/departments/tree');
  return data;
}

export async function createDepartment(payload: { name: string; parentId?: string | null; status: 'active' | 'disabled' }) {
  const { data } = await apiClient.post('/api/directory/departments', payload);
  return data;
}

export async function updateDepartment(id: string, payload: { name: string; status: 'active' | 'disabled' }) {
  const { data } = await apiClient.put(`/api/directory/departments/${id}`, payload);
  return data;
}

export async function moveDepartment(id: string, payload: { parentId?: string | null }) {
  const { data } = await apiClient.post(`/api/directory/departments/${id}/move`, payload);
  return data;
}

export async function deleteDepartment(id: string) {
  const { data } = await apiClient.delete(`/api/directory/departments/${id}`);
  return data;
}

export async function fetchUsers(params: {
  departmentId?: string;
  keyword?: string;
  statusFilter?: string;
  sourceFilter?: string;
}) {
  const { data } = await apiClient.get<DirectoryUserItem[]>('/api/directory/users', { params });
  return data;
}

export async function createUser(payload: {
  name: string;
  mobile: string;
  email: string;
  status: 'active' | 'disabled';
  source: 'local' | 'dingtalk' | 'wecom' | 'feishu';
  sourceUserId: string;
  primaryDepartmentId: string;
  departmentIds: string[];
  loginName: string;
  initialPassword: string;
  primaryRoleId: string;
  roleIds: string[];
}) {
  const { data } = await apiClient.post('/api/directory/users', payload);
  return data;
}

export async function updateUser(
  id: string,
  payload: {
    name: string;
    mobile: string;
    email: string;
    status: 'active' | 'disabled';
    source: 'local' | 'dingtalk' | 'wecom' | 'feishu';
    sourceUserId: string;
    primaryDepartmentId: string;
    departmentIds: string[];
    loginName: string;
    resetPassword: string;
    primaryRoleId: string;
    roleIds: string[];
  },
) {
  const { data } = await apiClient.put(`/api/directory/users/${id}`, payload);
  return data;
}

export async function deleteUser(id: string) {
  const { data } = await apiClient.delete(`/api/directory/users/${id}`);
  return data;
}

export async function disableUser(id: string) {
  const { data } = await apiClient.post(`/api/directory/users/${id}/disable`);
  return data;
}

export async function enableUser(id: string) {
  const { data } = await apiClient.post(`/api/directory/users/${id}/enable`);
  return data;
}

export async function createOrgInviteLink(payload: { defaultDepartmentId?: string | null; expiresHours?: number; primaryRoleId: string; roleIds: string[] }) {
  const { data } = await apiClient.post<UserInviteLinkResult>('/api/directory/invites', payload || {});
  return data;
}

export async function fetchInviteLinkDetail(token: string) {
  const { data } = await apiClient.get<InviteLinkDetail>(`/api/directory/invite-links/${token}`);
  return data;
}

export async function acceptInviteLink(
  token: string,
  payload: { name?: string; mobile?: string; email?: string; loginName: string; password: string },
) {
  const { data } = await apiClient.post<{ success: boolean }>(`/api/directory/invite-links/${token}/accept`, payload);
  return data;
}

export async function fetchUserFieldDefs() {
  const { data } = await apiClient.get<UserFieldDef[]>('/api/directory/user-fields');
  return data;
}

export async function createUserFieldDef(payload: {
  fieldKey: string;
  label: string;
  fieldType: UserFieldDef['fieldType'];
  required: boolean;
  options: string[];
  rows: number;
  masked: boolean;
  enabled: boolean;
  sort: number;
}) {
  const { data } = await apiClient.post('/api/directory/user-fields', payload);
  return data;
}

export async function updateUserFieldDef(id: string, payload: {
  fieldKey: string;
  label: string;
  fieldType: UserFieldDef['fieldType'];
  required: boolean;
  options: string[];
  rows: number;
  masked: boolean;
  enabled: boolean;
  sort: number;
}) {
  const { data } = await apiClient.put(`/api/directory/user-fields/${id}`, payload);
  return data;
}

export async function deleteUserFieldDef(id: string) {
  const { data } = await apiClient.delete(`/api/directory/user-fields/${id}`);
  return data;
}

export async function fetchUserCustomFields(userId: string) {
  const { data } = await apiClient.get<{ fields: Array<UserFieldDef & { value: unknown }> }>(`/api/directory/users/${userId}/custom-fields`);
  return data;
}

export async function updateUserCustomFields(userId: string, values: Record<string, unknown>) {
  const { data } = await apiClient.put(`/api/directory/users/${userId}/custom-fields`, { values });
  return data;
}

export async function fetchUserIdentities(userId: string) {
  const { data } = await apiClient.get<UserIdentity[]>(`/api/directory/users/${userId}/identities`);
  return data;
}

export async function addUserIdentity(
  userId: string,
  payload: {
    provider: UserIdentity['provider'];
    providerUserId: string;
    unionId: string;
    corpId: string;
    tenantKey: string;
    isPrimary: boolean;
    bindStatus: UserIdentity['bindStatus'];
  },
) {
  const { data } = await apiClient.post(`/api/directory/users/${userId}/identities`, payload);
  return data;
}

export async function deleteUserIdentity(identityId: string) {
  const { data } = await apiClient.delete(`/api/directory/user-identities/${identityId}`);
  return data;
}

export async function fetchAuditLogs(page = 1, pageSize = 20) {
  const { data } = await apiClient.get<{
    page: number;
    pageSize: number;
    total: number;
    items: Array<{
      id: string;
      operator: string;
      action: string;
      targetType: string;
      targetId: string;
      payload: Record<string, unknown>;
      createdAt: string;
    }>;
  }>('/api/directory/audit-logs', { params: { page, pageSize } });
  return data;
}
