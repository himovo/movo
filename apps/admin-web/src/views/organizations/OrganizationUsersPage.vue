<template>
  <div class="page-stack user-page">
    <n-card class="user-card" :bordered="false" size="large">
      <div class="user-layout">
        <aside class="dept-panel">
          <div class="panel-head">
            <span class="panel-title">{{ t('组织架构') }}</span>
            <n-space :size="6">
              <n-button size="tiny" @click="() => openCreateDept()">
                <template #icon>
                  <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <path d="M5 12h14" />
                    <path d="M12 5v14" />
                  </svg>
                </template>
                {{ t('新增') }}
              </n-button>
              <n-button size="tiny" :disabled="!selectedDeptId" @click="() => openEditDept(selectedDeptId)">
                <template #icon>
                  <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <path d="M12 20h9" />
                    <path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4 12.5-12.5z" />
                  </svg>
                </template>
                {{ t('编辑') }}
              </n-button>
            </n-space>
          </div>
          <n-input v-model:value="treeKeyword" :placeholder="t('搜索部门')" clearable size="small" />
          <div class="tree-wrap">
            <n-tree
              block-line
              selectable
              :pattern="treeKeyword"
              :data="treeOptions"
              :render-label="renderTreeLabel"
              :selected-keys="selectedDeptKeys"
              :expanded-keys="expandedDeptKeys"
              @update:selected-keys="handleSelectDepartment"
              @update:expanded-keys="handleExpandDepartments"
            />
          </div>
          <n-space :size="8">
            <n-button size="small" :disabled="!selectedDeptId" @click="openMoveDept">
              <template #icon>
                <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                  <path d="m5 9-3 3 3 3M9 5l3-3 3 3M15 19l-3 3-3-3M19 9l3 3-3 3M2 12h20M12 2v20" />
                </svg>
              </template>
              {{ t('移动') }}
            </n-button>
            <n-button size="small" type="error" ghost :disabled="!selectedDeptId" @click="deleteSelectedDept">
              <template #icon>
                <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                  <circle cx="12" cy="12" r="10" />
                  <path d="m4.9 4.9 14.2 14.2" />
                </svg>
              </template>
              {{ t('删除') }}
            </n-button>
          </n-space>
        </aside>

        <section class="list-panel">
          <div class="toolbar">
            <n-space :size="10">
              <n-input v-model:value="keyword" :placeholder="t('搜索姓名/手机号/邮箱')" clearable />
              <n-select v-model:value="sourceFilter" :options="sourceOptions" :placeholder="t('来源')" clearable style="width: 130px" />
              <n-select v-model:value="statusFilter" :options="statusOptions" :placeholder="t('状态')" clearable style="width: 120px" />
            </n-space>
            <n-space :size="10">
              <n-button :disabled="!selectedUserIds.length" @click="bulkRoleDialogVisible = true">
                {{ t('批量分配岗位') }}<template v-if="selectedUserIds.length">（{{ selectedUserIds.length }}）</template>
              </n-button>
              <n-button @click="fieldManagerVisible = true">
                <template #icon>
                  <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <line x1="4" y1="21" x2="4" y2="14" /><line x1="4" y1="10" x2="4" y2="3" /><line x1="12" y1="21" x2="12" y2="12" /><line x1="12" y1="8" x2="12" y2="3" /><line x1="20" y1="21" x2="20" y2="16" /><line x1="20" y1="12" x2="20" y2="3" /><line x1="2" y1="14" x2="6" y2="14" /><line x1="10" y1="8" x2="14" y2="8" /><line x1="18" y1="16" x2="22" y2="16" />
                  </svg>
                </template>
                {{ t('用户字段配置') }}
              </n-button>
              <n-button @click="openInviteUser">
                <template #icon>
                  <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <rect x="2" y="4" width="20" height="16" rx="2" /><path d="m22 7-8.97 5.7a1.94 1.94 0 0 1-2.06 0L2 7" />
                  </svg>
                </template>
                {{ t('邀请用户') }}
              </n-button>
              <n-button type="primary" @click="openCreateUser">
                <template #icon>
                  <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2" /><circle cx="9" cy="7" r="4" /><line x1="19" y1="8" x2="19" y2="14" /><line x1="22" y1="11" x2="16" y2="11" />
                  </svg>
                </template>
                {{ t('新增用户') }}
              </n-button>
            </n-space>
          </div>

          <div class="table-area">
            <n-data-table
              class="user-table"
              :columns="columns"
              :data="pagedUsers"
              :bordered="false"
              :pagination="false"
              flex-height
              :scroll-x="userTableScrollX"
              :scrollbar-props="tableScrollbarProps"
              :row-key="(row: DirectoryUserItem) => row.id"
              v-model:checked-row-keys="selectedUserIds"
            />
          </div>

          <div class="pager-row">
            <span class="pager-total">{{ t('共 {count} 条', { count: filteredUsers.length }) }}</span>
            <n-pagination v-model:page="currentPage" :page-size="pageSize" :item-count="filteredUsers.length" />
          </div>
        </section>
      </div>
    </n-card>
  </div>

  <n-modal v-model:show="deptEditorVisible" preset="card" :title="deptEditorTitle" style="width: 520px">
    <n-form :model="deptForm" label-placement="left" label-width="90">
      <n-form-item :label="t('部门名称')">
        <n-input v-model:value="deptForm.name" :placeholder="t('请输入部门名称')" />
      </n-form-item>
      <n-form-item :label="t('状态')">
        <n-select v-model:value="deptForm.status" :options="statusOptions" />
      </n-form-item>
      <n-form-item v-if="deptEditorMode === 'create'" :label="t('上级部门')">
        <n-select v-model:value="deptForm.parentId" :options="departmentOptionsWithRoot" clearable :placeholder="t('根部门')" />
      </n-form-item>
    </n-form>
    <template #footer>
      <n-space justify="end">
        <n-button @click="deptEditorVisible = false">{{ t('取消') }}</n-button>
        <n-button type="primary" :loading="saving" @click="saveDepartment">{{ t('保存') }}</n-button>
      </n-space>
    </template>
  </n-modal>

  <n-modal v-model:show="deptMoveVisible" preset="card" :title="t('移动部门')" style="width: 520px">
    <n-form :model="moveForm" label-placement="left" label-width="90">
      <n-form-item :label="t('目标上级')">
        <n-select v-model:value="moveForm.parentId" :options="moveDepartmentOptions" clearable :placeholder="t('根部门')" />
      </n-form-item>
    </n-form>
    <template #footer>
      <n-space justify="end">
        <n-button @click="deptMoveVisible = false">{{ t('取消') }}</n-button>
        <n-button type="primary" :loading="saving" @click="saveMoveDepartment">{{ t('确认移动') }}</n-button>
      </n-space>
    </template>
  </n-modal>

  <n-modal v-model:show="userEditorVisible" preset="card" :title="userEditorTitle" style="width: 760px">
    <n-form :model="userForm" label-placement="left" label-width="100">
      <EmployeeCredentialsFields
        v-model:login-name="userForm.loginName"
        v-model:password="userForm.credentialPassword"
        :mode="userEditorMode"
        :source="userForm.source"
      />
      <n-grid :cols="2" :x-gap="12">
        <n-grid-item>
          <n-form-item :label="t('姓名')" required><n-input v-model:value="userForm.name" /></n-form-item>
        </n-grid-item>
        <n-grid-item>
          <n-form-item :label="t('手机号')" required><n-input v-model:value="userForm.mobile" /></n-form-item>
        </n-grid-item>
        <n-grid-item>
          <n-form-item :label="t('邮箱')" required><n-input v-model:value="userForm.email" /></n-form-item>
        </n-grid-item>
        <n-grid-item>
          <n-form-item :label="t('主部门')" required>
            <n-select v-model:value="userForm.primaryDepartmentId" :options="departmentOptions" />
          </n-form-item>
        </n-grid-item>
        <n-grid-item>
          <n-form-item :label="t('状态')"><n-select v-model:value="userForm.status" :options="statusOptions" /></n-form-item>
        </n-grid-item>
        <n-grid-item>
          <n-form-item :label="t('主要岗位角色')" required>
            <n-select v-model:value="userForm.primaryRoleId" :options="roleOptions" @update:value="syncPrimaryRole" />
          </n-form-item>
        </n-grid-item>
        <n-grid-item :span="2">
          <n-form-item :label="t('其他岗位角色')">
            <n-select v-model:value="userForm.roleIds" multiple max-tag-count="responsive" :options="roleOptions" :placeholder="t('可多选')" />
          </n-form-item>
        </n-grid-item>
        <n-grid-item :span="2">
          <n-form-item :label="t('所属部门')">
            <n-select
              v-model:value="userForm.departmentIds"
              multiple
              max-tag-count="responsive"
              :options="departmentOptions"
              :placeholder="t('可多选')"
            />
          </n-form-item>
        </n-grid-item>
        <n-grid-item v-for="field in activeUserFields" :key="field.fieldKey" :span="field.fieldType === 'textarea' ? 2 : 1">
          <n-form-item :label="field.label" :required="field.required">
            <n-input
              v-if="field.fieldType === 'text'"
              v-model:value="userForm.customFields[field.fieldKey]"
              :placeholder="field.label"
            />
            <n-input
              v-else-if="field.fieldType === 'textarea'"
              v-model:value="userForm.customFields[field.fieldKey]"
              type="textarea"
              :rows="field.rows || 3"
              :placeholder="field.label"
              style="width: 100%"
            />
            <n-select
              v-else-if="field.fieldType === 'select'"
              v-model:value="userForm.customFields[field.fieldKey]"
              :options="field.options.map((option) => ({ label: option, value: option }))"
              clearable
              :placeholder="field.label"
            />
            <n-select
              v-else-if="field.fieldType === 'multiselect'"
              v-model:value="userForm.customFields[field.fieldKey]"
              multiple
              max-tag-count="responsive"
              :options="field.options.map((option) => ({ label: option, value: option }))"
              clearable
              :placeholder="field.label"
            />
            <n-input v-else v-model:value="userForm.customFields[field.fieldKey]" :placeholder="field.label" />
          </n-form-item>
        </n-grid-item>
      </n-grid>
    </n-form>
    <template #footer>
      <n-space justify="end">
        <n-button @click="userEditorVisible = false">{{ t('取消') }}</n-button>
        <n-button type="primary" :loading="saving" @click="saveUser">{{ t('保存') }}</n-button>
      </n-space>
    </template>
  </n-modal>

  <EmployeeCapabilityOverrideDialog
    v-model:show="overrideDialogVisible"
    :user-id="overrideTarget?.id || ''"
    :user-name="overrideTarget?.name || ''"
  />
  <BulkPositionRoleDialog
    v-model:show="bulkRoleDialogVisible"
    :user-ids="selectedUserIds"
    :roles="positionRoles"
    @saved="handleBulkRolesSaved"
  />

  <n-modal v-model:show="fieldManagerVisible" preset="card" :title="t('用户自定义字段')" style="width: 920px">
    <div class="toolbar compact-toolbar">
      <span class="section-muted">{{ t('固定字段外的扩展字段，动态渲染到用户资料。') }}</span>
      <n-button type="primary" size="small" @click="openCreateField">
        <template #icon>
          <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M5 12h14" />
            <path d="M12 5v14" />
          </svg>
        </template>
        {{ t('新增字段') }}
      </n-button>
    </div>
    <n-data-table :columns="fieldColumns" :data="fieldDefs" :bordered="false" :pagination="{ pageSize: 8 }" />
  </n-modal>

  <n-modal v-model:show="fieldEditorVisible" preset="card" :title="fieldEditorTitle" style="width: 620px">
    <n-form :model="fieldForm" label-placement="left" label-width="90">
      <n-form-item :label="t('字段Key')"><n-input v-model:value="fieldForm.fieldKey" :disabled="fieldEditorMode === 'edit'" /></n-form-item>
      <n-form-item :label="t('字段名称')"><n-input v-model:value="fieldForm.label" /></n-form-item>
      <n-form-item :label="t('字段类型')"><n-select v-model:value="fieldForm.fieldType" :options="fieldTypeOptions" /></n-form-item>
      <n-form-item v-if="fieldForm.fieldType === 'select' || fieldForm.fieldType === 'multiselect'" :label="t('选项值')">
        <n-input v-model:value="fieldForm.optionsText" :placeholder="t('用英文逗号分隔')" />
      </n-form-item>
      <n-form-item v-if="fieldForm.fieldType === 'textarea'" :label="t('默认行数')">
        <n-input-number v-model:value="fieldForm.rows" :min="2" :max="12" style="width: 100%" />
      </n-form-item>
      <n-form-item :label="t('排序')">
        <n-input-number v-model:value="fieldForm.sort" :min="0" :max="9999" style="width: 100%" />
      </n-form-item>
      <n-grid :cols="3" :x-gap="12">
        <n-grid-item><n-form-item :label="t('必填')"><n-switch v-model:value="fieldForm.required" /></n-form-item></n-grid-item>
        <n-grid-item><n-form-item :label="t('脱敏')"><n-switch v-model:value="fieldForm.masked" /></n-form-item></n-grid-item>
        <n-grid-item><n-form-item :label="t('启用')"><n-switch v-model:value="fieldForm.enabled" /></n-form-item></n-grid-item>
      </n-grid>
    </n-form>
    <template #footer>
      <n-space justify="end">
        <n-button @click="fieldEditorVisible = false">{{ t('取消') }}</n-button>
        <n-button type="primary" :loading="saving" @click="saveField">{{ t('保存') }}</n-button>
      </n-space>
    </template>
  </n-modal>

  <n-modal v-model:show="inviteVisible" preset="card" :title="t('邀请用户')" style="width: 720px">
    <n-form :model="inviteForm" label-placement="left" label-width="110">
      <n-grid :cols="2" :x-gap="12">
        <n-grid-item>
          <n-form-item :label="t('默认部门')">
            <n-select v-model:value="inviteForm.defaultDepartmentId" :options="departmentOptionsWithRoot" clearable :placeholder="t('默认根部门')" />
          </n-form-item>
        </n-grid-item>
        <n-grid-item>
          <n-form-item :label="t('有效期(小时)')">
            <n-input-number v-model:value="inviteForm.expiresHours" :min="1" :max="720" style="width: 100%" />
          </n-form-item>
        </n-grid-item>
      </n-grid>
      <n-form-item :label="t('岗位角色')" required>
        <n-select v-model:value="inviteForm.primaryRoleId" :options="roleOptions" @update:value="syncInvitePrimaryRole" />
      </n-form-item>
      <n-form-item :label="t('其他岗位角色')">
        <n-select v-model:value="inviteForm.roleIds" multiple max-tag-count="responsive" :options="roleOptions" />
      </n-form-item>
      <n-alert v-if="inviteCapabilityPreview" type="info" :bordered="false" style="margin-bottom: 18px">
        {{ t('接受邀请后可用：') }}{{ inviteCapabilityPreview }}
      </n-alert>
      <n-form-item v-if="inviteResult.inviteUrl" :label="t('邀请链接')">
        <div class="invite-link-block">
          <div class="invite-link-row">
            <n-input :value="inviteResult.inviteUrl" readonly />
            <n-button @click="copyInviteUrl">
              <template #icon>
                <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                  <rect x="9" y="9" width="13" height="13" rx="2" ry="2" />
                  <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" />
                </svg>
              </template>
              {{ t('复制链接') }}
            </n-button>
          </div>
          <div class="section-muted invite-expire-text">
            {{ t('用户注册链接，过期时间：{time}', { time: inviteResult.expiresAt }) }}
          </div>
        </div>
      </n-form-item>
      <n-form-item v-if="inviteResult.token" :label="t('邀请码')">
        <div class="invite-link-block">
          <div class="invite-link-row">
            <n-input :value="inviteResult.token" readonly />
            <n-button @click="copyInviteCode">
              <template #icon>
                <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                  <rect x="9" y="9" width="13" height="13" rx="2" ry="2" />
                  <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" />
                </svg>
              </template>
              {{ t('复制邀请码') }}
            </n-button>
          </div>
          <div class="section-muted invite-expire-text">
            {{ t('用户也可以在注册页手动输入邀请码加入组织。') }}
          </div>
        </div>
      </n-form-item>
    </n-form>
    <template #footer>
      <n-space justify="end">
        <n-button @click="inviteVisible = false">{{ t('关闭') }}</n-button>
        <n-button type="primary" :loading="saving" @click="generateInviteLink">
          <template #icon>
            <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M15 7h3a5 5 0 0 1 5 5 5 5 0 0 1-5 5h-3m-6 0H6a5 5 0 0 1-5-5 5 5 0 0 1 5-5h3" />
              <line x1="8" y1="12" x2="16" y2="12" />
            </svg>
          </template>
          {{ t('生成链接') }}
        </n-button>
      </n-space>
    </template>
  </n-modal>
