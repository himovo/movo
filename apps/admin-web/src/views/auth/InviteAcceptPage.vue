<template>
  <div class="invite-page">
    <div class="invite-shell">
      <section class="invite-hero">
        <div class="hero-badge">{{ t('legacy.organization_invitation') }}</div>
        <h1 class="hero-title">{{ t('legacy.join_s_movo_workspace', { org: orgName }) }}</h1>
        <p class="hero-desc">{{ t('legacy.activate_your_account_to_sign_in_and_start_using') }}</p>
        <div class="hero-meta">{{ t('legacy.invitation_valid_until', { time: inviteDetail.expiresAt || '--' }) }}</div>
      </section>

      <n-card class="invite-card" :bordered="false">
        <template v-if="state === 'loading'">
          <div class="state-wrap"><n-spin size="large" /></div>
        </template>
        <template v-else-if="state === 'error'">
          <n-result status="error" :title="t('legacy.invitation_link_is_invalid')" :description="errorMessage" />
        </template>
        <template v-else-if="state === 'success'">
          <n-result status="success" :title="t('legacy.joined_successfully')" :description="successDescription" />
          <div class="success-tip">{{ t('legacy.redirecting_to_movo_sign_in_page') }}</div>
        </template>
        <template v-else>
          <div class="form-title">{{ t('legacy.activate_organization_account') }}</div>
          <n-form :model="form" label-placement="top">
            <n-grid :cols="2" :x-gap="12">
              <n-grid-item :span="2">
                <n-form-item :label="t('legacy.login_name')">
                  <n-input v-model:value="form.loginName" :placeholder="t('legacy.please_enter_login_name_for_sign_in')" />
                </n-form-item>
              </n-grid-item>
              <n-grid-item>
                <n-form-item :label="t('legacy.name')">
                  <n-input v-model:value="form.name" :placeholder="t('legacy.please_enter_your_name')" />
                </n-form-item>
              </n-grid-item>
              <n-grid-item>
                <n-form-item :label="t('legacy.mobile_optional')">
                  <n-input v-model:value="form.mobile" :placeholder="t('legacy.used_for_subsequent_notifications')" />
                </n-form-item>
              </n-grid-item>
              <n-grid-item :span="2">
                <n-form-item :label="t('legacy.email_optional')">
                  <n-input v-model:value="form.email" :placeholder="t('legacy.used_for_password_recovery_optional')" />
                </n-form-item>
              </n-grid-item>
              <n-grid-item>
                <n-form-item :label="t('legacy.set_password')">
                  <n-input v-model:value="form.password" type="password" show-password-on="click" :placeholder="t('legacy.at_least_10_characters')" />
                </n-form-item>
              </n-grid-item>
              <n-grid-item>
                <n-form-item :label="t('legacy.confirm_password')">
                  <n-input v-model:value="form.confirmPassword" type="password" show-password-on="click" :placeholder="t('legacy.please_enter_password_again')" />
                </n-form-item>
              </n-grid-item>
            </n-grid>
          </n-form>
          <p v-if="errorMessage" class="error-line">{{ errorMessage }}</p>
          <n-button type="primary" class="submit-btn" :loading="submitting" @click="submitAccept">{{ t('legacy.join_activate') }}</n-button>
        </template>
      </n-card>
    </div>

    <footer class="invite-brand-footer" aria-label="MOVO Brand">
      <img class="invite-brand-logo" :src="movoLogo" alt="MOVO" />
      <span class="brand-text">Powered by MOVO</span>
    </footer>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue';
import { useRoute } from 'vue-router';
import axios from 'axios';
import { acceptInviteLink, fetchInviteLinkDetail, type InviteLinkDetail } from '@/api/directory';
import { t } from '@/composables/i18n';
import movoLogo from '@/assets/images/movo-logo.png';

const route = useRoute();
const state = ref<'loading' | 'ready' | 'success' | 'error'>('loading');
const submitting = ref(false);
const errorMessage = ref('');
const inviteDetail = reactive<InviteLinkDetail>({
  purpose: 'register',
  expiresAt: '',
  orgName: '',
  user: {
    name: '',
    mobile: '',
    email: '',
    loginName: '',
  },
});

const form = reactive({
  name: '',
  mobile: '',
  email: '',
  loginName: '',
  password: '',
  confirmPassword: '',
});

const token = computed(() => String(route.query.token || ''));
const orgName = computed(() => inviteDetail.orgName || t('legacy.organization_6ea45e8'));
const successDescription = computed(() => t('legacy.account_has_been_activated_you_can_now_sign_in', { username: form.loginName || '' }));

