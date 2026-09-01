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
import { SettingsIcon } from '@/icons/SettingsIcon';
import { PositionRolesIcon } from '@/icons/PositionRolesIcon';
import { SystemAuditIcon } from '@/icons/SystemAuditIcon';

export const appRoutes: RouteRecordRaw[] = [
  {
    path: '/setup',
    name: 'Setup',
    component: () => import('@/views/auth/SetupPage.vue'),
    meta: {
      title: '系统初始化',
      hideInMenu: true,
      public: true,
    },
  },
  {
    path: '/login',
    name: 'Login',
    component: () => import('@/views/auth/LoginPage.vue'),
    meta: {
      title: '登录',
      hideInMenu: true,
    },
  },
  {
    path: '/invite/accept',
    name: 'InviteAccept',
    component: () => import('@/views/auth/InviteAcceptPage.vue'),
    meta: {
      title: '接受邀请',
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
        meta: { title: '工作台', icon: DashboardBarsIcon },
      },
      {
        path: '/profile',
        name: 'Profile',
        component: () => import('@/views/profile/ProfilePage.vue'),
        meta: { title: '个人中心', hideInMenu: true },
      },
      {
        path: '/skills',
        name: 'Skills',
        component: () => import('@/views/skills/SkillsPage.vue'),
        meta: { title: 'Skill管理', icon: SkillsManagerIcon },
      },
      {
        path: '/skills/:id/config',
        name: 'SkillConfig',
        component: () => import('@/views/skills/SkillConfigPage.vue'),
        meta: { title: 'Skill配置', hideInMenu: true },
      },
      {
        path: '/tools',
        name: 'Tools',
        component: () => import('@/views/tools/ToolsPage.vue'),
        meta: { title: '工具与 MCP', icon: ToolsMcpIcon },
      },
      {
        path: '/tools/new',
        name: 'ToolCreate',
        component: () => import('@/views/tools/ToolEditPage.vue'),
        meta: { title: '新增工具连接', hideInMenu: true },
      },
      {
        path: '/tools/:id/edit',
        name: 'ToolEdit',
        component: () => import('@/views/tools/ToolEditPage.vue'),
        meta: { title: '编辑工具连接', hideInMenu: true },
      },
      {
        path: '/models',
        name: 'Models',
        component: () => import('@/views/models/ModelsPage.vue'),
        meta: { title: '模型中心', icon: ModelsCenterIcon },
      },
      {
        path: '/knowledge/documents',
        name: 'KnowledgeDocuments',
        component: () => import('@/views/knowledge/KnowledgeDocumentsPage.vue'),
        meta: { title: '知识文档', icon: KnowledgeDocumentsIcon },
      },
      {
        path: '/knowledge/documents/:id',
        name: 'KnowledgeDocumentDetail',
        component: () => import('@/views/knowledge/KnowledgeDocumentPreviewPage.vue'),
        meta: { title: '文档详情', hideInMenu: true },
      },
      {
        path: '/token-stats',
        name: 'TokenStats',
        component: () => import('@/views/analytics/AnalyticsPage.vue'),
        meta: { title: 'Token 统计', icon: TokenStatsIcon },
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
        meta: { title: '账号组与账号', icon: AccountGroupsIcon, menuGroup: 'organizations' },
      },
      {
        path: '/organizations/users',
        name: 'OrganizationUsers',
        component: () => import('@/views/organizations/OrganizationUsersPage.vue'),
        meta: { title: '用户管理', icon: UserManagementIcon, menuGroup: 'organizations' },
      },
      {
        path: '/organizations/position-roles',
        name: 'PositionRoles',
        component: () => import('@/views/position-roles/PositionRolesPage.vue'),
        meta: { title: '用户岗位角色', icon: PositionRolesIcon, menuGroup: 'organizations' },
      },
      {
        path: '/organizations/traffic',
        name: 'TrafficAllocations',
        component: () => import('@/views/organizations/TrafficAllocationsPage.vue'),
        meta: { title: '流量分配', icon: TrafficAllocationIcon, menuGroup: 'organizations' },
      },
      {
        path: '/organizations',
        redirect: '/organizations/accounts',
        meta: { hideInMenu: true },
      },
      {
        path: '/system-audit',
        name: 'SystemAudit',
        component: () => import('@/views/system-audit/SystemAuditPage.vue'),
        meta: { title: '系统审计', icon: SystemAuditIcon },
      },
      {
        path: '/settings',
        name: 'Settings',
        component: () => import('@/views/settings/ExternalSearchSettingsPage.vue'),
        meta: { title: '设置', icon: SettingsIcon },
      },
      {
        path: '/settings/presentation',
        name: 'PresentationSettings',
        component: () => import('@/views/settings/ExternalSearchSettingsPage.vue'),
        meta: { title: 'PPT 生成设置', hideInMenu: true },
      },
      {
        path: '/settings/external-search',
        name: 'ExternalSearchSettings',
        component: () => import('@/views/settings/ExternalSearchSettingsPage.vue'),
        meta: { title: '设置', hideInMenu: true },
      },
      {
        path: '/settings/knowledge',
        name: 'KnowledgeSettings',
        component: () => import('@/views/settings/ExternalSearchSettingsPage.vue'),
        meta: { title: '知识库设置', hideInMenu: true },
      },
      {
        path: '/settings/page-collection',
        name: 'PageCollectionSettings',
        component: () => import('@/views/settings/ExternalSearchSettingsPage.vue'),
        meta: { title: '页面采集设置', hideInMenu: true },
      },
    ],
  },
];
