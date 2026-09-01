import type { MenuOption } from 'naive-ui';
import { NIcon } from 'naive-ui';
import type { RouteRecordRaw } from 'vue-router';
import { computed, h, ref, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { OrganizationUsersIcon } from '@/icons/OrganizationUsersIcon';
import { appRoutes } from '@/router/routes';
import { useLocale, t } from '@/composables/i18n';

function renderMenuIcon(icon: unknown) {
  if (typeof icon === 'string') {
    return h(
      'span',
      {
        class: 'menu-symbol',
        'aria-hidden': 'true',
      },
      icon,
    );
  }

  if (icon) {
    return h(
      NIcon,
      {
        class: 'menu-symbol',
      },
      {
        default: () => h(icon as any),
      },
    );
  }

  return null;
}

function buildOptions() {
  const root = appRoutes.find((route) => route.path === '/');
  const children = (root?.children ?? []) as RouteRecordRaw[];
  const visibleRoutes = children.filter((route: RouteRecordRaw) => !route.meta?.hideInMenu && route.path);
  const options: MenuOption[] = [];
  let orgMenuAdded = false;

  for (const route of visibleRoutes) {
    const routePath = route.path as string;
    if (route.meta?.menuGroup === 'organizations') {
      if (!orgMenuAdded) {
        orgMenuAdded = true;
        options.push({
          key: '/organizations-group',
          label: t('组织与用户'),
          icon: () =>
            h(
              NIcon,
              {
                class: 'menu-symbol',
              },
              {
                default: () => h(OrganizationUsersIcon),
              },
            ),
          children: [],
        });
      }
      const group = options.find((item) => item.key === '/organizations-group');
      const childrenOptions = ((group?.children as MenuOption[] | undefined) || []);
      childrenOptions.push({
        key: routePath,
        label: t(route.meta?.title as string),
        icon: () => renderMenuIcon(route.meta?.icon),
      });
      if (group) {
        group.children = childrenOptions;
      }
      continue;
    }
    options.push({
      key: routePath,
      label: t(route.meta?.title as string),
      icon: () => renderMenuIcon(route.meta?.icon),
    });
  }

  return options;
}

export function useMenuOptions() {
  const route = useRoute();
  const router = useRouter();
  const { locale } = useLocale();

  const menuOptions = computed(() => {
    // eslint-disable-next-line no-unused-expressions
    locale.value; // Explicitly depend on locale reactive state
    return buildOptions();
  });

  const expandedKeys = ref<string[]>(route.path.startsWith('/organizations') ? ['/organizations-group'] : []);

  watch(
    () => route.path,
    (path) => {
      if (path.startsWith('/organizations') && !expandedKeys.value.includes('/organizations-group')) {
        expandedKeys.value = [...expandedKeys.value, '/organizations-group'];
      }
    },
  );

  return {
    menuOptions,
    selectedKey: computed(() => route.path),
    expandedKeys,
    handleUpdate: (key: string) => {
      router.push(key);
    },
    handleExpandedKeysUpdate: (keys: string[]) => {
      expandedKeys.value = keys;
    },
  };
}

