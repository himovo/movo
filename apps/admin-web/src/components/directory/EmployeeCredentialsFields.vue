<script setup lang="ts">
import { computed } from 'vue';
import { t } from '@/composables/i18n';

const props = defineProps<{
  mode: 'create' | 'edit';
  source: 'local' | 'dingtalk' | 'wecom' | 'feishu';
}>();

const loginName = defineModel<string>('loginName', { required: true });
const password = defineModel<string>('password', { required: true });
const isLocal = computed(() => props.source === 'local');
const passwordLabel = computed(() => (props.mode === 'create' ? t('初始密码') : t('重置密码（可选）')));
const passwordPlaceholder = computed(() => (props.mode === 'create' ? t('至少 6 位') : t('不填则保留当前密码')));
</script>

<template>
  <section class="credentials-section" aria-labelledby="employee-credentials-heading">
    <div class="credentials-heading">
      <div>
        <h3 id="employee-credentials-heading">{{ t('登录凭据') }}</h3>
        <p v-if="isLocal">
          {{ mode === 'create' ? t('为员工创建可直接登录用户端的账号密码。') : t('登录名可修改；密码留空表示不重置。') }}
        </p>
        <p v-else>{{ t('外部同步用户由身份源负责登录，不能在此设置本地密码。') }}</p>
      </div>
      <n-tag size="small" :type="isLocal ? 'success' : 'default'">
        {{ isLocal ? t('本地账号') : t('外部身份') }}
      </n-tag>
    </div>

    <n-grid v-if="isLocal" :cols="2" :x-gap="12">
      <n-grid-item>
        <n-form-item :label="t('登录名')" required>
          <n-input
            v-model:value="loginName"
            autocomplete="off"
            :placeholder="t('请输入登录名（登录时使用）')"
          />
        </n-form-item>
      </n-grid-item>
      <n-grid-item>
        <n-form-item :label="passwordLabel" :required="mode === 'create'">
          <n-input
            v-model:value="password"
            type="password"
            show-password-on="click"
            autocomplete="new-password"
            :placeholder="passwordPlaceholder"
          />
        </n-form-item>
      </n-grid-item>
    </n-grid>
  </section>
</template>

<style scoped>
.credentials-section {
  margin: 4px 0 18px;
  padding: 16px 16px 2px;
  border: 1px solid #dbe4f0;
  border-radius: 12px;
  background: #f8fafc;
}

.credentials-heading {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 14px;
}

.credentials-heading h3 {
  margin: 0;
  color: #172033;
  font-size: 15px;
  line-height: 22px;
}

.credentials-heading p {
  margin: 3px 0 0;
  color: #64748b;
  font-size: 12px;
  line-height: 18px;
}
</style>