</template>

<script setup lang="ts">
import type { DataTableColumns, SelectOption, TreeOption } from 'naive-ui';
import { NTag, useDialog, useMessage } from 'naive-ui';
import { computed, h, onMounted, ref, watch } from 'vue';
import { t } from '@/composables/i18n';
import { formatAdminDateTime } from '@/composables/adminTimezone';
import axios from 'axios';
import {
  createDepartment,
  createOrgInviteLink,
  createUser,
  createUserFieldDef,
  deleteDepartment,
  deleteUser,
  deleteUserFieldDef,
  disableUser,
  enableUser,
  fetchUserCustomFields,
  fetchDepartmentTree,
  fetchUserFieldDefs,
  fetchUsers,
  moveDepartment,
  updateDepartment,
  updateUser,
  updateUserCustomFields,
  updateUserFieldDef,
  type DepartmentNode,
  type DirectoryUserItem,
  type UserFieldDef,
  type UserInviteLinkResult,
} from '@/api/directory';
import { listPositionRoles, type PositionRole } from '@/api/positionRoles';
import EmployeeCapabilityOverrideDialog from './EmployeeCapabilityOverrideDialog.vue';
import BulkPositionRoleDialog from './BulkPositionRoleDialog.vue';
import EmployeeCredentialsFields from '@/components/directory/EmployeeCredentialsFields.vue';

