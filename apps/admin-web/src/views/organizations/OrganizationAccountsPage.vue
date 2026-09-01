<template>
  <div class="page-stack account-page">
    <n-card class="account-card" :bordered="false" size="large">
      <div class="toolbar">
        <n-space align="center" :size="10">
          <n-input v-model:value="filters.keyword" :placeholder="t('搜索账号/姓名/邮箱')" clearable />
          <n-select
            v-model:value="filters.groupCode"
            :options="groupOptions"
            :placeholder="t('账号组')"
            clearable
            style="width: 180px"
          />
          <n-select
            v-model:value="filters.status"
            :options="statusOptions"
            :placeholder="t('状态')"
            clearable
            style="width: 130px"
          />
        </n-space>
        <n-space :size="10">
          <n-button @click="groupManagerVisible = true">
            <template #icon>
              <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2" />
                <circle cx="9" cy="7" r="4" />
                <path d="M22 21v-2a4 4 0 0 0-3-3.87" />
                <path d="M16 3.13a4 4 0 0 1 0 7.75" />
              </svg>
            </template>
            {{ t('账号组管理') }}
          </n-button>
          <n-button type="primary" @click="openCreateAccount">
            <template #icon>
              <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2" />
                <circle cx="9" cy="7" r="4" />
                <line x1="19" y1="8" x2="19" y2="14" />
                <line x1="22" y1="11" x2="16" y2="11" />
              </svg>
            </template>
            {{ t('新增账号') }}
          </n-button>
        </n-space>
      </div>
      <div class="table-area">
        <n-data-table
          class="account-table"
          :columns="accountColumns"
          :data="pagedAccounts"
          :pagination="false"
          :bordered="false"
          flex-height
          :scroll-x="accountTableScrollX"
          :scrollbar-props="tableScrollbarProps"
        />
      </div>
      <div class="pager-row">
        <span class="pager-total">{{ t('共 {count} 条', { count: filteredAccounts.length }) }}</span>
        <n-pagination
          v-model:page="currentPage"
          :page-size="pageSize"
          :page-sizes="[10, 20, 50]"
          :item-count="filteredAccounts.length"
          show-size-picker
        />
      </div>
    </n-card>
  </div>

  <n-modal v-model:show="groupManagerVisible" preset="card" :title="t('账号组管理')" style="width: 860px">
    <div class="toolbar group-toolbar">
      <span class="section-muted">{{ t('简易版：新增、编辑、删除账号组') }}</span>
      <n-button type="primary" size="small" @click="openCreateGroup">
        <template #icon>
          <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M5 12h14" />
            <path d="M12 5v14" />
          </svg>
        </template>
        {{ t('新增账号组') }}
      </n-button>
    </div>
    <n-data-table :columns="groupColumns" :data="groups" :pagination="{ pageSize: 6 }" :bordered="false" />
  </n-modal>

  <n-modal v-model:show="groupEditorVisible" preset="card" :title="groupEditorTitle" style="width: 560px">
    <n-form :model="groupForm" label-placement="left" label-width="84">
      <n-form-item :label="t('账号组名称')">
        <n-input v-model:value="groupForm.name" :placeholder="t('如: 组织运营管理员组')" />
      </n-form-item>
      <n-form-item :label="t('说明')">
        <n-input v-model:value="groupForm.description" type="textarea" :rows="3" :placeholder="t('账号组说明')" />
      </n-form-item>
    </n-form>
    <template #footer>
      <n-space justify="end">
        <n-button @click="groupEditorVisible = false">{{ t('取消') }}</n-button>
        <n-button type="primary" :loading="saving" @click="saveGroup">{{ t('保存') }}</n-button>
      </n-space>
    </template>
  </n-modal>

  <n-modal v-model:show="accountEditorVisible" preset="card" :title="accountEditorTitle" style="width: 620px">
    <n-form :model="accountForm" label-placement="left" label-width="84">
      <n-grid :cols="2" :x-gap="12">
        <n-grid-item>
          <n-form-item :label="t('登录账号')" required>
            <n-input
              v-model:value="accountForm.username"
              :disabled="accountEditorMode === 'edit'"
              :placeholder="t('如: wang.li')"
            />
          </n-form-item>
        </n-grid-item>
        <n-grid-item>
          <n-form-item :label="t('姓名')" required>
            <n-input v-model:value="accountForm.displayName" :placeholder="t('如: 王丽')" />
          </n-form-item>
        </n-grid-item>
        <n-grid-item>
          <n-form-item :label="t('邮箱')">
            <n-input v-model:value="accountForm.email" :placeholder="t('如: wang.li@company.com')" />
          </n-form-item>
        </n-grid-item>
        <n-grid-item>
          <n-form-item :label="t('手机号')">
            <n-input v-model:value="accountForm.phone" :placeholder="t('如: 13800000000')" />
          </n-form-item>
        </n-grid-item>
        <n-grid-item>
          <n-form-item :label="t('账号组')" required>
            <n-select v-model:value="accountForm.groupCode" :options="groupOptions" />
          </n-form-item>
        </n-grid-item>
        <n-grid-item>
          <n-form-item :label="t('角色')" required>
            <n-select v-model:value="accountForm.roleName" :options="roleOptions" />
          </n-form-item>
        </n-grid-item>
        <n-grid-item>
          <n-form-item :label="t('状态')">
            <n-select v-model:value="accountForm.status" :options="statusOptions" />
          </n-form-item>
        </n-grid-item>
        <n-grid-item v-if="accountEditorMode === 'create'" :span="2">
          <n-form-item :label="t('初始密码')" required>
            <n-input
              v-model:value="accountForm.initialPassword"
              type="password"
              show-password-on="click"
              :placeholder="t('至少 10 位')"
            />
          </n-form-item>
          <div class="section-muted">{{ t('新建账号需设置初始密码，创建后可直接用于登录后台。') }}</div>
        </n-grid-item>
      </n-grid>
    </n-form>
    <template #footer>
      <n-space justify="end">
        <n-button @click="accountEditorVisible = false">{{ t('取消') }}</n-button>
        <n-button type="primary" :loading="saving" @click="saveAccount">{{ t('保存') }}</n-button>
      </n-space>
    </template>
  </n-modal>
