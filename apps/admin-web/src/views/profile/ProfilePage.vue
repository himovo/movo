<template>
  <div class="profile-page">
    <section class="profile-summary">
      <div class="avatar-editor">
        <button class="avatar-button" type="button" :disabled="uploadingAvatar" @click="openAvatarPicker">
          <span class="profile-avatar-large" :class="{ 'has-image': showProfileAvatar }">
            <img v-if="showProfileAvatar" :key="profileAvatarUrl" :src="profileAvatarUrl" alt="" @error="handleProfileAvatarError" />
            <span v-else>{{ profileInitial }}</span>
          </span>
          <span>{{ uploadingAvatar ? t('上传中') : t('更换头像') }}</span>
        </button>
        <input
          ref="avatarInputRef"
          type="file"
          class="avatar-input"
          accept="image/png,image/jpeg,image/webp"
          @change="handleAvatarChange"
        />
      </div>
      <div class="summary-main">
        <div class="summary-kicker">{{ t('个人中心') }}</div>
        <h1>{{ profileDisplayName }}</h1>
        <div class="summary-meta">
          <n-tag size="small" :bordered="false" type="info">{{ authStore.profile?.roleName || t('组织管理员') }}</n-tag>
          <span>{{ authStore.profile?.orgName || t('组织空间') }}</span>
          <span>{{ maskedUsername }}</span>
        </div>
      </div>
    </section>

    <section class="profile-grid">
      <n-card class="profile-card" :bordered="false" size="large">
        <template #header>
          <div class="card-header">
            <span>{{ t('基本信息') }}</span>
            <n-button text type="primary" :loading="loadingProfile" @click="loadProfile">{{ t('刷新') }}</n-button>
          </div>
        </template>

        <n-form
          ref="profileFormRef"
          :model="profileForm"
          :rules="profileRules"
          label-placement="top"
          require-mark-placement="right-hanging"
        >
          <n-form-item :label="t('姓名')" path="name">
            <n-input v-model:value="profileForm.name" :placeholder="t('请输入姓名或昵称')" />
          </n-form-item>
          <n-form-item :label="t('邮箱')" path="email">
            <n-input v-model:value="profileForm.email" :placeholder="t('请输入邮箱')" />
          </n-form-item>
          <n-form-item :label="t('手机号')" path="phone">
            <n-input v-model:value="profileForm.phone" :placeholder="t('请输入手机号')" />
          </n-form-item>

          <div class="readonly-grid">
            <div class="readonly-item">
              <span>{{ t('登录账号') }}</span>
              <strong>{{ maskedUsername }}</strong>
            </div>
            <div class="readonly-item">
              <span>{{ t('所属组织') }}</span>
              <strong>{{ authStore.profile?.orgName || '-' }}</strong>
            </div>
            <div class="readonly-item">
              <span>{{ t('当前角色') }}</span>
              <strong>{{ authStore.profile?.roleName || '-' }}</strong>
            </div>
            <div class="readonly-item">
              <span>{{ t('最近登录') }}</span>
              <strong>{{ formatAdminDateTime(authStore.profile?.lastLoginAt, t('暂无记录')) }}</strong>
            </div>
          </div>

          <div class="form-actions">
            <n-button :disabled="savingProfile || !profileDirty" @click="resetProfileForm">{{ t('重置') }}</n-button>
            <n-button type="primary" :loading="savingProfile" :disabled="!profileDirty" @click="saveProfile">
              {{ t('保存资料') }}
            </n-button>
          </div>
        </n-form>
      </n-card>

      <n-card class="profile-card" :bordered="false" size="large">
        <template #header>{{ t('账号安全') }}</template>

        <div class="security-note">
          <strong>{{ t('修改登录密码') }}</strong>
          <span>{{ t('密码修改成功后，需要重新登录管理后台。') }}</span>
        </div>

        <n-form
          ref="passwordFormRef"
          :model="passwordForm"
          :rules="passwordRules"
          label-placement="top"
          require-mark-placement="right-hanging"
        >
          <n-form-item :label="t('当前密码')" path="currentPassword">
            <n-input
              v-model:value="passwordForm.currentPassword"
              type="password"
              show-password-on="click"
              :placeholder="t('请输入当前密码')"
            />
          </n-form-item>
          <n-form-item :label="t('新密码')" path="newPassword">
            <n-input
              v-model:value="passwordForm.newPassword"
              type="password"
              show-password-on="click"
              :placeholder="t('至少 10 位字符')"
            />
          </n-form-item>
          <n-form-item :label="t('确认新密码')" path="confirmPassword">
            <n-input
              v-model:value="passwordForm.confirmPassword"
              type="password"
              show-password-on="click"
              :placeholder="t('请再次输入新密码')"
            />
          </n-form-item>

          <div class="form-actions">
            <n-button :disabled="changingPassword" @click="resetPasswordForm">{{ t('清空') }}</n-button>
            <n-button type="primary" :loading="changingPassword" @click="submitPasswordChange">
              {{ t('修改密码') }}
            </n-button>
          </div>
        </n-form>
      </n-card>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue';
