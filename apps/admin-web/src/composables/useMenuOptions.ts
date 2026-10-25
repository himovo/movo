import type { MenuOption } from 'naive-ui';
import { NIcon } from 'naive-ui';
import type { RouteRecordRaw } from 'vue-router';
import { computed, h, ref, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { OrganizationUsersIcon } from '@/icons/OrganizationUsersIcon';
import { appRoutes } from '@/router/routes';
import { useLocale, translateSourceText } from '@/composables/i18n';
import adminProductUiExtension from '@movo-admin-product-extension';

const builtInGroups = [{
  key: 'organizations',
  label: 'legacy.organizations_users',
  icon: OrganizationUsersIcon,
}];

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
  const groups = [...builtInGroups, ...(adminProductUiExtension.menuGroups ?? [])];
  const groupOptions = new Map<string, MenuOption>();

  const ensureGroup = (key: string) => {
    const existing = groupOptions.get(key);
    if (existing) return existing;
    const definition = groups.find((item) => item.key === key);
    if (!definition) return null;
    const option: MenuOption = {
      key: `/${key}-group`,
      label: translateSourceText(definition.label),
      icon: () => renderMenuIcon(definition.icon),
      children: [],
    };
    groupOptions.set(key, option);
    return option;
  };

  for (const route of visibleRoutes) {
    const routePath = route.path as string;
    const menuGroup = typeof route.meta?.menuGroup === 'string' ? route.meta.menuGroup : '';
    if (menuGroup) {
      const group = ensureGroup(menuGroup);
      if (!group) continue;
      if (!options.includes(group)) options.push(group);
      const childrenOptions = ((group?.children as MenuOption[] | undefined) || []);
      childrenOptions.push({
        key: routePath,
        label: translateSourceText(route.meta?.title as string),
        icon: () => renderMenuIcon(route.meta?.icon),
      });
      if (group) {
        group.children = childrenOptions;
      }
      continue;
    }
    options.push({
      key: routePath,
      label: translateSourceText(route.meta?.title as string),
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

  const routeGroupKey = () => {
    const group = route.meta?.menuGroup;
    return typeof group === 'string' && group ? `/${group}-group` : '';
  };
  const initialGroupKey = routeGroupKey();
  const expandedKeys = ref<string[]>(initialGroupKey ? [initialGroupKey] : []);

  watch(
    () => route.path,
    (path) => {
      const groupKey = routeGroupKey();
      if (groupKey && !expandedKeys.value.includes(groupKey)) {
        expandedKeys.value = [...expandedKeys.value, groupKey];
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
