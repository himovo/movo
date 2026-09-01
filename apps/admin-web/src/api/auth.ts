import { apiClient } from './client';
import type { AdminProfile } from '@/stores/auth';

interface LoginPayload {
  username: string;
  password: string;
  mainId?: string;
}

export interface TenantCandidate {
  mainId: string;
  orgName: string;
  roleName: string;
  displayName: string;
  username: string;
}

interface LoginResponse {
  token: string;
  profile: AdminProfile;
  requiresTenantSelection?: false;
}

export interface TenantSelectionResponse {
  requiresTenantSelection: true;
  challengeToken: string;
  candidates: TenantCandidate[];
  expiresAt?: string;
}

export async function login(payload: LoginPayload) {
  const { data } = await apiClient.post<LoginResponse | TenantSelectionResponse>('/api/auth/login', payload);
  return data;
}

export async function selectTenantLogin(payload: { challengeToken: string; mainId: string }) {
  const { data } = await apiClient.post<LoginResponse>('/api/auth/login/select-tenant', payload);
  return data;
}

export async function fetchCurrentProfile() {
  const { data } = await apiClient.get<AdminProfile & { username: string }>('/api/auth/me');
  return data;
}

export async function updateCurrentProfile(payload: { name: string; email: string; phone: string }) {
  const { data } = await apiClient.patch<AdminProfile & { username: string }>('/api/auth/me', payload);
  return data;
}

export async function changeCurrentPassword(payload: { currentPassword: string; newPassword: string }) {
  const { data } = await apiClient.post<{ success: boolean }>('/api/auth/me/password', payload);
  return data;
}

export async function uploadCurrentAvatar(file: File) {
  const formData = new FormData();
  formData.append('file', file);
  const { data } = await apiClient.post<AdminProfile & { username: string }>('/api/auth/me/avatar', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  });
  return data;
}

export async function logout() {
  const { data } = await apiClient.post<{ success: boolean }>('/api/auth/logout');
  return data;
}
