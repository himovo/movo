import { defineStore } from 'pinia';
import { fetchSetupStatus, type SetupServiceStatus, type SetupStatus, type SetupUrls } from '@/api/setup';

interface SetupState {
  checked: boolean;
  loading: boolean;
  completed: boolean;
  orgName: string;
  mainId: string;
  initializedAt: string;
  ready: boolean;
  services: SetupServiceStatus[];
  urls: SetupUrls;
}

function toState(status: SetupStatus): Omit<SetupState, 'checked' | 'loading'> {
  return {
    completed: Boolean(status.completed),
    orgName: status.orgName || '',
    mainId: status.mainId || '',
    initializedAt: status.initializedAt || '',
    ready: Boolean(status.ready),
    services: Array.isArray(status.services) ? status.services : [],
    urls: status.urls || { userWeb: '', adminWeb: '', desktopService: '', agentWebSocket: '' },
  };
}

export const useSetupStore = defineStore('setup', {
  state: (): SetupState => ({
    checked: false,
    loading: false,
    completed: false,
    orgName: '',
    mainId: '',
    initializedAt: '',
    ready: false,
    services: [],
    urls: { userWeb: '', adminWeb: '', desktopService: '', agentWebSocket: '' },
  }),
  actions: {
    async ensureStatus(force = false) {
      if (this.loading) return;
      if (this.checked && !force) return;
      this.loading = true;
      try {
        const status = await fetchSetupStatus();
        Object.assign(this, toState(status));
        this.checked = true;
      } finally {
        this.loading = false;
      }
    },
  },
});
