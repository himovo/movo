<template>
  <div class="profile-page">
    <section class="profile-summary">
      <div class="avatar-editor">
        <button class="avatar-button" type="button" :disabled="uploadingAvatar" @click="openAvatarPicker">
          <span class="profile-avatar-large" :class="{ 'has-image': showProfileAvatar }">
            <img v-if="showProfileAvatar" :key="profileAvatarUrl" :src="profileAvatarUrl" alt="" @error="handleProfileAvatarError" />
            <span v-else>{{ profileInitial }}</span>
          </span>
          <span>{{ uploadingAvatar ? t('legacy.uploading') : t('additional.change_avatar') }}</span>
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
        <div class="summary-kicker">{{ t('legacy.profile') }}</div>
        <h1>{{ profileDisplayName }}</h1>
        <div class="summary-meta">
          <n-tag size="small" :bordered="false" type="info">{{ authStore.profile?.roleName || t('legacy.organization_administrator') }}</n-tag>
          <span>{{ authStore.profile?.orgName || t('legacy.org_space') }}</span>
          <span>{{ maskedUsername }}</span>
        </div>
      </div>
    </section>

    <section class="profile-grid">
      <n-card class="profile-card" :bordered="false" size="large">
        <template #header>
          <div class="card-header">
            <span>{{ t('additional.basic_information') }}</span>
            <n-button text type="primary" :loading="loadingProfile" @click="loadProfile">{{ t('legacy.refresh') }}</n-button>
          </div>
        </template>

        <n-form
          ref="profileFormRef"
          :model="profileForm"
          :rules="profileRules"
          label-placement="top"
          require-mark-placement="right-hanging"
        >
          <n-form-item :label="t('legacy.name')" path="name">
            <n-input v-model:value="profileForm.name" :placeholder="t('additional.enter_a_name_or_nickname')" />
          </n-form-item>
          <n-form-item :label="t('legacy.email')" path="email">
            <n-input v-model:value="profileForm.email" :placeholder="t('additional.enter_an_email_address_f2dc24d')" />
          </n-form-item>
          <n-form-item :label="t('legacy.mobile')" path="phone">
            <n-input v-model:value="profileForm.phone" :placeholder="t('additional.enter_a_phone_number_5ecce33')" />
          </n-form-item>

          <div class="readonly-grid">
            <div class="readonly-item">
              <span>{{ t('legacy.username') }}</span>
              <strong>{{ maskedUsername }}</strong>
            </div>
            <div class="readonly-item">
              <span>{{ t('additional.organization') }}</span>
              <strong>{{ authStore.profile?.orgName || '-' }}</strong>
            </div>
            <div class="readonly-item">
              <span>{{ t('additional.current_role') }}</span>
              <strong>{{ authStore.profile?.roleName || '-' }}</strong>
            </div>
            <div class="readonly-item">
              <span>{{ t('additional.last_sign_in') }}</span>
              <strong>{{ formatAdminDateTime(authStore.profile?.lastLoginAt, t('legacy.no_records')) }}</strong>
            </div>
          </div>

          <div class="form-actions">
            <n-button :disabled="savingProfile || !profileDirty" @click="resetProfileForm">{{ t('legacy.reset') }}</n-button>
            <n-button type="primary" :loading="savingProfile" :disabled="!profileDirty" @click="saveProfile">
              {{ t('additional.save_profile') }}
            </n-button>
          </div>
        </n-form>
      </n-card>

      <n-card class="profile-card" :bordered="false" size="large">
        <template #header>{{ t('additional.account_security') }}</template>

        <div class="security-note">
          <strong>{{ t('additional.change_sign_in_password') }}</strong>
          <span>{{ t('additional.after_changing_your_password_you_must_sign_in_to') }}</span>
        </div>

        <n-form
          ref="passwordFormRef"
          :model="passwordForm"
          :rules="passwordRules"
          label-placement="top"
          require-mark-placement="right-hanging"
        >
          <n-form-item :label="t('additional.current_password')" path="currentPassword">
            <n-input
              v-model:value="passwordForm.currentPassword"
              type="password"
              show-password-on="click"
              :placeholder="t('additional.enter_your_current_password')"
            />
          </n-form-item>
          <n-form-item :label="t('additional.new_password')" path="newPassword">
            <n-input
              v-model:value="passwordForm.newPassword"
              type="password"
              show-password-on="click"
              :placeholder="t('legacy.at_least_10_characters_9ef2b0f')"
            />
          </n-form-item>
          <n-form-item :label="t('additional.confirm_new_password')" path="confirmPassword">
            <n-input
              v-model:value="passwordForm.confirmPassword"
              type="password"
              show-password-on="click"
              :placeholder="t('additional.enter_your_new_password_again')"
            />
          </n-form-item>

          <div class="form-actions">
            <n-button :disabled="changingPassword" @click="resetPasswordForm">{{ t('additional.clear') }}</n-button>
            <n-button type="primary" :loading="changingPassword" @click="submitPasswordChange">
              {{ t('additional.change_password') }}
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
  name: [{ required: true, message: t('additional.enter_a_name_or_nickname'), trigger: ['input', 'blur'] }],
  email: [
    {
      validator: (_rule, value: string) => {
        if (!value) return true;
        return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value);
      },
      message: t('additional.enter_a_valid_email_address'),
      trigger: ['input', 'blur'],
    },
  ],
};

const passwordRules: FormRules = {
  currentPassword: [{ required: true, message: t('additional.enter_your_current_password'), trigger: ['input', 'blur'] }],
  newPassword: [
    { required: true, message: t('additional.enter_a_new_password'), trigger: ['input', 'blur'] },
    { min: 10, message: t('legacy.new_password_must_be_at_least_10_characters'), trigger: ['input', 'blur'] },
    {
      validator: (_rule, value: string) => value !== passwordForm.currentPassword,
      message: t('additional.the_new_password_must_differ_from_the_current_password'),
      trigger: ['input', 'blur'],
    },
  ],
  confirmPassword: [
    { required: true, message: t('additional.enter_your_new_password_again'), trigger: ['input', 'blur'] },
    {
      validator: (_rule, value: string) => value === passwordForm.newPassword,
      message: t('additional.the_new_passwords_do_not_match'),
      trigger: ['input', 'blur'],
    },
  ],
};

const profileDisplayName = computed(() =>
  profileForm.name.trim() ? profileForm.name.trim() : displayAdminName(authStore.profile, t('legacy.admin')),
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
    message.error(t('additional.failed_to_load_profile'));
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
    message.error(t('additional.avatars_must_be_jpg_png_or_webp'));
    input.value = '';
    return;
  }
  if (file.size > 2 * 1024 * 1024) {
    message.error(t('additional.avatar_file_must_not_exceed_2_mb'));
    input.value = '';
    return;
  }
  uploadingAvatar.value = true;
  try {
    const profile = await uploadCurrentAvatar(file);
    profileAvatarFailedUrl.value = '';
    applyProfile(profile);
    message.success(t('additional.avatar_updated'));
  } catch (error) {
    message.error(t('additional.failed_to_upload_avatar'));
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
    message.success(t('additional.profile_saved'));
  } catch (error) {
    message.error(t('additional.failed_to_save_profile'));
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
    message.success(t('additional.password_changed_please_sign_in_again'));
    authStore.clearSession();
    router.push('/login');
  } catch (error) {
    message.error(t('additional.failed_to_change_password_check_your_current_password'));
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