</template>

<script setup lang="ts">
import type { DataTableColumns } from 'naive-ui';
import { useMessage } from 'naive-ui';
import { computed, h, onMounted, ref, watch } from 'vue';
import axios from 'axios';
import { t } from '@/composables/i18n';
import { formatAdminDateTime } from '@/composables/adminTimezone';
import {
  createAccount,
  createAccountGroup,
  deleteAccount,
  deleteAccountGroup,
  fetchAccountGroups,
  fetchAccounts,
  updateAccount,
  updateAccountGroup,
  type AccountGroupItem,
  type AccountItem,
} from '@/api/organizations';

type StatusType = 'active' | 'disabled';

interface GroupForm {
  id: string;
  name: string;
  description: string;
}

interface AccountForm {
  id: string;
  username: string;
  displayName: string;
  email: string;
  phone: string;
  groupCode: string;
  roleName: string;
  status: StatusType;
  initialPassword: string;
}

const message = useMessage();
const saving = ref(false);
const groups = ref<AccountGroupItem[]>([]);
const accounts = ref<AccountItem[]>([]);

const roleOptions = computed(() => [
  { label: t('平台管理员'), value: '平台管理员' },
  { label: t('组织管理员'), value: '组织管理员' },
  { label: t('审计员'), value: '审计员' },
  { label: t('运营人员'), value: '运营人员' },
]);

const statusOptions = computed(() => [
  { label: t('启用'), value: 'active' },
  { label: t('禁用'), value: 'disabled' },
]);

const filters = ref({
  keyword: '',
  groupCode: null as string | null,
  status: null as StatusType | null,
});

const groupManagerVisible = ref(false);
const groupEditorVisible = ref(false);
const groupEditorMode = ref<'create' | 'edit'>('create');
const groupForm = ref<GroupForm>({
  id: '',
  name: '',
  description: '',
});

