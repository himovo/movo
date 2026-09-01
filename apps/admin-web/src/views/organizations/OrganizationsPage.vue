<template>
  <div class="page-stack">
    <PageIntro
      :title="t('组织与用户')"
      :description="t('面向组织、部门、用户、角色和权限的控制面。')"
      :tags="[t('组织管理'), t('权限'), 'RBAC']"
    />

    <div class="page-grid">
      <div class="span-8">
        <n-card :bordered="false" size="large">
          <template #header>{{ t('组织列表') }}</template>
          <n-data-table :columns="columns" :data="rows" :pagination="{ pageSize: 5 }" />
        </n-card>
      </div>
      <div class="span-4">
        <n-card :bordered="false" size="large">
          <template #header>{{ t('本模块承载的内容') }}</template>
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
  { title: t('组织'), key: 'name' },
  { title: t('编码'), key: 'code' },
  { title: t('管理员'), key: 'owner' },
  { title: t('策略'), key: 'policy' },
  { title: t('状态'), key: 'status' },
];

const rows = [
  { name: '集团总部', code: 'hq', owner: '刘颖', policy: t('共享模型 + 自有能力'), status: t('启用') },
  { name: '销售中心', code: 'sales', owner: '陈诚', policy: t('组织隔离'), status: t('启用') },
  { name: '交付中心', code: 'delivery', owner: '李威', policy: t('高权限浏览器自动化'), status: t('试运行') },
];

const items = [t('组织'), t('部门'), t('用户'), t('角色'), t('用户组'), t('登录方式')];
</script>
