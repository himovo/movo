<template>
  <div class="page-stack account-page">
    <n-card class="account-card" :bordered="false" size="large">
      <div class="toolbar">
        <n-space align="center" :size="10">
          <n-input v-model:value="filters.keyword" :placeholder="t('legacy.search_by_username_name_email')" clearable />
          <n-select
            v-model:value="filters.groupCode"
            :options="groupOptions"
            :placeholder="t('legacy.account_group')"
            clearable
            style="width: 180px"
          />
          <n-select
            v-model:value="filters.status"
            :options="statusOptions"
            :placeholder="t('legacy.status')"
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
            {{ t('legacy.manage_groups') }}
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
            {{ t('legacy.add_account') }}
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
        <span class="pager-total">{{ t('legacy.total_items', { count: filteredAccounts.length }) }}</span>
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

  <n-modal v-model:show="groupManagerVisible" preset="card" :title="t('legacy.manage_groups')" style="width: 860px">
    <div class="toolbar group-toolbar">
      <span class="section-muted">{{ t('legacy.simple_mode_add_edit_or_delete_account_groups') }}</span>
      <n-button type="primary" size="small" @click="openCreateGroup">
        <template #icon>
          <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M5 12h14" />
            <path d="M12 5v14" />
          </svg>
        </template>
        {{ t('legacy.new_group') }}
      </n-button>
    </div>
    <n-data-table :columns="groupColumns" :data="groups" :pagination="{ pageSize: 6 }" :bordered="false" />
  </n-modal>

  <n-modal v-model:show="groupEditorVisible" preset="card" :title="groupEditorTitle" style="width: 560px">
    <n-form :model="groupForm" label-placement="left" label-width="84">
      <n-form-item :label="t('legacy.group_name')">
        <n-input v-model:value="groupForm.name" :placeholder="t('legacy.example_org_operations_admin_group')" />
      </n-form-item>
      <n-form-item :label="t('legacy.description')">
        <n-input v-model:value="groupForm.description" type="textarea" :rows="3" :placeholder="t('legacy.account_group_description')" />
      </n-form-item>
    </n-form>
    <template #footer>
      <n-space justify="end">
        <n-button @click="groupEditorVisible = false">{{ t('legacy.cancel') }}</n-button>
        <n-button type="primary" :loading="saving" @click="saveGroup">{{ t('legacy.save') }}</n-button>
      </n-space>
    </template>
  </n-modal>

  <n-modal v-model:show="accountEditorVisible" preset="card" :title="accountEditorTitle" style="width: 620px">
    <n-form :model="accountForm" label-placement="left" label-width="84">
      <n-grid :cols="2" :x-gap="12">
        <n-grid-item>
          <n-form-item :label="t('legacy.username')" required>
            <n-input
              v-model:value="accountForm.username"
              :disabled="accountEditorMode === 'edit'"
              :placeholder="t('legacy.example_wang_li')"
            />
          </n-form-item>
        </n-grid-item>
        <n-grid-item>
          <n-form-item :label="t('legacy.name')" required>
            <n-input v-model:value="accountForm.displayName" :placeholder="t('legacy.example_jane_doe')" />
          </n-form-item>
        </n-grid-item>
        <n-grid-item>
          <n-form-item :label="t('legacy.email')">
            <n-input v-model:value="accountForm.email" :placeholder="t('legacy.example_wang_li_company_com')" />
          </n-form-item>
        </n-grid-item>
        <n-grid-item>
          <n-form-item :label="t('legacy.mobile')">
            <n-input v-model:value="accountForm.phone" :placeholder="t('legacy.example_13800000000')" />
          </n-form-item>
        </n-grid-item>
        <n-grid-item>
          <n-form-item :label="t('legacy.account_group')" required>
            <n-select v-model:value="accountForm.groupCode" :options="groupOptions" />
          </n-form-item>
        </n-grid-item>
        <n-grid-item>
          <n-form-item :label="t('legacy.role')" required>
            <n-select v-model:value="accountForm.roleName" :options="roleOptions" />
          </n-form-item>
        </n-grid-item>
        <n-grid-item>
          <n-form-item :label="t('legacy.status')">
            <n-select v-model:value="accountForm.status" :options="statusOptions" />
          </n-form-item>
        </n-grid-item>
        <n-grid-item v-if="accountEditorMode === 'create'" :span="2">
          <n-form-item :label="t('legacy.initial_password')" required>
            <n-input
              v-model:value="accountForm.initialPassword"
              type="password"
              show-password-on="click"
              :placeholder="t('legacy.at_least_10_characters')"
            />
          </n-form-item>
          <div class="section-muted">{{ t('legacy.new_accounts_require_an_initial_password_to_log_in') }}</div>
        </n-grid-item>
      </n-grid>
    </n-form>
    <template #footer>
      <n-space justify="end">
        <n-button @click="accountEditorVisible = false">{{ t('legacy.cancel') }}</n-button>
        <n-button type="primary" :loading="saving" @click="saveAccount">{{ t('legacy.save') }}</n-button>
      </n-space>
    </template>
  </n-modal>
