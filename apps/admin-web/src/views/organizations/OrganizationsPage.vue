<template>
  <div class="page-stack">
    <PageIntro
      :title="t('legacy.organizations_users')"
      :description="t('legacy.control_organizations_departments_users_roles_and_permissions')"
      :tags="[t('legacy.organization_management'), t('legacy.permissions'), 'RBAC']"
    />

    <div class="page-grid">
      <div class="span-8">
        <n-card :bordered="false" size="large">
          <template #header>{{ t('legacy.organizations') }}</template>
          <n-data-table :columns="columns" :data="rows" :pagination="{ pageSize: 5 }" />
        </n-card>
      </div>
      <div class="span-4">
        <n-card :bordered="false" size="large">
          <template #header>{{ t('legacy.managed_resources') }}</template>
          <n-space vertical :size="10">
            <n-tag v-for="item in items" :key="item" round>{{ item }}</n-tag>
          </n-space>
        </n-card>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { t } from '@/composables/i18n';
import PageIntro from '@/components/PageIntro.vue';

const columns = [
  { title: t('legacy.organization_a3540e8'), key: 'name' },
  { title: t('legacy.code'), key: 'code' },
  { title: t('legacy.admin'), key: 'owner' },
  { title: t('legacy.policy'), key: 'policy' },
  { title: t('legacy.status'), key: 'status' },
];

const rows = [
  { name: '集团总部', code: 'hq', owner: '刘颖', policy: t('legacy.shared_models_own_capabilities'), status: t('legacy.active') },
  { name: '销售中心', code: 'sales', owner: '陈诚', policy: t('legacy.organization_isolation'), status: t('legacy.active') },
  { name: '交付中心', code: 'delivery', owner: '李威', policy: t('legacy.privileged_browser_automation'), status: t('legacy.pilot') },
];

const items = [t('legacy.organization_a3540e8'), t('legacy.dept'), t('legacy.user_9ba763e'), t('legacy.role'), t('legacy.user_groups'), t('legacy.sign_in_methods')];
</script>
