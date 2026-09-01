<template>
  <div class="invite-page">
    <div class="invite-shell">
      <section class="invite-hero">
        <div class="hero-badge">{{ t('企业邀请') }}</div>
        <h1 class="hero-title">{{ t('加入 {org} 的 MOVO 工作空间', { org: orgName }) }}</h1>
        <p class="hero-desc">{{ t('完成账号激活后，即可登录 MOVO 前台系统开始使用。') }}</p>
        <div class="hero-meta">{{ t('邀请有效期至：{time}', { time: inviteDetail.expiresAt || '--' }) }}</div>
      </section>

      <n-card class="invite-card" :bordered="false">
        <template v-if="state === 'loading'">
          <div class="state-wrap"><n-spin size="large" /></div>
        </template>
        <template v-else-if="state === 'error'">
          <n-result status="error" :title="t('邀请链接不可用')" :description="errorMessage" />
        </template>
        <template v-else-if="state === 'success'">
          <n-result status="success" :title="t('加入成功')" :description="successDescription" />
          <div class="success-tip">{{ t('正在跳转到 MOVO 登录页…') }}</div>
        </template>
        <template v-else>
          <div class="form-title">{{ t('激活企业账号') }}</div>
          <n-form :model="form" label-placement="top">
            <n-grid :cols="2" :x-gap="12">
              <n-grid-item :span="2">
                <n-form-item :label="t('登录名')">
                  <n-input v-model:value="form.loginName" :placeholder="t('请输入登录名（登录时使用）')" />
                </n-form-item>
              </n-grid-item>
              <n-grid-item>
                <n-form-item :label="t('姓名')">
                  <n-input v-model:value="form.name" :placeholder="t('请输入姓名')" />
                </n-form-item>
              </n-grid-item>
              <n-grid-item>
                <n-form-item :label="t('手机号（可选）')">
                  <n-input v-model:value="form.mobile" :placeholder="t('用于后续通知')" />
                </n-form-item>
              </n-grid-item>
              <n-grid-item :span="2">
                <n-form-item :label="t('邮箱（可选）')">
                  <n-input v-model:value="form.email" :placeholder="t('用于后续找回密码（可选）')" />
                </n-form-item>
              </n-grid-item>
              <n-grid-item>
                <n-form-item :label="t('设置密码')">
                  <n-input v-model:value="form.password" type="password" show-password-on="click" :placeholder="t('至少 6 位')" />
                </n-form-item>
              </n-grid-item>
              <n-grid-item>
                <n-form-item :label="t('确认密码')">
                  <n-input v-model:value="form.confirmPassword" type="password" show-password-on="click" :placeholder="t('请再次输入密码')" />
                </n-form-item>
              </n-grid-item>
            </n-grid>
          </n-form>
          <p v-if="errorMessage" class="error-line">{{ errorMessage }}</p>
          <n-button type="primary" class="submit-btn" :loading="submitting" @click="submitAccept">{{ t('加入企业并激活') }}</n-button>
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
const orgName = computed(() => inviteDetail.orgName || t('企业组织'));
const successDescription = computed(() => t('账号 {username} 已激活，可前往 MOVO 登录。', { username: form.loginName || '' }));

function parseError(error: unknown) {
  if (axios.isAxiosError(error)) {
    return (error.response?.data as { detail?: string } | undefined)?.detail || error.message;
  }
  return t('请求失败');
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
    errorMessage.value = t('缺少邀请 token');
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
    errorMessage.value = t('请填写登录名');
    return;
  }
  if (!form.name.trim()) {
    errorMessage.value = t('请填写姓名');
    return;
  }
  if (form.password.length < 6) {
    errorMessage.value = t('密码至少 6 位');
    return;
  }
  if (form.password !== form.confirmPassword) {
    errorMessage.value = t('两次密码不一致');
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