const accountEditorVisible = ref(false);
const accountEditorMode = ref<'create' | 'edit'>('create');
const accountForm = ref<AccountForm>({
  id: '',
  username: '',
  displayName: '',
  email: '',
  phone: '',
  groupCode: '',
  roleName: '组织管理员',
  status: 'active',
  initialPassword: '',
});

const groupEditorTitle = computed(() => (groupEditorMode.value === 'create' ? t('新增账号组') : t('编辑账号组')));
const accountEditorTitle = computed(() =>
  accountEditorMode.value === 'create' ? t('新增账号') : t('编辑账号'),
);

const groupOptions = computed(() =>
  groups.value.map((item) => ({
    label: item.name,
    value: item.code,
  })),
);

const filteredAccounts = computed(() => {
  return accounts.value.filter((row) => {
    const keyword = filters.value.keyword.trim().toLowerCase();
    const hitKeyword =
      !keyword ||
      [row.username, row.displayName, row.email].some((field) => field.toLowerCase().includes(keyword));
    const hitGroup = !filters.value.groupCode || row.groupCode === filters.value.groupCode;
    const hitStatus = !filters.value.status || row.status === filters.value.status;
    return hitKeyword && hitGroup && hitStatus;
  });
});
const currentPage = ref(1);
const pageSize = 10;
const tableScrollbarProps = { trigger: 'none' as const };
const accountTableScrollX = 1400;

const pagedAccounts = computed(() => {
  const start = (currentPage.value - 1) * pageSize;
  return filteredAccounts.value.slice(start, start + pageSize);
});
watch(filteredAccounts, (rows) => {
  const nextPageCount = Math.max(1, Math.ceil(rows.length / pageSize));
  if (currentPage.value > nextPageCount) {
    currentPage.value = nextPageCount;
  }
});

const groupColumns = computed<DataTableColumns<AccountGroupItem>>(() => [
  { title: t('账号组名称'), key: 'name' },
  { title: t('说明'), key: 'description' },
  { title: t('账号数'), key: 'accountCount' },
  {
    title: t('操作'),
    key: 'actions',
    width: 160,
    render: (row) =>
      h('div', { class: 'action-row' }, [
        h(
          'button',
          {
            class: 'action-link',
            onClick: () => openEditGroup(row),
          },
          t('编辑'),
        ),
        h(
          'button',
          {
            class: 'action-link danger',
            onClick: () => removeGroup(row),
          },
          t('删除'),
        ),
      ]),
  },
]);

const accountColumns = computed<DataTableColumns<AccountItem>>(() => [
  { title: t('登录账号'), key: 'username', width: 150, fixed: 'left' },
  { title: t('姓名'), key: 'displayName', width: 130, fixed: 'left' },
  { title: t('账号组'), key: 'groupName', width: 160 },
  { title: t('角色'), key: 'roleName', width: 140, render: (row) => t(row.roleName) },
  { title: t('邮箱'), key: 'email', width: 200 },
  { title: t('手机号'), key: 'phone', width: 140 },
  {
    title: t('状态'),
    key: 'status',
    width: 90,
    render: (row) =>
      h('span', { class: row.status === 'active' ? 'status-on' : 'status-off' }, formatStatus(row.status)),
  },
  {
    title: t('更新时间'),
    key: 'updatedAt',
    width: 170,
    render: (row) => formatAdminDateTime(row.updatedAt, '-'),
  },
  {
    title: t('操作'),
    key: 'actions',
    width: 220,
    render: (row) =>
      h('div', { class: 'action-row' }, [
        h(
          'button',
          {
            class: 'action-link',
            onClick: () => openEditAccount(row),
          },
          t('编辑'),
        ),
        row.isProtected
          ? h('span', { class: 'builtin-tag' }, t('内置账号'))
          : h(
              'button',
              {
                class: 'action-link danger',
                onClick: () => removeAccount(row),
              },
              t('删除'),
            ),
      ]),
  },
]);