const message = useMessage();
const dialog = useDialog();
const saving = ref(false);
const overrideDialogVisible = ref(false);
const overrideTarget = ref<DirectoryUserItem | null>(null);
const bulkRoleDialogVisible = ref(false);
const selectedUserIds = ref<string[]>([]);

function openCapabilityOverride(row: DirectoryUserItem) {
  overrideTarget.value = row;
  overrideDialogVisible.value = true;
}

async function handleBulkRolesSaved() {
  selectedUserIds.value = [];
  await loadUsers();
}

const departments = ref<DepartmentNode[]>([]);
const users = ref<DirectoryUserItem[]>([]);
const fieldDefs = ref<UserFieldDef[]>([]);
const positionRoles = ref<PositionRole[]>([]);
const roleOptions = computed<SelectOption[]>(() => positionRoles.value.filter(role => role.status === 'active').map(role => ({ label: role.name, value: role.id })));
const capabilityNames: Record<string, string> = { content_generation: '内容生成', image_generation: '图片生成', code_generation: '代码生成', browser_automation: '浏览器自动运行', internal_knowledge: '内部知识检索' };
const activeUserFields = computed(() => fieldDefs.value.filter((field) => field.enabled));

const treeKeyword = ref('');
const selectedDeptKeys = ref<string[]>([]);
const expandedDeptKeys = ref<string[]>([]);
const keyword = ref('');
const sourceFilter = ref<string | null>(null);
const statusFilter = ref<string | null>(null);
const revealedMaskedFields = ref<Set<string>>(new Set());

const sourceOptions = computed<SelectOption[]>(() => [
  { label: t('本地'), value: 'local' },
  { label: t('钉钉'), value: 'dingtalk' },
  { label: t('企业微信'), value: 'wecom' },
  { label: t('飞书'), value: 'feishu' },
]);
const statusOptions = computed<SelectOption[]>(() => [
  { label: t('启用'), value: 'active' },
  { label: t('禁用'), value: 'disabled' },
]);

const treeOptions = computed<TreeOption[]>(() => toTreeOptions(departments.value));

const selectedDeptId = computed(() => selectedDeptKeys.value[0] || '');
const departmentOptions = computed<SelectOption[]>(() => flattenDepartmentOptions(departments.value, true));
const departmentOptionsWithRoot = computed<SelectOption[]>(() => flattenDepartmentOptions(departments.value, true));
const moveDepartmentOptions = computed<SelectOption[]>(() => flattenDepartmentOptions(departments.value, true, selectedMoveBlockedDeptIds.value));
const selectedMoveBlockedDeptIds = computed(() => {
  if (!selectedDeptId.value) return new Set<string>();
  const target = findDepartmentById(departments.value, selectedDeptId.value);
  return new Set(target ? collectDeptIds([target]) : [selectedDeptId.value]);
});

const filteredUsers = computed(() => {
  const q = keyword.value.trim().toLowerCase();
  return users.value.filter((item) => {
    const hitKeyword =
      !q || [item.name, item.mobile, item.email, item.loginName].some((v) => (v || '').toLowerCase().includes(q));
    const hitSource = !sourceFilter.value || item.source === sourceFilter.value;
    const hitStatus = !statusFilter.value || item.status === statusFilter.value;
    return hitKeyword && hitSource && hitStatus;
  });
});

const pageSize = 10;
const tableScrollbarProps = { trigger: 'none' as const };
const currentPage = ref(1);
const pagedUsers = computed(() => {
  const start = (currentPage.value - 1) * pageSize;
  return filteredUsers.value.slice(start, start + pageSize);
});

