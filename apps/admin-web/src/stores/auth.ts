import { defineStore } from 'pinia';
import axios from 'axios';
import { fetchCurrentProfile, logout as logoutApi } from '@/api/auth';

export interface AdminProfile {
  name: string;
  roleName: string;
  orgName: string;
  username?: string;
  email?: string;
  phone?: string;
  avatarUrl?: string;
  avatarUpdatedAt?: string;
  lastLoginAt?: string;
  mainId?: string;
}

interface AuthState {
  token: string;
  profile: AdminProfile | null;
  initialized: boolean;
}

const STORAGE_KEY = 'askai-admin-auth';

function readState(): AuthState {
  if (typeof window === 'undefined') {
    return { token: '', profile: null, initialized: false };
  }
  const raw = localStorage.getItem(STORAGE_KEY);
  if (!raw) {
    return { token: '', profile: null, initialized: false };
  }
  try {
    const parsed = JSON.parse(raw) as Partial<AuthState>;
    return {
      token: parsed.token || '',
      profile: parsed.profile || null,
      initialized: false,
    };
  } catch {
    return { token: '', profile: null, initialized: false };
  }
}

function persistState(state: Pick<AuthState, 'token' | 'profile'>) {
  if (typeof window === 'undefined') {
    return;
  }
  localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
}

export const useAuthStore = defineStore('auth', {
  state: (): AuthState => readState(),
  getters: {
    isAuthenticated: (state) => Boolean(state.token),
  },
  actions: {
    clearSession() {
      this.token = '';
      this.profile = null;
      this.initialized = true;
      persistState({ token: '', profile: null });
    },
    login(payload: Pick<AuthState, 'token' | 'profile'>) {
      this.token = payload.token;
      this.profile = payload.profile;
      this.initialized = true;
      persistState({ token: this.token, profile: this.profile });
    },
    setProfile(profile: AdminProfile) {
      this.profile = profile;
      persistState({ token: this.token, profile: this.profile });
    },
    async initializeSession() {
      if (typeof window !== 'undefined') {
        const params = new URLSearchParams(window.location.search);
        const ssoToken = params.get('sso_token');
        if (ssoToken) {
          this.token = ssoToken;
          this.profile = null;
          this.initialized = false;
          persistState({ token: this.token, profile: null });

          const url = new URL(window.location.href);
          url.searchParams.delete('sso_token');
          window.history.replaceState({}, '', url.toString());
        }
      }

      if (this.initialized) {
        return;
      }
      if (!this.token) {
        this.initialized = true;
        return;
      }
      try {
        const profile = await fetchCurrentProfile();
        this.setProfile({
          name: profile.name,
          roleName: profile.roleName,
          orgName: profile.orgName,
          username: profile.username,
          email: profile.email,
          phone: profile.phone,
          avatarUrl: profile.avatarUrl,
          avatarUpdatedAt: profile.avatarUpdatedAt,
          lastLoginAt: profile.lastLoginAt,
          mainId: profile.mainId,
        });
      } catch (error) {
        // Only clear local auth on real auth failures.
        // Temporary network issues / 5xx should not force logout.
        if (axios.isAxiosError(error)) {
          const status = error.response?.status;
          if (status === 401 || status === 403) {
            this.clearSession();
          }
        }
      } finally {
        this.initialized = true;
        persistState({ token: this.token, profile: this.profile });
      }
    },
    async logout() {
      if (this.token) {
        try {
          await logoutApi();
        } catch {
          // Ignore remote logout failures and still clear local state.
        }
      }
      this.clearSession();
    },
  },
});
