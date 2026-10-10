import axios from 'axios';
import { useAuthStore } from '@/stores/auth';
import { expireAdminSession, isAdminLoginRequest } from './adminSessionExpiry';

export const apiClient = axios.create({
  baseURL: import.meta.env.VITE_ADMIN_API_BASE_URL || '/admin-api',
  timeout: 10000,
});

apiClient.interceptors.request.use((config) => {
  const authStore = useAuthStore();
  if (authStore.token) {
    config.headers.Authorization = `Bearer ${authStore.token}`;
  }
  return config;
});

apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    if (axios.isAxiosError(error)) {
      const status = error.response?.status;
      if (status === 401 && !isAdminLoginRequest(error.config?.url)) {
        expireAdminSession();
      }
    }
    return Promise.reject(error);
  },
);
