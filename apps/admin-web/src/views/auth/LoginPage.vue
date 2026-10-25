<template>
  <div class="login-page">
    <div class="login-panel">
      <div class="login-copy">
        <img class="login-logo" :src="movoLogo" alt="MOVO" />
        <h1>{{ t('legacy.movo_agent_console') }}</h1>
        <p>
          {{ t('legacy.manage_organizations_models_and_process_configurations_to_ensure_stable') }}
        </p>
      </div>

      <n-card class="login-card" :bordered="false">
        <n-form label-placement="top" @submit.prevent="handleLogin">
          <n-form-item :label="t('legacy.username_email')">
            <n-input v-model:value="form.username" :placeholder="t('legacy.please_enter_your_username')" @keydown.enter.prevent="handleLogin" />
          </n-form-item>
          <n-form-item :label="t('legacy.password')">
            <n-input
              v-model:value="form.password"
              type="password"
              show-password-on="click"
              :placeholder="t('legacy.enter_password')"
              @keydown.enter.prevent="handleLogin"
            />
          </n-form-item>
          <n-space vertical :size="14">
            <n-button block type="primary" size="large" :loading="loading" attr-type="submit">
              {{ t('legacy.sign_in_3481b81') }}
            </n-button>
          </n-space>
        </n-form>
      </n-card>
    </div>

    <n-modal v-model:show="tenantModalVisible" preset="card" :title="t('legacy.please_select_an_organization_to_enter')" style="width: 520px" :mask-closable="false">
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
            <strong>{{ candidate.orgName || t('legacy.unnamed_organization') }}</strong>
            <small>{{ candidate.roleName || t('legacy.organization_administrator') }}</small>
          </span>
          <span class="tenant-arrow" aria-hidden="true">›</span>
        </button>
      </div>
      <div v-if="!tenantCandidates.length" class="tenant-empty">{{ t('legacy.no_organizations_available_please_sign_in_again') }}</div>
      <template #footer>
        <n-space justify="end">
          <n-button :disabled="selectingTenant" @click="resetTenantSelection">{{ t('legacy.sign_in_again') }}</n-button>
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
    message.success(t('legacy.logged_in_successfully'));
    router.push('/dashboard');
  } catch (error) {
    console.error(error);
    message.error(t('legacy.login_failed_please_check_username_password_or_if_the'));
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
    message.success(t('legacy.entered', { org: candidate.orgName || t('legacy.organization') }));
    router.push('/dashboard');
  } catch (error) {
    console.error(error);
    message.error(t('legacy.failed_to_enter_organization_please_sign_in_again'));
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