watch(filteredUsers, (rows) => {
  const next = Math.max(1, Math.ceil(rows.length / pageSize));
  if (currentPage.value > next) {
    currentPage.value = next;
  }
});

watch([selectedDeptId, sourceFilter, statusFilter], async () => {
  await loadUsers();
});

function parseError(error: unknown) {
  if (axios.isAxiosError(error)) {
    const detail = (error.response?.data as { detail?: string | Array<{ msg?: string }> } | undefined)?.detail;
    if (typeof detail === 'string') return detail;
    if (Array.isArray(detail)) return t('请求参数有误，请检查后重试');
    if (error.response?.status === 422) return t('请求参数有误，请检查后重试');
    if (error.response?.status && error.response.status >= 500) return t('服务器处理失败，请稍后重试');
    return error.message || t('请求失败');
  }
  return t('请求失败');
}

function toTreeOptions(nodes: DepartmentNode[]): TreeOption[] {
  return nodes.map((node) => ({
    key: node.id,
    label: node.name,
    rawName: node.name,
    userCount: node.userCount,
    children: toTreeOptions(node.children || []),
  }));
}

function renderTreeLabel(info: { option: TreeOption & { rawName?: string; userCount?: number } }) {
  const nodeId = String(info.option.key);
  const name = info.option.rawName || String(info.option.label || '');
  const count = Number(info.option.userCount || 0);
  return h('div', { class: 'dept-node-label' }, [
    h('span', { class: 'dept-node-title' }, `${name} (${count})`),
    h('span', { class: 'dept-node-actions' }, [
      h(
        'button',
        {
          class: 'dept-node-action',
          title: t('新增子部门'),
          onClick: (event: MouseEvent) => {
            event.preventDefault();
            event.stopPropagation();
            selectedDeptKeys.value = [nodeId];
            openCreateDept(nodeId);
          },
        },
        '+',
      ),
      h(
        'button',
        {
          class: 'dept-node-action',
          title: t('编辑部门'),
          onClick: (event: MouseEvent) => {
            event.preventDefault();
            event.stopPropagation();
            selectedDeptKeys.value = [nodeId];
            openEditDept(nodeId);
          },
        },
        '✎',
      ),
    ]),
  ]);
}

function flattenDepartmentOptions(nodes: DepartmentNode[], includeRoot: boolean, excludeIds: Set<string> = new Set()): SelectOption[] {
  const result: SelectOption[] = [];
  const dfs = (items: DepartmentNode[], lineage: string[] = []) => {
    for (const item of items) {
      if (excludeIds.has(item.id)) {
        continue;
      }
      if (!includeRoot && item.code === 'root') {
        dfs(item.children || [], lineage);
        continue;
      }
      const nextLineage = [...lineage, item.name];
      result.push({ label: nextLineage.join(' / '), value: item.id });
      dfs(item.children || [], nextLineage);
    }
  };
  dfs(nodes);
  return result;
}

function handleSelectDepartment(keys: Array<string | number>) {
  selectedDeptKeys.value = keys.map(String);
}

function handleExpandDepartments(keys: Array<string | number>) {
  expandedDeptKeys.value = keys.map(String);
}

const columns = computed<DataTableColumns<DirectoryUserItem>>(() => {
  const dynamicColumns: DataTableColumns<DirectoryUserItem> = fieldDefs.value
    .filter((field) => field.enabled)
    .map((field) => ({
      title: field.label,
      key: `custom_${field.fieldKey}`,
      width: field.masked ? 170 : 140,
      render: (row) => renderCustomFieldValue(row, field),
    }));
  return [
    { type: 'selection', fixed: 'left', width: 44 },
    { title: t('姓名'), key: 'name', width: 120, fixed: 'left' },
    { title: t('登录名'), key: 'loginName', width: 140, fixed: 'left' },
    { title: t('手机号'), key: 'mobile', width: 140, fixed: 'left' },
    { title: t('邮箱'), key: 'email', width: 180 },
    { title: t('主部门'), key: 'primaryDepartmentName', width: 180 },
    {
      title: t('岗位角色'), key: 'positionRoles', width: 220,
      render: row => row.pendingPositionRole
        ? h(NTag, { type: 'warning', bordered: false, size: 'small' }, { default: () => t('待分配') })
        : h('div', { class: 'role-tags' }, row.positionRoles.map(role => h(NTag, { type: role.isPrimary ? 'info' : 'default', bordered: false, size: 'small' }, { default: () => role.name }))),
    },
    {
      title: t('来源'),
      key: 'source',
      width: 110,
      render: (row) => h('span', { class: 'source-tag' }, sourceLabel(row.source)),
    },
    ...dynamicColumns,
    {
      title: t('状态'),
      key: 'status',
      width: 90,
      render: (row) => h('span', { class: row.status === 'active' ? 'status-on' : 'status-off' }, row.status === 'active' ? t('启用') : t('禁用')),
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
      width: 360,
      render: (row) =>
        h('div', { class: 'action-row' }, [
          h(
            'button',
            {
              class: 'action-link',
              onClick: () => openEditUser(row),
            },
            t('编辑'),
          ),
          h(
            'button',
            {
              class: 'action-link',
              onClick: () => openCapabilityOverride(row),
            },
            t('临时授权'),
          ),
          row.status === 'active'
            ? h(
                'button',
                {
                  class: 'action-link danger',
                  onClick: () => disableUserRow(row),
                },
                t('停用'),
              )
            : h(
                'button',
                {
                  class: 'action-link',
                  onClick: () => enableUserRow(row),
                },
                t('启用'),
              ),
          h(
            'button',
            {
              class: 'action-link danger',
              onClick: () => deleteUserRow(row),
            },
            t('删除'),
          ),
        ]),
    },
  ];
});
const userTableScrollX = computed(() => 1490 + fieldDefs.value.filter((field) => field.enabled).length * 140);

const fieldColumns = computed<DataTableColumns<UserFieldDef>>(() => [
  { title: t('字段Key'), key: 'fieldKey' },
  { title: t('字段名称'), key: 'label' },
  {
    title: t('类型'),
    key: 'fieldType',
    render: (row) => {
      const map: Record<string, string> = {
        text: t('单行文本'),
        textarea: t('多行文本'),
        select: t('单选'),
        multiselect: t('多选'),
      };
      return map[row.fieldType] || row.fieldType;
    },
  },
  {
    title: t('默认行数'),
    key: 'rows',
    render: (row) => (row.fieldType === 'textarea' ? row.rows || 3 : '-'),
  },
  {
    title: t('状态'),
    key: 'enabled',
    render: (row) => h('span', { class: row.enabled ? 'status-on' : 'status-off' }, row.enabled ? t('启用') : t('禁用')),
  },
  { title: t('排序'), key: 'sort' },
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
            onClick: () => openEditField(row),
          },
          t('编辑'),
        ),
        h(
          'button',
          {
            class: 'action-link danger',
            onClick: () => removeField(row),
          },
          t('删除'),
        ),
      ]),
  },
]);

function sourceLabel(source: string) {
  const map: Record<string, string> = {
    local: t('本地'),
    dingtalk: t('钉钉'),
    wecom: t('企业微信'),
    feishu: t('飞书'),
  };
  return map[source] || source;
}

function formatCustomFieldValue(value: unknown) {
  if (value === null || value === undefined || value === '') return '-';
  if (typeof value === 'boolean') return value ? t('是') : t('否');
  if (Array.isArray(value)) return value.join(', ');
  if (typeof value === 'object') return JSON.stringify(value);
  return String(value);
}

