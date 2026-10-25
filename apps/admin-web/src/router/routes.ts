import type { RouteRecordRaw } from 'vue-router';
import { AccountGroupsIcon } from '@/icons/AccountGroupsIcon';
import { DashboardBarsIcon } from '@/icons/DashboardBarsIcon';
import { ModelsCenterIcon } from '@/icons/ModelsCenterIcon';
import { KnowledgeDocumentsIcon } from '@/icons/KnowledgeDocumentsIcon';
import { TokenStatsIcon } from '@/icons/TokenStatsIcon';
import { TrafficAllocationIcon } from '@/icons/TrafficAllocationIcon';
import { UserManagementIcon } from '@/icons/UserManagementIcon';
import { ToolsMcpIcon } from '@/icons/ToolsMcpIcon';
import { SkillsManagerIcon } from '@/icons/SkillsManagerIcon';
import { DshPluginsIcon } from '@/icons/DshPluginsIcon';
import { SettingsIcon } from '@/icons/SettingsIcon';
import { PositionRolesIcon } from '@/icons/PositionRolesIcon';
import { SystemAuditIcon } from '@/icons/SystemAuditIcon';
import adminProductUiExtension from '@movo-admin-product-extension';

const productRoutes = adminProductUiExtension.routes ?? [];

export const appRoutes: RouteRecordRaw[] = [
  {
    path: '/setup',
    name: 'Setup',
    component: () => import('@/views/auth/SetupPage.vue'),
    meta: {
      title: 'legacy.system_setup',
      hideInMenu: true,
      public: true,
    },
  },
  {
    path: '/login',
    name: 'Login',
    component: () => import('@/views/auth/LoginPage.vue'),
    meta: {
      title: 'legacy.sign_in',
      hideInMenu: true,
    },
  },
  {
    path: '/invite/accept',
    name: 'InviteAccept',
    component: () => import('@/views/auth/InviteAcceptPage.vue'),
    meta: {
      title: 'legacy.accept_invitation',
      hideInMenu: true,
      public: true,
    },
  },
  {
    path: '/',
    component: () => import('@/layouts/BasicLayout.vue'),
    children: [
      {
        path: '',
        redirect: '/dashboard',
      },
      {
        path: '/dashboard',
        name: 'Dashboard',
        component: () => import('@/views/dashboard/DashboardPage.vue'),
        meta: { title: 'legacy.dashboard', icon: DashboardBarsIcon },
      },
      {
        path: '/profile',
        name: 'Profile',
        component: () => import('@/views/profile/ProfilePage.vue'),
        meta: { title: 'legacy.profile', hideInMenu: true },
      },
      {
        path: '/skills',
        name: 'Skills',
        component: () => import('@/views/skills/SkillsPage.vue'),
        meta: { title: 'legacy.skills', icon: SkillsManagerIcon },
      },
      {
        path: '/skills/:id/config',
        name: 'SkillConfig',
        component: () => import('@/views/skills/SkillConfigPage.vue'),
        meta: { title: 'legacy.skill_config', hideInMenu: true },
      },
      {
        path: '/dsh-plugins',
        name: 'DshPlugins',
        component: () => import('@/views/dsh-plugins/DshPluginsPage.vue'),
        meta: { title: 'dshPlugins.title', icon: DshPluginsIcon },
      },
      {
        path: '/tools',
        name: 'Tools',
        component: () => import('@/views/tools/ToolsPage.vue'),
        meta: { title: 'legacy.tools_mcp', icon: ToolsMcpIcon },
      },
      {
        path: '/tools/new',
        name: 'ToolCreate',
        component: () => import('@/views/tools/ToolEditPage.vue'),
        meta: { title: 'legacy.new_tool', hideInMenu: true },
      },
      {
        path: '/tools/:id/edit',
        name: 'ToolEdit',
        component: () => import('@/views/tools/ToolEditPage.vue'),
        meta: { title: 'legacy.edit_tool', hideInMenu: true },
      },
      {
        path: '/models',
        name: 'Models',
        component: () => import('@/views/models/ModelsPage.vue'),
        meta: { title: 'legacy.models', icon: ModelsCenterIcon },
      },
      {
        path: '/knowledge/documents',
        name: 'KnowledgeDocuments',
        component: () => import('@/views/knowledge/KnowledgeDocumentsPage.vue'),
        meta: { title: 'legacy.knowledge_documents', icon: KnowledgeDocumentsIcon },
      },
      {
        path: '/knowledge/documents/:id',
        name: 'KnowledgeDocumentDetail',
        component: () => import('@/views/knowledge/KnowledgeDocumentPreviewPage.vue'),
        meta: { title: 'legacy.document_details', hideInMenu: true },
      },
      {
        path: '/token-stats',
        name: 'TokenStats',
        component: () => import('@/views/analytics/AnalyticsPage.vue'),
        meta: { title: 'legacy.token_stats', icon: TokenStatsIcon },
      },
      {
        path: '/analytics',
        redirect: '/token-stats',
        meta: { hideInMenu: true },
      },
      {
        path: '/organizations/accounts',
        name: 'OrganizationAccounts',
        component: () => import('@/views/organizations/OrganizationAccountsPage.vue'),
        meta: { title: 'legacy.accounts_org_groups', icon: AccountGroupsIcon, menuGroup: 'organizations' },
      },
      {
        path: '/organizations/users',
        name: 'OrganizationUsers',
        component: () => import('@/views/organizations/OrganizationUsersPage.vue'),
        meta: { title: 'legacy.users', icon: UserManagementIcon, menuGroup: 'organizations' },
      },
      {
        path: '/organizations/position-roles',
        name: 'PositionRoles',
        component: () => import('@/views/position-roles/PositionRolesPage.vue'),
        meta: { title: 'legacy.position_roles', icon: PositionRolesIcon, menuGroup: 'organizations' },
      },
      {
        path: '/organizations/traffic',
        name: 'TrafficAllocations',
        component: () => import('@/views/organizations/TrafficAllocationsPage.vue'),
        meta: { title: 'legacy.traffic_allocation', icon: TrafficAllocationIcon, menuGroup: 'organizations' },
      },
      ...productRoutes,
      {
        path: '/organizations',
        redirect: '/organizations/accounts',
        meta: { hideInMenu: true },
      },
      {
        path: '/system-audit',
        name: 'SystemAudit',
        component: () => import('@/views/system-audit/SystemAuditPage.vue'),
        meta: { title: 'legacy.system_audit', icon: SystemAuditIcon },
      },
      {
        path: '/settings',
        name: 'Settings',
        component: () => import('@/views/settings/ExternalSearchSettingsPage.vue'),
        meta: { title: 'legacy.settings', icon: SettingsIcon },
      },
      {
        path: '/settings/shortcuts',
        name: 'ShortcutSettings',
        component: () => import('@/views/settings/ExternalSearchSettingsPage.vue'),
        meta: { title: 'legacy.quick_access', hideInMenu: true },
      },
      {
        path: '/settings/shortcuts/default',
        name: 'ShortcutDefaultSettings',
        component: () => import('@/views/settings/ExternalSearchSettingsPage.vue'),
        meta: { title: 'legacy.default_shortcuts_23e515b', hideInMenu: true },
      },
      {
        path: '/settings/presentation',
        name: 'PresentationSettings',
        component: () => import('@/views/settings/ExternalSearchSettingsPage.vue'),
        meta: { title: 'legacy.ppt_generation_settings', hideInMenu: true },
      },
      {
        path: '/settings/external-search',
        name: 'ExternalSearchSettings',
        component: () => import('@/views/settings/ExternalSearchSettingsPage.vue'),
        meta: { title: 'legacy.settings', hideInMenu: true },
      },
      {
        path: '/settings/knowledge',
        name: 'KnowledgeSettings',
        component: () => import('@/views/settings/ExternalSearchSettingsPage.vue'),
        meta: { title: 'knowledgeSource.pageTitle', hideInMenu: true },
      },
      {
        path: '/settings/page-collection',
        name: 'PageCollectionSettings',
        component: () => import('@/views/settings/ExternalSearchSettingsPage.vue'),
        meta: { title: 'legacy.page_collection_settings', hideInMenu: true },
      },
      {
        path: '/settings/topic-admission',
        name: 'TopicAdmissionSettings',
        component: () => import('@/views/settings/ExternalSearchSettingsPage.vue'),
        meta: { title: 'taskAdmission.title', hideInMenu: true },
      },
    ],
  },
];