</template>

<script setup lang="ts">
import type { DataTableColumns } from 'naive-ui';
import { useMessage } from 'naive-ui';
import { computed, h, onMounted, ref, watch } from 'vue';
import axios from 'axios';
import { t, translateSourceText } from '@/composables/i18n';
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
  { label: t('legacy.platform_admin'), value: '平台管理员' },
  { label: t('legacy.organization_administrator'), value: '组织管理员' },
  { label: t('legacy.auditor'), value: '审计员' },
  { label: t('legacy.operator'), value: '运营人员' },
]);

// Keep compatibility with accounts created by older API versions that persisted
// the English role label instead of the stable Chinese message key.
const roleMessageKeys: Record<string, string> = {
  'Platform Admin': '平台管理员',
  'Organization Admin': '组织管理员',
  Auditor: '审计员',
  Operator: '运营人员',
};

function roleLabel(value: string) {
  return t(roleMessageKeys[value] || value);
}

const statusOptions = computed(() => [
  { label: t('legacy.active'), value: 'active' },
  { label: t('legacy.disabled_be70be5'), value: 'disabled' },
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
  roleName: t('legacy.organization_administrator'),
  status: 'active',
  initialPassword: '',
});

const groupEditorTitle = computed(() => (groupEditorMode.value === 'create' ? t('legacy.new_group') : t('legacy.edit_group')));
const accountEditorTitle = computed(() =>
  accountEditorMode.value === 'create' ? t('legacy.add_account') : t('legacy.edit_account'),
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
  { title: t('legacy.group_name'), key: 'name' },
  { title: t('legacy.description'), key: 'description' },
  { title: t('legacy.accounts_count'), key: 'accountCount' },
  {
    title: t('legacy.actions'),
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
          t('legacy.edit'),
        ),
        h(
          'button',
          {
            class: 'action-link danger',
            onClick: () => removeGroup(row),
          },
          t('legacy.delete'),
        ),
      ]),
  },
]);

const accountColumns = computed<DataTableColumns<AccountItem>>(() => [
  { title: t('legacy.username'), key: 'username', width: 150, fixed: 'left' },
  { title: t('legacy.name'), key: 'displayName', width: 130, fixed: 'left' },
  { title: t('legacy.account_group'), key: 'groupName', width: 160 },
  { title: t('legacy.role'), key: 'roleName', width: 140, render: (row) => roleLabel(row.roleName) },
  { title: t('legacy.email'), key: 'email', width: 200 },
  { title: t('legacy.mobile'), key: 'phone', width: 140 },
  {
    title: t('legacy.status'),
    key: 'status',
    width: 90,
    render: (row) =>
      h('span', { class: row.status === 'active' ? 'status-on' : 'status-off' }, formatStatus(row.status)),
  },
  {
    title: t('legacy.updated_at'),
    key: 'updatedAt',
    width: 170,
    render: (row) => formatAdminDateTime(row.updatedAt, '-'),
  },
  {
    title: t('legacy.actions'),
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
          t('legacy.edit'),
        ),
        row.isProtected
          ? h('span', { class: 'builtin-tag' }, t('legacy.built_in'))
          : h(
              'button',
              {
                class: 'action-link danger',
                onClick: () => removeAccount(row),
              },
              t('legacy.delete'),
            ),
      ]),
  },
]);