function maskedFieldKey(row: DirectoryUserItem, fieldKey: string) {
  return `${row.id}:${fieldKey}`;
}

function isEmptyCustomValue(value: unknown) {
  return value === null || value === undefined || value === '' || (Array.isArray(value) && value.length === 0);
}

function toggleMaskedField(row: DirectoryUserItem, fieldKey: string) {
  const key = maskedFieldKey(row, fieldKey);
  const next = new Set(revealedMaskedFields.value);
  if (next.has(key)) {
    next.delete(key);
  } else {
    next.add(key);
  }
  revealedMaskedFields.value = next;
}

function renderMaskedFieldIcon(revealed: boolean) {
  const svgProps = {
    xmlns: 'http://www.w3.org/2000/svg',
    viewBox: '0 0 512 512',
    fill: 'none',
    stroke: 'currentColor',
    'stroke-linecap': 'round',
    'stroke-linejoin': 'round',
    'aria-hidden': 'true',
    style: 'display:block;width:15px;height:15px;',
  };
  if (revealed) {
    return h('svg', svgProps, [
      h('path', { d: 'M432 448 80 64', 'stroke-width': 32 }),
      h('path', {
        d: 'M255.66 112c-77.94 0-157.89 45.11-220.83 135.33a16 16 0 0 0 0 18.88c31 44.5 66.62 78.6 104.11 101.83M194.93 153.56A138.37 138.37 0 0 1 255.66 140c77.94 0 157.89 45.11 220.83 135.33a16 16 0 0 1 0 18.88c-22.56 32.43-47.68 59.35-74.35 80.28',
        'stroke-width': 32,
      }),
      h('path', { d: 'M336 256a80 80 0 0 1-104.28 76.17M176.27 219.84A80 80 0 0 1 280.55 143.7', 'stroke-width': 32 }),
    ]);
  }
  return h('svg', svgProps, [
    h('path', {
      d: 'M255.66 112c-77.94 0-157.89 45.11-220.83 135.33a16 16 0 0 0 0 18.88C97.77 356.89 177.72 402 255.66 402s157.89-45.11 220.83-135.33a16 16 0 0 0 0-18.88C413.55 157.11 333.6 112 255.66 112Z',
      'stroke-width': 32,
    }),
    h('circle', { cx: 256, cy: 256, r: 80, 'stroke-miterlimit': 10, 'stroke-width': 32 }),
  ]);
}

function renderCustomFieldValue(row: DirectoryUserItem, field: UserFieldDef) {
  const value = row.customFields?.[field.fieldKey];
  if (!field.masked || isEmptyCustomValue(value)) {
    return formatCustomFieldValue(value);
  }
  const key = maskedFieldKey(row, field.fieldKey);
  const revealed = revealedMaskedFields.value.has(key);
  return h('span', { class: 'masked-field' }, [
    h('span', { class: revealed ? 'masked-field-value' : 'masked-field-placeholder' }, revealed ? formatCustomFieldValue(value) : '*****'),
    h(
      'button',
      {
        class: 'masked-field-toggle',
        type: 'button',
        title: revealed ? t('隐藏原始信息') : t('查看原始信息'),
        'aria-label': revealed ? t('隐藏原始信息') : t('查看原始信息'),
        style:
          'display:inline-flex;align-items:center;justify-content:center;width:24px;height:24px;flex:0 0 24px;border:0;border-radius:6px;background:transparent;color:#64748b;cursor:pointer;padding:0;',
        onClick: (event: MouseEvent) => {
          event.stopPropagation();
          toggleMaskedField(row, field.fieldKey);
        },
      },
      [renderMaskedFieldIcon(revealed)],
    ),
  ]);
}

function defaultCustomFields(values: Record<string, unknown> = {}) {
  return activeUserFields.value.reduce<Record<string, any>>((result, field) => {
    const value = values[field.fieldKey];
    if (field.fieldType === 'multiselect') {
      result[field.fieldKey] = Array.isArray(value) ? value : [];
    } else {
      result[field.fieldKey] = value ?? '';
    }
    return result;
  }, {});
}

function buildCustomFieldPayload() {
  const payload: Record<string, unknown> = {};
  for (const field of activeUserFields.value) {
    const value = userForm.value.customFields[field.fieldKey];
    if (field.required && (value === '' || value === null || value === undefined || (Array.isArray(value) && value.length === 0))) {
      message.warning(t('请填写 {name}', { name: field.label }));
      return null;
    }
    if (field.fieldType === 'multiselect') {
      payload[field.fieldKey] = Array.isArray(value) ? value : [];
    } else {
      payload[field.fieldKey] = value === '' ? null : value;
    }
  }
  return payload;
}

function confirmDanger(content: string) {
  return new Promise<boolean>((resolve) => {
    dialog.warning({
      title: t('确认操作'),
      content,
      positiveText: t('确认'),
      negativeText: t('取消'),
      onPositiveClick: () => resolve(true),
      onNegativeClick: () => resolve(false),
      onClose: () => resolve(false),
    });
  });
}

function isValidEmail(value: string) {
  return !value || /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value);
}

function isValidPhone(value: string) {
  return !value || /^1[3-9]\d{9}$/.test(value) || /^\+\d{7,20}$/.test(value);
}

const deptEditorVisible = ref(false);
const deptEditorMode = ref<'create' | 'edit'>('create');
const deptForm = ref({
  id: '',
  name: '',
  status: 'active' as 'active' | 'disabled',
  parentId: null as string | null,
});
const deptEditorTitle = computed(() => (deptEditorMode.value === 'create' ? t('新增部门') : t('编辑部门')));

const deptMoveVisible = ref(false);
const moveForm = ref({ parentId: null as string | null });

const userEditorVisible = ref(false);
const userEditorMode = ref<'create' | 'edit'>('create');
const userForm = ref({
  id: '',
  name: '',
  mobile: '',
  email: '',
  status: 'active' as 'active' | 'disabled',
  source: 'local' as 'local' | 'dingtalk' | 'wecom' | 'feishu',
  sourceUserId: '',
  loginName: '',
  credentialPassword: '',
  primaryDepartmentId: '',
  departmentIds: [] as string[],
  customFields: {} as Record<string, any>,
  primaryRoleId: '',
  roleIds: [] as string[],
});
const userEditorTitle = computed(() => (userEditorMode.value === 'create' ? t('新增用户') : t('编辑用户')));

const fieldManagerVisible = ref(false);
const fieldEditorVisible = ref(false);
const fieldEditorMode = ref<'create' | 'edit'>('create');
const fieldForm = ref({
  id: '',
  fieldKey: '',
  label: '',
  fieldType: 'text' as UserFieldDef['fieldType'],
  required: false,
  optionsText: '',
  rows: 3,
  masked: false,
  enabled: true,
  sort: 0,
});
const fieldEditorTitle = computed(() => (fieldEditorMode.value === 'create' ? t('新增字段') : t('编辑字段')));
const fieldTypeOptions = computed<SelectOption[]>(() => [
  { label: t('单行文本'), value: 'text' },
  { label: t('多行文本'), value: 'textarea' },
  { label: t('单选'), value: 'select' },
  { label: t('多选'), value: 'multiselect' },
]);

