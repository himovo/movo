import { createRouter, createWebHistory } from 'vue-router';
import { appRoutes } from './routes';
import { useAuthStore } from '@/stores/auth';
import { useSetupStore } from '@/stores/setup';

export const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: appRoutes,
});

router.beforeEach(async (to) => {
  const setupStore = useSetupStore();
  if (to.path !== '/invite/accept') {
    try {
      await setupStore.ensureStatus();
      if (!setupStore.completed && to.path !== '/setup') {
        return '/setup';
      }
      if (setupStore.completed && to.path === '/setup') {
        return '/login';
      }
    } catch {
      if (to.path !== '/setup') return '/setup';
    }
  }
  const authStore = useAuthStore();
  if (to.meta.public) {
    return true;
  }
  await authStore.initializeSession();
  if (to.path === '/login') {
    if (authStore.isAuthenticated) {
      return '/dashboard';
    }
    return true;
  }
  if (!authStore.isAuthenticated) {
    return '/login';
  }
  return true;
});