function formatStatus(status: StatusType) {
  return status === 'active' ? t('legacy.active') : t('legacy.disabled_be70be5');
}

function parseError(error: unknown, fallback = t('legacy.request_failed')) {
  if (axios.isAxiosError(error)) {
    const detail = (error.response?.data as { detail?: string } | undefined)?.detail?.trim();
    if (detail) {
      return translateSourceText(detail);
    }
    const status = error.response?.status;
    if (status) {
      if (status >= 500) return t('legacy.server_error_please_try_again_later');
      if (status === 404) return t('legacy.the_requested_resource_was_not_found');
      if (status === 400 || status === 422) return t('legacy.invalid_request_please_check_and_try_again');
      return fallback;
    }
    if (error.code === 'ECONNABORTED') return t('legacy.request_timed_out_please_try_again_later');
    return t('legacy.network_error_please_check_whether_admin_api_is_running');
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
    message.warning(t('legacy.please_enter_group_name'));
    return;
  }
  saving.value = true;
  try {
    if (groupEditorMode.value === 'create') {
      await createAccountGroup({
        name: groupForm.value.name.trim(),
        description: groupForm.value.description.trim(),
      });
      message.success(t('legacy.group_created_successfully'));
    } else {
      await updateAccountGroup(groupForm.value.id, {
        name: groupForm.value.name.trim(),
        description: groupForm.value.description.trim(),
      });
      message.success(t('legacy.group_updated_successfully'));
    }
    groupEditorVisible.value = false;
    await loadData();
  } catch (error) {
    message.error(parseError(error, t('legacy.failed_to_save_group')));
  } finally {
    saving.value = false;
  }
}

async function removeGroup(row: AccountGroupItem) {
  if (!window.confirm(t('legacy.are_you_sure_to_delete_group', { name: row.name }))) {
    return;
  }
  try {
    await deleteAccountGroup(row.id);
    message.success(t('legacy.group_deleted_successfully'));
    await loadData();
  } catch (error) {
    message.error(parseError(error, t('legacy.failed_to_delete_group')));
  }
}

function openCreateAccount() {
  if (!groups.value.length) {
    message.warning(t('legacy.please_create_an_account_group_first'));
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
    roleName: t('legacy.organization_administrator'),
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
    roleName: roleMessageKeys[row.roleName] || row.roleName,
    status: row.status,
    initialPassword: '',
  };
  accountEditorVisible.value = true;
}

async function saveAccount() {
  if (!accountForm.value.username.trim() || !accountForm.value.displayName.trim()) {
    message.warning(t('legacy.please_enter_username_and_display_name'));
    return;
  }
  if (!isValidPhone(accountForm.value.phone.trim())) {
    message.warning(t('legacy.invalid_mobile_number_format'));
    return;
  }
  if (!isValidEmail(accountForm.value.email.trim())) {
    message.warning(t('legacy.invalid_email_format'));
    return;
  }
  if (accountEditorMode.value === 'create' && accountForm.value.initialPassword.trim().length < 10) {
    message.warning(t('legacy.initial_password_must_be_at_least_10_characters'));
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
      message.success(t('legacy.account_created_successfully'));
    } else {
      await updateAccount(accountForm.value.id, {
        displayName: accountForm.value.displayName.trim(),
        email: accountForm.value.email.trim(),
        phone: accountForm.value.phone.trim(),
        groupCode: accountForm.value.groupCode,
        roleName: accountForm.value.roleName,
        status: accountForm.value.status,
      });
      message.success(t('legacy.account_updated_successfully'));
    }
    accountEditorVisible.value = false;
    await loadData();
  } catch (error) {
    message.error(parseError(error, t('legacy.failed_to_save_account')));
  } finally {
    saving.value = false;
  }
}

async function removeAccount(row: AccountItem) {
  if (!window.confirm(t('legacy.are_you_sure_to_delete_account', { name: row.username }))) {
    return;
  }
  try {
    await deleteAccount(row.id);
    message.success(t('legacy.account_deleted_successfully'));
    await loadData();
  } catch (error) {
    message.error(parseError(error, t('legacy.failed_to_delete_account')));
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
    message.error(parseError(error, t('legacy.failed_to_load_account_data')));
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