const inviteVisible = ref(false);
const inviteForm = ref({
  defaultDepartmentId: null as string | null,
  expiresHours: 72,
  primaryRoleId: '',
  roleIds: [] as string[],
});
const inviteCapabilityPreview = computed(() => {
  const selected = positionRoles.value.filter(role => inviteForm.value.roleIds.includes(role.id));
  const capabilitySet = new Set<string>();
  selected.forEach(role => Object.entries(role.capabilities).forEach(([key, enabled]) => { if (enabled) capabilitySet.add(capabilityNames[key] || key); }));
  const toolAll = selected.some(role => role.toolAccessMode === 'all');
  const skillAll = selected.some(role => role.skillAccessMode === 'all');
  const toolCount = new Set(selected.flatMap(role => role.toolIds)).size;
  const skillCount = new Set(selected.flatMap(role => role.skillIds)).size;
  if (!selected.length) return '';
  return `${[...capabilitySet].join('、') || '普通问答'}；${toolAll ? '全部工具' : `${toolCount} 个工具`}；${skillAll ? '全部 Skill' : `${skillCount} 个 Skill`}`;
});

function syncPrimaryRole(roleId: string) {
  userForm.value.roleIds = Array.from(new Set([roleId, ...userForm.value.roleIds.filter(Boolean)]));
}

function syncInvitePrimaryRole(roleId: string) {
  inviteForm.value.roleIds = Array.from(new Set([roleId, ...inviteForm.value.roleIds.filter(Boolean)]));
}
const inviteResult = ref<UserInviteLinkResult>({
  inviteUrl: '',
  token: '',
  purpose: 'register',
  expiresAt: '',
});

function openCreateDept(parentId?: string | null) {
  deptEditorMode.value = 'create';
  const resolvedParentId = (typeof parentId === 'string' ? parentId : selectedDeptId.value) || null;
  deptForm.value = { id: '', name: '', status: 'active', parentId: resolvedParentId };
  deptEditorVisible.value = true;
}

function openEditDept(deptId?: string) {
  const targetId = (typeof deptId === 'string' ? deptId : selectedDeptId.value) || '';
  if (!targetId) return;
  const target = findDepartmentById(departments.value, targetId);
  if (!target) return;
  deptEditorMode.value = 'edit';
  deptForm.value = { id: target.id, name: target.name, status: target.status, parentId: target.parentId };
  deptEditorVisible.value = true;
}

function openMoveDept() {
  if (!selectedDeptId.value) return;
  moveForm.value.parentId = null;
  deptMoveVisible.value = true;
}

async function saveDepartment() {
  if (!deptForm.value.name.trim()) {
    message.warning(t('请填写部门名称'));
    return;
  }
  saving.value = true;
  try {
    if (deptEditorMode.value === 'create') {
      await createDepartment({
        name: deptForm.value.name.trim(),
        parentId: deptForm.value.parentId,
        status: deptForm.value.status,
      });
      message.success(t('部门已创建'));
    } else {
      await updateDepartment(deptForm.value.id, {
        name: deptForm.value.name.trim(),
        status: deptForm.value.status,
      });
      message.success(t('部门已更新'));
    }
    deptEditorVisible.value = false;
    await loadDepartments();
    await loadUsers();
  } catch (error) {
    message.error(parseError(error));
  } finally {
    saving.value = false;
  }
}

async function saveMoveDepartment() {
  if (!selectedDeptId.value) return;
  if (moveForm.value.parentId && selectedMoveBlockedDeptIds.value.has(moveForm.value.parentId)) {
    message.warning(t('不能移动到自身或子部门下'));
    return;
  }
  saving.value = true;
  try {
    await moveDepartment(selectedDeptId.value, { parentId: moveForm.value.parentId });
    message.success(t('部门已移动'));
    deptMoveVisible.value = false;
    await loadDepartments();
    await loadUsers();
  } catch (error) {
    message.error(parseError(error));
  } finally {
    saving.value = false;
  }
}

async function deleteSelectedDept() {
  if (!selectedDeptId.value) return;
  const target = findDepartmentById(departments.value, selectedDeptId.value);
  if (!(await confirmDanger(t('确认删除部门 {name} ? 删除前请确保没有子部门和用户。', { name: target?.name || '' })))) return;
  try {
    await deleteDepartment(selectedDeptId.value);
    message.success(t('部门已删除'));
    await loadDepartments();
    await loadUsers();
  } catch (error) {
    message.error(parseError(error));
  }
}

function openCreateUser() {
  userEditorMode.value = 'create';
  userForm.value = {
    id: '',
    name: '',
    mobile: '',
    email: '',
    status: 'active',
    source: 'local',
    sourceUserId: '',
    loginName: '',
    credentialPassword: '',
    primaryDepartmentId: selectedDeptId.value || firstDepartmentId(departments.value),
    departmentIds: selectedDeptId.value ? [selectedDeptId.value] : [],
    customFields: defaultCustomFields(),
    primaryRoleId: positionRoles.value.find(role => !role.protected && role.status === 'active')?.id || positionRoles.value.find(role => role.status === 'active')?.id || '',
    roleIds: [],
  };
  syncPrimaryRole(userForm.value.primaryRoleId);
  userEditorVisible.value = true;
}

async function openEditUser(row: DirectoryUserItem) {
  userEditorMode.value = 'edit';
  let customFields = row.customFields || {};
  try {
    const result = await fetchUserCustomFields(row.id);
    customFields = result.fields.reduce<Record<string, unknown>>((values, field) => {
      values[field.fieldKey] = field.value;
      return values;
    }, {});
  } catch (error) {
    message.warning(parseError(error));
  }
  userForm.value = {
    id: row.id,
    name: row.name,
    mobile: row.mobile,
    email: row.email,
    status: row.status,
    source: row.source,
    sourceUserId: row.sourceUserId,
    loginName: row.loginName,
    credentialPassword: '',
    primaryDepartmentId: row.primaryDepartmentId,
    departmentIds: row.primaryDepartmentId ? [row.primaryDepartmentId] : [],
    customFields: defaultCustomFields(customFields),
    primaryRoleId: row.positionRoles?.find(role => role.isPrimary)?.id || '',
    roleIds: row.positionRoles?.map(role => role.id) || [],
  };
  userEditorVisible.value = true;
}