function formatStatus(status: StatusType) {
  return status === 'active' ? t('启用') : t('禁用');
}

function parseError(error: unknown, fallback = t('请求失败')) {
  if (axios.isAxiosError(error)) {
    const detail = (error.response?.data as { detail?: string } | undefined)?.detail?.trim();
    if (detail) {
      return t(detail);
    }
    const status = error.response?.status;
    if (status) {
      if (status >= 500) return t('服务器处理失败，请稍后重试');
      if (status === 404) return t('请求的资源不存在');
      if (status === 400 || status === 422) return t('请求参数有误，请检查后重试');
      return fallback;
    }
    if (error.code === 'ECONNABORTED') return t('请求超时，请稍后重试');
    return t('网络异常，请检查 admin-api 是否已启动');
  }
  return fallback;
}

function isValidEmail(value: string) {
  return !value || /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value);
}

function isValidPhone(value: string) {
  return !value || /^1[3-9]\d{9}$/.test(value) || /^\+\d{7,20}$/.test(value);
}

function openCreateGroup() {
  groupEditorMode.value = 'create';
  groupForm.value = { id: '', name: '', description: '' };
  groupEditorVisible.value = true;
}

function openEditGroup(row: AccountGroupItem) {
  groupEditorMode.value = 'edit';
  groupForm.value = {
    id: row.id,
    name: row.name,
    description: row.description,
  };
  groupEditorVisible.value = true;
}

async function saveGroup() {
  if (!groupForm.value.name.trim()) {
    message.warning(t('请填写账号组名称'));
    return;
  }
  saving.value = true;
  try {
    if (groupEditorMode.value === 'create') {
      await createAccountGroup({
        name: groupForm.value.name.trim(),
        description: groupForm.value.description.trim(),
      });
      message.success(t('账号组已创建'));
    } else {
      await updateAccountGroup(groupForm.value.id, {
        name: groupForm.value.name.trim(),
        description: groupForm.value.description.trim(),
      });
      message.success(t('账号组已更新'));
    }
    groupEditorVisible.value = false;
    await loadData();
  } catch (error) {
    message.error(parseError(error, t('账号组保存失败')));
  } finally {
    saving.value = false;
  }
}

async function removeGroup(row: AccountGroupItem) {
  if (!window.confirm(t('确认删除账号组 {name} ?', { name: row.name }))) {
    return;
  }
  try {
    await deleteAccountGroup(row.id);
    message.success(t('账号组已删除'));
    await loadData();
  } catch (error) {
    message.error(parseError(error, t('账号组删除失败')));
  }
}

function openCreateAccount() {
  if (!groups.value.length) {
    message.warning(t('请先创建账号组'));
    return;
  }
  accountEditorMode.value = 'create';
  accountForm.value = {
    id: '',
    username: '',
    displayName: '',
    email: '',
    phone: '',
    groupCode: groups.value[0].code,
    roleName: '组织管理员',
    status: 'active',
    initialPassword: '',
  };
  accountEditorVisible.value = true;
}

function openEditAccount(row: AccountItem) {
  accountEditorMode.value = 'edit';
  accountForm.value = {
    id: row.id,
    username: row.username,
    displayName: row.displayName,
    email: row.email,
    phone: row.phone,
    groupCode: row.groupCode,
    roleName: row.roleName,
    status: row.status,
    initialPassword: '',
  };
  accountEditorVisible.value = true;
}