import { useMessage, type FormInst, type FormRules } from 'naive-ui';
import { useRouter } from 'vue-router';
import { changeCurrentPassword, fetchCurrentProfile, updateCurrentProfile, uploadCurrentAvatar } from '@/api/auth';
import { resolveAdminAssetUrlWithVersion } from '@/composables/adminAsset';
import { formatAdminDateTime } from '@/composables/adminTimezone';
import { t } from '@/composables/i18n';
import { displayAdminName, displayProfileNameForEdit, isMobileLike, maskMobile } from '@/composables/privacy';
import { useAuthStore } from '@/stores/auth';

const router = useRouter();
const message = useMessage();
const authStore = useAuthStore();

const profileFormRef = ref<FormInst | null>(null);
const passwordFormRef = ref<FormInst | null>(null);
const avatarInputRef = ref<HTMLInputElement | null>(null);
const loadingProfile = ref(false);
const savingProfile = ref(false);
const changingPassword = ref(false);
const uploadingAvatar = ref(false);

const profileForm = reactive({
  name: '',
  email: '',
  phone: '',
});

const profileSnapshot = reactive({
  name: '',
  email: '',
  phone: '',
});

const passwordForm = reactive({
  currentPassword: '',
  newPassword: '',
  confirmPassword: '',
});

const profileRules: FormRules = {
  name: [{ required: true, message: t('请输入姓名或昵称'), trigger: ['input', 'blur'] }],
  email: [
    {
      validator: (_rule, value: string) => {
        if (!value) return true;
        return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value);
      },
      message: t('请输入有效邮箱'),
      trigger: ['input', 'blur'],
    },
  ],
};

const passwordRules: FormRules = {
  currentPassword: [{ required: true, message: t('请输入当前密码'), trigger: ['input', 'blur'] }],
  newPassword: [
    { required: true, message: t('请输入新密码'), trigger: ['input', 'blur'] },
    { min: 10, message: t('新密码至少 10 位'), trigger: ['input', 'blur'] },
    {
      validator: (_rule, value: string) => value !== passwordForm.currentPassword,
      message: t('新密码不能与当前密码相同'),
      trigger: ['input', 'blur'],
    },
  ],
  confirmPassword: [
    { required: true, message: t('请再次输入新密码'), trigger: ['input', 'blur'] },
    {
      validator: (_rule, value: string) => value === passwordForm.newPassword,
      message: t('两次输入的新密码不一致'),
      trigger: ['input', 'blur'],
    },
  ],
};