async function saveUser() {
  if (!userForm.value.name.trim()) {
    message.warning(t('请填写姓名'));
    return;
  }
  if (!userForm.value.primaryDepartmentId) {
    message.warning(t('请选择主部门'));
    return;
  }
  if (!userForm.value.primaryRoleId) {
    message.warning(t('请选择主要岗位角色'));
    return;
  }
  syncPrimaryRole(userForm.value.primaryRoleId);
  if (!userForm.value.mobile.trim()) {
    message.warning(t('请填写手机号'));
    return;
  }
  if (!userForm.value.email.trim()) {
    message.warning(t('请填写邮箱'));
    return;
  }
  if (!isValidPhone(userForm.value.mobile.trim())) {
    message.warning(t('手机号格式不正确'));
    return;
  }
  if (!isValidEmail(userForm.value.email.trim())) {
    message.warning(t('邮箱格式不正确'));
    return;
  }
  if (userForm.value.source === 'local' && !userForm.value.loginName.trim()) {
    message.warning(t('请填写登录名'));
    return;
  }
  if (
    userForm.value.source === 'local'
    && userEditorMode.value === 'create'
    && userForm.value.credentialPassword.length < 10
  ) {
    message.warning(t('初始密码至少 10 位'));
    return;
  }
  if (userForm.value.credentialPassword && userForm.value.credentialPassword.length < 10) {
    message.warning(t('密码至少 10 位'));
    return;
  }
  const customFieldPayload = buildCustomFieldPayload();
  if (customFieldPayload === null) {
    return;
  }
  saving.value = true;
  try {
    let savedUserId = userForm.value.id;
    if (userEditorMode.value === 'create') {
      const result = await createUser({
        name: userForm.value.name.trim(),
        mobile: userForm.value.mobile.trim(),
        email: userForm.value.email.trim(),
        status: userForm.value.status,
        source: userForm.value.source,
        sourceUserId: userForm.value.sourceUserId.trim(),
        loginName: userForm.value.loginName.trim(),
        primaryDepartmentId: userForm.value.primaryDepartmentId,
        departmentIds: userForm.value.departmentIds.length ? userForm.value.departmentIds : [userForm.value.primaryDepartmentId],
        initialPassword: userForm.value.credentialPassword,
        primaryRoleId: userForm.value.primaryRoleId,
        roleIds: userForm.value.roleIds,
      });
      savedUserId = String(result.id || '');
    } else {
      await updateUser(userForm.value.id, {
        name: userForm.value.name.trim(),
        mobile: userForm.value.mobile.trim(),
        email: userForm.value.email.trim(),
        status: userForm.value.status,
        source: userForm.value.source,
        sourceUserId: userForm.value.sourceUserId.trim(),
        loginName: userForm.value.loginName.trim(),
        primaryDepartmentId: userForm.value.primaryDepartmentId,
        departmentIds: userForm.value.departmentIds.length ? userForm.value.departmentIds : [userForm.value.primaryDepartmentId],
        resetPassword: userForm.value.credentialPassword,
        primaryRoleId: userForm.value.primaryRoleId,
        roleIds: userForm.value.roleIds,
      });
    }
    if (savedUserId && activeUserFields.value.length) {
      await updateUserCustomFields(savedUserId, customFieldPayload);
    }
    message.success(userEditorMode.value === 'create' ? t('用户已创建') : t('用户已更新'));
    userEditorVisible.value = false;
    await loadUsers();
    await loadDepartments();
  } catch (error) {
    message.error(parseError(error));
  } finally {
    saving.value = false;
  }
}

function openInviteUser() {
  inviteForm.value = {
    defaultDepartmentId: selectedDeptId.value || null,
    expiresHours: 72,
    primaryRoleId: positionRoles.value.find(role => !role.protected && role.status === 'active')?.id || positionRoles.value.find(role => role.status === 'active')?.id || '',
    roleIds: [],
  };
  syncInvitePrimaryRole(inviteForm.value.primaryRoleId);
  inviteResult.value = {
    inviteUrl: '',
    token: '',
    purpose: 'register',
    expiresAt: '',
  };
  inviteVisible.value = true;
}

async function generateInviteLink() {
  if (!inviteForm.value.primaryRoleId) {
    message.warning(t('请选择岗位角色'));
    return;
  }
  syncInvitePrimaryRole(inviteForm.value.primaryRoleId);
  saving.value = true;
  try {
    const result = await createOrgInviteLink({
      defaultDepartmentId: inviteForm.value.defaultDepartmentId,
      expiresHours: inviteForm.value.expiresHours,
      primaryRoleId: inviteForm.value.primaryRoleId,
      roleIds: inviteForm.value.roleIds,
    });
    inviteResult.value = result;
    message.success(t('邀请链接已生成'));
  } catch (error) {
    message.error(parseError(error));
  } finally {
    saving.value = false;
  }
}

async function copyInviteUrl() {
  if (!inviteResult.value.inviteUrl) return;
  try {
    await navigator.clipboard.writeText(inviteResult.value.inviteUrl);
    message.success(t('邀请链接已复制'));
  } catch (_error) {
    message.warning(t('复制失败，请手动复制'));
  }
}

async function copyInviteCode() {
  if (!inviteResult.value.token) return;
  try {
    await navigator.clipboard.writeText(inviteResult.value.token);
    message.success(t('邀请码已复制'));
  } catch {
    message.warning(t('复制失败，请手动复制'));
  }
}

async function deleteUserRow(row: DirectoryUserItem) {
  if (!(await confirmDanger(t('确认删除用户 {name} ? 删除后不可恢复。', { name: row.name })))) return;
  try {
    await deleteUser(row.id);
    message.success(t('用户已删除'));
    await loadUsers();
    await loadDepartments();
  } catch (error) {
    message.error(parseError(error));
  }
}

async function updateUserStatus(row: DirectoryUserItem, status: 'active' | 'disabled') {
  try {
    if (status === 'disabled') {
      await disableUser(row.id);
    } else {
      await enableUser(row.id);
    }
    return;
  } catch (error) {
    if (!axios.isAxiosError(error) || error.response?.status !== 404) {
      throw error;
    }
  }
  await updateUser(row.id, {
    name: row.name,
    mobile: row.mobile,
    email: row.email,
    status,
    source: row.source,
    sourceUserId: row.sourceUserId,
    loginName: row.loginName,
    primaryDepartmentId: row.primaryDepartmentId,
    departmentIds: row.primaryDepartmentId ? [row.primaryDepartmentId] : [],
    resetPassword: '',
    primaryRoleId: row.positionRoles?.find(role => role.isPrimary)?.id || row.positionRoles?.[0]?.id || '',
    roleIds: row.positionRoles?.map(role => role.id) || [],
  });
}

async function disableUserRow(row: DirectoryUserItem) {
  if (!(await confirmDanger(t('确认停用用户 {name} ?', { name: row.name })))) return;
  try {
    await updateUserStatus(row, 'disabled');
    message.success(t('用户已停用'));
    await loadUsers();
  } catch (error) {
    message.error(parseError(error));
  }
}

async function enableUserRow(row: DirectoryUserItem) {
  if (!(await confirmDanger(t('确认启用用户 {name} ?', { name: row.name })))) return;
  try {
    await updateUserStatus(row, 'active');
    message.success(t('用户已启用'));
    await loadUsers();
  } catch (error) {
    message.error(parseError(error));
  }
}

function openCreateField() {
  fieldEditorMode.value = 'create';
  fieldForm.value = {
    id: '',
    fieldKey: '',
    label: '',
    fieldType: 'text',
    required: false,
    optionsText: '',
    rows: 3,
    masked: false,
    enabled: true,
    sort: 0,
  };
  fieldEditorVisible.value = true;
}

function openEditField(row: UserFieldDef) {
  fieldEditorMode.value = 'edit';
  fieldForm.value = {
    id: row.id,
    fieldKey: row.fieldKey,
    label: row.label,
    fieldType: row.fieldType,
    required: row.required,
    optionsText: (row.options || []).join(','),
    rows: row.rows || 3,
    masked: row.masked,
    enabled: row.enabled,
    sort: row.sort,
  };
  fieldEditorVisible.value = true;
}