async function saveAccount() {
  if (!accountForm.value.username.trim() || !accountForm.value.displayName.trim()) {
    message.warning(t('请填写登录账号和姓名'));
    return;
  }
  if (!isValidPhone(accountForm.value.phone.trim())) {
    message.warning(t('手机号格式不正确'));
    return;
  }
  if (!isValidEmail(accountForm.value.email.trim())) {
    message.warning(t('邮箱格式不正确'));
    return;
  }
  if (accountEditorMode.value === 'create' && accountForm.value.initialPassword.trim().length < 10) {
    message.warning(t('初始密码至少 10 位'));
    return;
  }
  saving.value = true;
  try {
    if (accountEditorMode.value === 'create') {
      await createAccount({
        username: accountForm.value.username.trim(),
        displayName: accountForm.value.displayName.trim(),
        email: accountForm.value.email.trim(),
        phone: accountForm.value.phone.trim(),
        groupCode: accountForm.value.groupCode,
        roleName: accountForm.value.roleName,
        status: accountForm.value.status,
        initialPassword: accountForm.value.initialPassword.trim(),
      });
      message.success(t('账号已创建'));
    } else {
      await updateAccount(accountForm.value.id, {
        displayName: accountForm.value.displayName.trim(),
        email: accountForm.value.email.trim(),
        phone: accountForm.value.phone.trim(),
        groupCode: accountForm.value.groupCode,
        roleName: accountForm.value.roleName,
        status: accountForm.value.status,
      });
      message.success(t('账号已更新'));
    }
    accountEditorVisible.value = false;
    await loadData();
  } catch (error) {
    message.error(parseError(error, t('账号保存失败')));
  } finally {
    saving.value = false;
  }
}

async function removeAccount(row: AccountItem) {
  if (!window.confirm(t('确认删除账号 {name} ?', { name: row.username }))) {
    return;
  }
  try {
    await deleteAccount(row.id);
    message.success(t('账号已删除'));
    await loadData();
  } catch (error) {
    message.error(parseError(error, t('账号删除失败')));
  }
}

async function loadData() {
  const [groupData, accountData] = await Promise.all([fetchAccountGroups(), fetchAccounts()]);
  groups.value = groupData;
  accounts.value = accountData;
}

onMounted(async () => {
  try {
    await loadData();
  } catch (error) {
    message.error(parseError(error, t('账号数据加载失败')));
  }
});
</script>

<style scoped>
.account-page {
  height: calc(100vh - 98px);
  min-height: 520px;
}

.account-card {
  height: 100%;
}

:deep(.account-card .n-card__content) {
  height: 100%;
  display: flex;
  flex-direction: column;
}

.toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 14px;
  gap: 10px;
}

.group-toolbar {
  margin-bottom: 10px;
}

.table-area {
  flex: 1 1 0;
  min-height: 0;
  overflow: hidden;
}

.pager-row {
  margin-top: 12px;
  border-top: 1px solid #eceff5;
  padding-top: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 12px;
}

.pager-total {
  font-size: 12px;
  color: #6b7280;
}

:deep(.action-row) {
  display: inline-flex;
  align-items: center;
  gap: 8px;
}

:deep(.table-area .n-data-table) {
  height: 100%;
}

.account-table,
:deep(.account-table .n-data-table-wrapper),
:deep(.account-table .n-data-table-base-table),
:deep(.account-table .n-data-table-base-table-body) {
  height: 100%;
}

:deep(.action-link) {
  border: 1px solid #d8e2ff;
  border-radius: 6px;
  background: #f4f7ff;
  color: #366aff;
  cursor: pointer;
  padding: 2px 10px;
  font-size: 12px;
  line-height: 20px;
  transition:
    background-color 0.2s ease,
    border-color 0.2s ease,
    color 0.2s ease;
}

:deep(.action-link:hover) {
  background: #eaf0ff;
  border-color: #b9caff;
}

:deep(.action-link.danger) {
  border-color: #ffd5de;
  background: #fff6f8;
  color: #d03050;
}

:deep(.action-link.danger:hover) {
  background: #ffeef2;
  border-color: #ffb8c7;
}

:deep(.builtin-tag) {
  display: inline-flex;
  align-items: center;
  height: 24px;
  padding: 0 10px;
  border-radius: 12px;
  background: #f2f3f5;
  color: #767c82;
  font-size: 12px;
}

.status-on {
  color: #18a058;
}

.status-off {
  color: #767c82;
}

:deep(.n-button svg) {
  width: 15px;
  height: 15px;
  fill: none;
  stroke: currentColor;
  stroke-width: 2;
  stroke-linecap: round;
  stroke-linejoin: round;
}
</style>