const profileDisplayName = computed(() =>
  profileForm.name.trim() ? profileForm.name.trim() : displayAdminName(authStore.profile, t('管理员')),
);
const profileAvatarUrl = computed(() => resolveAdminAssetUrlWithVersion(authStore.profile?.avatarUrl, authStore.profile?.avatarUpdatedAt));
const profileAvatarFailedUrl = ref('');
const showProfileAvatar = computed(() => Boolean(profileAvatarUrl.value) && profileAvatarFailedUrl.value !== profileAvatarUrl.value);
const profileInitial = computed(() =>
  isMobileLike(profileDisplayName.value) || profileDisplayName.value.includes('****')
    ? '管'
    : profileDisplayName.value.slice(0, 1).toUpperCase(),
);
const maskedUsername = computed(() => maskMobile(authStore.profile?.username, authStore.profile?.username || '-'));
const profileDirty = computed(
  () =>
    profileForm.name !== profileSnapshot.name ||
    profileForm.email !== profileSnapshot.email ||
    profileForm.phone !== profileSnapshot.phone,
);

function applyProfile(profile: NonNullable<typeof authStore.profile>) {
  authStore.setProfile(profile);
  profileForm.name = displayProfileNameForEdit(profile);
  profileForm.email = profile.email || '';
  profileForm.phone = profile.phone || '';
  profileSnapshot.name = profileForm.name;
  profileSnapshot.email = profileForm.email;
  profileSnapshot.phone = profileForm.phone;
}

async function loadProfile() {
  loadingProfile.value = true;
  try {
    const profile = await fetchCurrentProfile();
    applyProfile(profile);
  } catch (error) {
    message.error(t('个人资料加载失败'));
  } finally {
    loadingProfile.value = false;
  }
}

function resetProfileForm() {
  profileForm.name = profileSnapshot.name;
  profileForm.email = profileSnapshot.email;
  profileForm.phone = profileSnapshot.phone;
}

function openAvatarPicker() {
  if (uploadingAvatar.value) return;
  avatarInputRef.value?.click();
}

function handleProfileAvatarError() {
  profileAvatarFailedUrl.value = profileAvatarUrl.value;
}

async function handleAvatarChange(event: Event) {
  const input = event.target as HTMLInputElement;
  const file = input.files?.[0];
  if (!file) return;
  const allowedTypes = new Set(['image/jpeg', 'image/png', 'image/webp']);
  if (!allowedTypes.has(file.type)) {
    message.error(t('头像仅支持 JPG、PNG、WebP'));
    input.value = '';
    return;
  }
  if (file.size > 2 * 1024 * 1024) {
    message.error(t('头像文件不能超过 2MB'));
    input.value = '';
    return;
  }
  uploadingAvatar.value = true;
  try {
    const profile = await uploadCurrentAvatar(file);
    profileAvatarFailedUrl.value = '';
    applyProfile(profile);
    message.success(t('头像已更新'));
  } catch (error) {
    message.error(t('头像上传失败'));
  } finally {
    uploadingAvatar.value = false;
    input.value = '';
  }
}

async function saveProfile() {
  await profileFormRef.value?.validate();
  savingProfile.value = true;
  try {
    const profile = await updateCurrentProfile({
      name: profileForm.name.trim(),
      email: profileForm.email.trim(),
      phone: profileForm.phone.trim(),
    });
    applyProfile(profile);
    message.success(t('个人资料已保存'));
  } catch (error) {
    message.error(t('保存个人资料失败'));
  } finally {
    savingProfile.value = false;
  }
}

function resetPasswordForm() {
  passwordForm.currentPassword = '';
  passwordForm.newPassword = '';
  passwordForm.confirmPassword = '';
}

async function submitPasswordChange() {
  await passwordFormRef.value?.validate();
  changingPassword.value = true;
  try {
    await changeCurrentPassword({
      currentPassword: passwordForm.currentPassword,
      newPassword: passwordForm.newPassword,
    });
    message.success(t('密码已修改，请重新登录'));
    authStore.clearSession();
    router.push('/login');
  } catch (error) {
    message.error(t('修改密码失败，请检查当前密码'));
  } finally {
    changingPassword.value = false;
  }
}

onMounted(() => {
  if (authStore.profile) {
    applyProfile(authStore.profile);
  }
  loadProfile();
});
</script>

<style scoped>
.profile-page {
  min-height: 100%;
  padding: 24px;
}