async function saveField() {
  const fieldKey = fieldForm.value.fieldKey.trim();
  if (!fieldKey || !fieldForm.value.label.trim()) {
    message.warning(t('请填写字段 key 和名称'));
    return;
  }
  if (!/^[a-zA-Z0-9_]{2,64}$/.test(fieldKey)) {
    message.warning(t('字段Key只能包含英文字母、数字、下划线，长度为 2-64 位'));
    return;
  }
  const options = fieldForm.value.optionsText
    .split(',')
    .map((s) => s.trim())
    .filter(Boolean);
  if ((fieldForm.value.fieldType === 'select' || fieldForm.value.fieldType === 'multiselect') && !options.length) {
    message.warning(t('请填写选项值'));
    return;
  }
  saving.value = true;
  try {
    const payload = {
      fieldKey,
      label: fieldForm.value.label.trim(),
      fieldType: fieldForm.value.fieldType,
      required: fieldForm.value.required,
      options,
      rows: fieldForm.value.fieldType === 'textarea' ? fieldForm.value.rows : 3,
      masked: fieldForm.value.masked,
      enabled: fieldForm.value.enabled,
      sort: fieldForm.value.sort,
    };
    if (fieldEditorMode.value === 'create') {
      await createUserFieldDef(payload);
      message.success(t('字段已创建'));
    } else {
      await updateUserFieldDef(fieldForm.value.id, payload);
      message.success(t('字段已更新'));
    }
    fieldEditorVisible.value = false;
    await loadFieldDefs();
  } catch (error) {
    message.error(parseError(error));
  } finally {
    saving.value = false;
  }
}

async function removeField(row: UserFieldDef) {
  if (!(await confirmDanger(t('确认删除字段 {name} ?', { name: row.label })))) return;
  try {
    await deleteUserFieldDef(row.id);
    message.success(t('字段已删除'));
    await loadFieldDefs();
  } catch (error) {
    message.error(parseError(error));
  }
}

async function loadDepartments() {
  const prevExpanded = new Set(expandedDeptKeys.value);
  departments.value = await fetchDepartmentTree();
  const allDeptIds = collectDeptIds(departments.value);
  if (prevExpanded.size === 0) {
    expandedDeptKeys.value = allDeptIds;
  } else {
    const merged = new Set([...allDeptIds, ...Array.from(prevExpanded)]);
    expandedDeptKeys.value = Array.from(merged);
  }
  if (!selectedDeptKeys.value.length) {
    selectedDeptKeys.value = [firstDepartmentId(departments.value)];
  } else if (selectedDeptKeys.value[0] && !findDepartmentById(departments.value, selectedDeptKeys.value[0])) {
    selectedDeptKeys.value = [firstDepartmentId(departments.value)];
  }
}

async function loadUsers() {
  users.value = await fetchUsers({
    departmentId: selectedDeptId.value || undefined,
    statusFilter: statusFilter.value || undefined,
    sourceFilter: sourceFilter.value || undefined,
  });
}

async function loadFieldDefs() {
  fieldDefs.value = await fetchUserFieldDefs();
}

function firstDepartmentId(nodes: DepartmentNode[]): string {
  if (!nodes.length) return '';
  return nodes[0].id;
}

function collectDeptIds(nodes: DepartmentNode[]): string[] {
  const ids: string[] = [];
  const dfs = (items: DepartmentNode[]) => {
    for (const item of items) {
      ids.push(item.id);
      if (item.children?.length) {
        dfs(item.children);
      }
    }
  };
  dfs(nodes);
  return ids;
}

function findDepartmentById(nodes: DepartmentNode[], id: string): DepartmentNode | null {
  for (const node of nodes) {
    if (node.id === id) return node;
    const sub = findDepartmentById(node.children || [], id);
    if (sub) return sub;
  }
  return null;
}

onMounted(async () => {
  try {
    await loadDepartments();
    positionRoles.value = await listPositionRoles();
    await Promise.all([loadUsers(), loadFieldDefs()]);
  } catch (error) {
    message.error(parseError(error));
  }
});
</script>

<style scoped>
.user-page {
  height: calc(100vh - 98px);
  min-height: 520px;
  min-width: 0;
  max-width: 100%;
  overflow: hidden;
}

.user-card {
  height: 100%;
  min-width: 0;
  max-width: 100%;
  overflow: hidden;
}

:deep(.user-card .n-card__content) {
  height: 100%;
  min-width: 0;
  overflow: hidden;
}

.user-layout {
  height: 100%;
  display: grid;
  grid-template-columns: 280px minmax(0, 1fr);
  gap: 14px;
  min-width: 0;
  max-width: 100%;
  overflow: hidden;
}

.dept-panel {
  border: 1px solid #eceff5;
  border-radius: 10px;
  padding: 10px;
  display: flex;
  flex-direction: column;
  gap: 10px;
  min-width: 0;
  overflow: hidden;
}

.panel-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.panel-title {
  font-size: 14px;
  font-weight: 600;
}

.tree-wrap {
  flex: 1;
  min-height: 0;
  overflow: auto;
}

:deep(.dept-node-label) {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  width: 100%;
}

:deep(.dept-node-title) {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

:deep(.dept-node-actions) {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  opacity: 0;
  transition: opacity 0.15s ease;
}

:deep(.n-tree-node-content:hover .dept-node-actions) {
  opacity: 1;
}

:deep(.dept-node-action) {
  width: 18px;
  height: 18px;
  border: 1px solid #d9dce4;
  border-radius: 4px;
  background: #fff;
  color: #51607a;
  font-size: 11px;
  line-height: 1;
  cursor: pointer;
  padding: 0;
}

:deep(.dept-node-action:hover) {
  border-color: #9fb5ff;
  color: #366aff;
}

.list-panel {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
  min-width: 0;
}

.toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 10px;
  margin-bottom: 10px;
  min-width: 0;
}

.toolbar :deep(.n-space) {
  flex-wrap: wrap;
  min-width: 0;
}

.compact-toolbar {
  margin-bottom: 10px;
}

.invite-link-row {
  width: 100%;
  display: flex;
  align-items: center;
  gap: 8px;
}

.invite-link-block {
  width: 100%;
}

.invite-expire-text {
  margin-top: 6px;
}

.table-area {
  flex: 1 1 0;
  width: 100%;
  min-height: 0;
  min-width: 0;
  max-width: 100%;
  overflow: hidden;
}

.user-table,
:deep(.user-table .n-data-table-wrapper),
:deep(.user-table .n-data-table-base-table),
:deep(.user-table .n-data-table-base-table-body) {
  height: 100%;
  max-width: 100%;
}

.pager-row {
  margin-top: 10px;
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

.source-tag {
  color: #366aff;
}

.masked-field {
  display: inline-flex;
  align-items: center;
  max-width: 100%;
  gap: 6px;
}

.masked-field-value,
.masked-field-placeholder {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.masked-field-placeholder {
  color: #6b7280;
  letter-spacing: 1px;
  font-weight: 700;
}

.masked-field-toggle {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  flex: 0 0 24px;
  border: 0;
  border-radius: 6px;
  background: transparent;
  color: #64748b;
  cursor: pointer;
  padding: 0;
  transition: background-color 0.18s ease, color 0.18s ease;
}

.masked-field-toggle:hover,
.masked-field-toggle:focus-visible {
  background: rgba(54, 106, 255, 0.1);
  color: #366aff;
  outline: none;
}

.masked-field-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 15px;
  height: 15px;
}

.masked-field-icon :deep(svg) {
  display: block;
  width: 15px;
  height: 15px;
}

.status-on {
  color: #18a058;
}

.status-off {
  color: #767c82;
}

:deep(.role-tags) {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
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