function parseError(error: unknown) {
  if (axios.isAxiosError(error)) {
    return (error.response?.data as { detail?: string } | undefined)?.detail || error.message;
  }
  return t('legacy.request_failed');
}

function redirectToFrontendLogin() {
  const query = new URLSearchParams({
    invite: '1',
    username: form.loginName.trim(),
  });
  window.setTimeout(() => {
    window.location.href = `${window.location.origin}/?${query.toString()}`;
  }, 1200);
}

async function loadInviteDetail() {
  if (!token.value) {
    state.value = 'error';
    errorMessage.value = t('legacy.missing_invitation_token');
    return;
  }
  state.value = 'loading';
  try {
    const detail = await fetchInviteLinkDetail(token.value);
    inviteDetail.purpose = detail.purpose;
    inviteDetail.expiresAt = detail.expiresAt;
    inviteDetail.orgName = detail.orgName || '';
    inviteDetail.user = detail.user;
    if (detail.user?.loginName) {
      form.loginName = detail.user.loginName;
    }
    state.value = 'ready';
  } catch (error) {
    state.value = 'error';
    errorMessage.value = parseError(error);
  }
}

async function submitAccept() {
  errorMessage.value = '';
  if (!form.loginName.trim()) {
    errorMessage.value = t('legacy.please_enter_login_name');
    return;
  }
  if (!form.name.trim()) {
    errorMessage.value = t('legacy.please_enter_name');
    return;
  }
  if (form.password.length < 10) {
    errorMessage.value = t('legacy.password_must_be_at_least_10_characters');
    return;
  }
  if (form.password !== form.confirmPassword) {
    errorMessage.value = t('legacy.passwords_do_not_match');
    return;
  }
  submitting.value = true;
  try {
    await acceptInviteLink(token.value, {
      name: form.name.trim(),
      mobile: form.mobile.trim(),
      email: form.email.trim(),
      loginName: form.loginName.trim(),
      password: form.password,
    });
    state.value = 'success';
    redirectToFrontendLogin();
  } catch (error) {
    errorMessage.value = parseError(error);
  } finally {
    submitting.value = false;
  }
}

onMounted(async () => {
  await loadInviteDetail();
});
</script>

<style scoped>
.invite-page {
  min-height: 100vh;
  background: linear-gradient(160deg, #edf2ff 0%, #f5f8ff 48%, #eef8ff 100%);
  padding: 44px 24px 64px;
}

.invite-shell {
  margin: 0 auto;
  width: min(960px, 100%);
  display: grid;
  grid-template-columns: 1.05fr 1fr;
  gap: 20px;
}

.invite-hero {
  border: 1px solid #dbe5ff;
  border-radius: 18px;
  background: linear-gradient(145deg, #366aff 0%, #5d86ff 100%);
  color: #fff;
  padding: 28px;
  min-height: 360px;
}

.hero-badge {
  display: inline-flex;
  align-items: center;
  border: 1px solid rgba(255, 255, 255, 0.35);
  border-radius: 999px;
  padding: 4px 10px;
  font-size: 12px;
}

.hero-title {
  margin: 14px 0 10px;
  font-size: 30px;
  line-height: 1.26;
  font-weight: 700;
}

.hero-desc {
  margin: 0;
  font-size: 14px;
  line-height: 1.75;
  color: rgba(255, 255, 255, 0.92);
}

.hero-meta {
  margin-top: 22px;
  font-size: 13px;
  color: rgba(255, 255, 255, 0.88);
}

.invite-card {
  border-radius: 18px;
}

.state-wrap {
  min-height: 300px;
  display: grid;
  place-items: center;
}

.form-title {
  margin-bottom: 8px;
  font-size: 18px;
  font-weight: 700;
  color: #1f2937;
}

.error-line {
  margin: 8px 0 12px;
  border-radius: 10px;
  background: #fef2f2;
  color: #dc2626;
  padding: 8px 10px;
  font-size: 13px;
}

.submit-btn {
  width: 100%;
  height: 42px;
  border-radius: 10px;
}

.success-tip {
  margin-top: 10px;
  text-align: center;
  font-size: 13px;
  color: #6b7280;
}

.invite-brand-footer {
  position: fixed;
  left: 0;
  right: 0;
  bottom: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  color: #7a8599;
  font-size: 12px;
  user-select: none;
}

.invite-brand-logo {
  display: block;
  width: 34px;
  height: 28px;
  object-fit: contain;
}

@media (max-width: 860px) {
  .invite-shell {
    grid-template-columns: 1fr;
  }

  .invite-hero {
    min-height: 220px;
  }

  .hero-title {
    font-size: 24px;
  }
}
</style>