.profile-summary {
  display: flex;
  align-items: center;
  gap: 18px;
  margin-bottom: 18px;
  padding: 22px 24px;
  border: 1px solid rgba(87, 112, 160, 0.14);
  border-radius: 12px;
  background: rgba(255, 255, 255, 0.78);
  box-shadow: 0 10px 30px rgba(28, 53, 94, 0.08);
}

html.dark .profile-summary {
  border-color: rgba(148, 163, 184, 0.16);
  background: rgba(17, 24, 39, 0.76);
  box-shadow: 0 10px 30px rgba(0, 0, 0, 0.28);
}

.summary-main {
  min-width: 0;
}

.avatar-editor {
  flex: 0 0 auto;
}

.avatar-button {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  min-width: 86px;
  min-height: 104px;
  padding: 0;
  border: 0;
  background: transparent;
  color: #366aff;
  cursor: pointer;
  font-size: 13px;
  font-weight: 600;
}

.avatar-button:disabled {
  cursor: not-allowed;
  opacity: 0.72;
}

.avatar-button:focus-visible {
  outline: 2px solid rgba(54, 106, 255, 0.55);
  outline-offset: 4px;
  border-radius: 12px;
}

.profile-avatar-large {
  display: inline-grid;
  place-items: center;
  width: 78px;
  height: 78px;
  overflow: hidden;
  border-radius: 50%;
  background: #366aff;
  color: #fff;
  font-size: 28px;
  font-weight: 700;
  line-height: 1;
}

.profile-avatar-large img {
  display: block;
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.avatar-input {
  display: none;
}

.summary-kicker {
  color: #5f736d;
  font-size: 13px;
  font-weight: 600;
}

html.dark .summary-kicker {
  color: #9ca3af;
}

.summary-main h1 {
  margin: 4px 0 8px;
  color: #17233d;
  font-size: 24px;
  line-height: 1.25;
}

html.dark .summary-main h1 {
  color: #f8fafc;
}

.summary-meta {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px 12px;
  color: #627086;
  font-size: 13px;
}

html.dark .summary-meta {
  color: #cbd5e1;
}

.profile-grid {
  display: grid;
  grid-template-columns: minmax(0, 1.1fr) minmax(320px, 0.9fr);
  gap: 18px;
}

.profile-card {
  border-radius: 12px;
  box-shadow: 0 10px 28px rgba(30, 57, 100, 0.08);
}

html.dark .profile-card {
  background: rgba(17, 24, 39, 0.78);
  box-shadow: 0 10px 28px rgba(0, 0, 0, 0.28);
}

.card-header,
.form-actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.readonly-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
  margin: 4px 0 18px;
}

.readonly-item {
  min-width: 0;
  padding: 12px;
  border-radius: 8px;
  background: rgba(54, 106, 255, 0.06);
}

html.dark .readonly-item {
  background: rgba(96, 165, 250, 0.1);
}

.readonly-item span,
.security-note span {
  display: block;
  color: #637083;
  font-size: 12px;
}

html.dark .readonly-item span,
html.dark .security-note span {
  color: #94a3b8;
}

.readonly-item strong {
  display: block;
  overflow: hidden;
  margin-top: 4px;
  color: #17233d;
  font-size: 14px;
  font-weight: 600;
  text-overflow: ellipsis;
  white-space: nowrap;
}

html.dark .readonly-item strong {
  color: #f8fafc;
}

.security-note {
  margin-bottom: 18px;
  padding: 12px 14px;
  border-radius: 8px;
  background: rgba(16, 185, 129, 0.08);
}

.security-note strong {
  display: block;
  margin-bottom: 4px;
  color: #135e46;
}

html.dark .security-note strong {
  color: #86efac;
}

.form-actions {
  justify-content: flex-end;
}

@media (max-width: 900px) {
  .profile-grid,
  .readonly-grid {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 640px) {
  .profile-page {
    padding: 16px;
  }

  .profile-summary {
    align-items: flex-start;
    padding: 18px;
  }

  .avatar-button {
    min-width: 78px;
    min-height: 96px;
  }
}
</style>
