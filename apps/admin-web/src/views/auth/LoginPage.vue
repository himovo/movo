<template>
  <div class="login-page">
    <div class="login-panel">
      <div class="login-copy">
        <img class="login-logo" :src="movoLogo" alt="MOVO" />
        <h1>{{ t('MOVO 智能体控制台') }}</h1>
        <p>
          {{ t('管理组织、模型与流程配置，确保平台运行稳定、可控、可追踪。') }}
        </p>
      </div>

      <n-card class="login-card" :bordered="false">
        <n-form label-placement="top" @submit.prevent="handleLogin">
          <n-form-item :label="t('账号')">
            <n-input v-model:value="form.username" :placeholder="t('请输入账号')" @keydown.enter.prevent="handleLogin" />
          </n-form-item>
          <n-form-item :label="t('密码')">
            <n-input
              v-model:value="form.password"
              type="password"
              show-password-on="click"
              :placeholder="t('输入密码')"
              @keydown.enter.prevent="handleLogin"
            />
          </n-form-item>
          <n-space vertical :size="14">
            <n-button block type="primary" size="large" :loading="loading" attr-type="submit">
              {{ t('登录后台') }}
            </n-button>
          </n-space>
        </n-form>
      </n-card>
    </div>

    <n-modal v-model:show="tenantModalVisible" preset="card" :title="t('请选择要进入的企业')" style="width: 520px" :mask-closable="false">
      <div class="tenant-list">
        <button
          v-for="candidate in tenantCandidates"
          :key="candidate.mainId"
          class="tenant-option"
          type="button"
          :disabled="selectingTenant"
          @click="handleTenantSelect(candidate)"
        >
          <span class="tenant-copy">
            <strong>{{ candidate.orgName || t('未命名企业') }}</strong>
            <small>{{ candidate.roleName || t('组织管理员') }}</small>
          </span>
          <span class="tenant-arrow" aria-hidden="true">›</span>
        </button>
      </div>
      <div v-if="!tenantCandidates.length" class="tenant-empty">{{ t('暂无可选择企业，请重新登录。') }}</div>
      <template #footer>
        <n-space justify="end">
          <n-button :disabled="selectingTenant" @click="resetTenantSelection">{{ t('重新登录') }}</n-button>
        </n-space>
      </template>
    </n-modal>
  </div>
</template>

<script setup lang="ts">
import { reactive, ref } from 'vue';
import { useRouter } from 'vue-router';
import { useMessage } from 'naive-ui';
import { login, selectTenantLogin, type TenantCandidate } from '@/api/auth';
import { useAuthStore } from '@/stores/auth';
import { t } from '@/composables/i18n';
import movoLogo from '@/assets/images/movo-logo.png';

const router = useRouter();
const message = useMessage();
const authStore = useAuthStore();
const loading = ref(false);
const tenantModalVisible = ref(false);
const selectingTenant = ref(false);
const challengeToken = ref('');
const tenantCandidates = ref<TenantCandidate[]>([]);
const form = reactive({
  username: '',
  password: '',
});

async function handleLogin() {
  loading.value = true;
  try {
    const result = await login(form);
    if ('requiresTenantSelection' in result && result.requiresTenantSelection) {
      challengeToken.value = result.challengeToken;
      tenantCandidates.value = result.candidates || [];
      tenantModalVisible.value = true;
      return;
    }
    authStore.login(result);
    message.success(t('登录成功'));
    router.push('/dashboard');
  } catch (error) {
    console.error(error);
    message.error(t('登录失败，请检查账号密码或 admin-api 是否已启动'));
  } finally {
    loading.value = false;
  }
}

async function handleTenantSelect(candidate: TenantCandidate) {
  if (!challengeToken.value) return;
  selectingTenant.value = true;
  try {
    const result = await selectTenantLogin({
      challengeToken: challengeToken.value,
      mainId: candidate.mainId,
    });
    authStore.login(result);
    message.success(t('已进入 {org}', { org: candidate.orgName || t('企业') }));
    router.push('/dashboard');
  } catch (error) {
    console.error(error);
    message.error(t('进入企业失败，请重新登录'));
    resetTenantSelection();
  } finally {
    selectingTenant.value = false;
  }
}

async function resetTenantSelection() {
  tenantModalVisible.value = false;
  challengeToken.value = '';
  tenantCandidates.value = [];
}
</script>

<style scoped>
.login-page {
  min-height: 100vh;
  display: grid;
  place-items: center;
  padding: 32px;
}

.login-panel {
  display: grid;
  grid-template-columns: 1.1fr 420px;
  gap: 28px;
  width: min(1100px, 100%);
}

.login-copy {
  padding: 38px;
  border-radius: 28px;
  background:
    radial-gradient(circle at top left, rgba(112, 155, 255, 0.34), transparent 34%),
    linear-gradient(135deg, #18306f, #2449a9 48%, #0d1d4f);
  color: #effbf8;
  box-shadow: 0 30px 80px rgba(25, 49, 116, 0.24);
}

.login-logo {
  display: block;
  width: 112px;
  height: 90px;
  object-fit: contain;
  filter: drop-shadow(0 8px 18px rgba(0, 0, 0, 0.16));
}

.login-copy h1 {
  margin: 16px 0 14px;
  font-size: 42px;
  line-height: 1.08;
}

.login-copy p {
  margin: 0;
  font-size: 16px;
  line-height: 1.7;
  color: rgba(239, 251, 248, 0.82);
}

.login-card {
  border-radius: 28px;
  box-shadow: 0 30px 80px rgba(23, 46, 43, 0.12);
}

.tenant-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.tenant-option {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 14px;
  width: 100%;
  padding: 14px 16px;
  border: 1px solid #dbe5f5;
  border-radius: 8px;
  background: #fff;
  cursor: pointer;
  text-align: left;
  transition: border-color 0.2s ease, background-color 0.2s ease, box-shadow 0.2s ease;
}

.tenant-option:hover:not(:disabled) {
  border-color: #9db8f8;
  background: #f8fbff;
  box-shadow: 0 8px 20px rgba(37, 99, 235, 0.08);
}

.tenant-option:disabled {
  cursor: not-allowed;
  opacity: 0.62;
}

.tenant-copy {
  min-width: 0;
}

.tenant-copy strong,
.tenant-copy small {
  display: block;
}

.tenant-copy strong {
  color: #12234b;
  font-size: 15px;
  font-weight: 800;
}

.tenant-copy small {
  margin-top: 4px;
  color: #64748b;
  font-size: 13px;
}

.tenant-arrow {
  color: #94a3b8;
  font-size: 22px;
}

.tenant-empty {
  padding: 24px 0;
  color: #64748b;
  text-align: center;
}

@media (max-width: 980px) {
  .login-panel {
    grid-template-columns: 1fr;
  }

  .login-copy h1 {
    font-size: 34px;
  }
}
</style>
