<template>
  <div class="step-content">
    <div class="step-heading">
      <span class="step-kicker">{{ t('步骤 5 / 5') }}</span>
      <h2>{{ t('配置联网搜索') }}</h2>
      <p>{{ t('任选一个搜索服务即可启用网页搜索与多源研究；也可以跳过并稍后在管理后台配置。') }}</p>
    </div>

    <n-alert :type="model.enabled ? 'info' : 'warning'" :show-icon="true">
      {{ model.enabled
        ? t('API Key 将加密保存，连接测试成功后才能随初始化一并保存。')
        : t('暂不配置时，普通对话仍可使用，但网页搜索和多源研究不可用。') }}
    </n-alert>

    <div class="enable-row">
      <div>
        <strong>{{ t('现在配置联网搜索') }}</strong>
        <span>{{ t('推荐') }}</span>
      </div>
      <n-switch v-model:value="model.enabled" :aria-label="t('现在配置联网搜索')" />
    </div>

    <template v-if="model.enabled">
      <fieldset class="provider-fieldset" :disabled="providersLoading || testing">
        <legend>{{ t('选择一个搜索服务') }}</legend>
        <button
          v-for="provider in providers"
          :key="provider.id"
          type="button"
          class="provider-card"
          :class="{ selected: model.provider === provider.id }"
          :aria-pressed="model.provider === provider.id"
          @click="selectProvider(provider)"
        >
          <span class="provider-check" aria-hidden="true">
            <svg v-if="model.provider === provider.id" viewBox="0 0 24 24"><path d="m5 12 4 4L19 6" /></svg>
          </span>
          <span>
            <strong>{{ provider.name }}</strong>
            <small>{{ t(provider.description) }}</small>
          </span>
        </button>
      </fieldset>

      <SearchProviderGuide :provider="model.provider" />

      <n-form label-placement="top" class="search-form">
        <n-form-item label="API Key" required>
          <n-input v-model:value="model.apiKey" type="password" show-password-on="click" :disabled="testing" />
        </n-form-item>
        <n-form-item v-if="model.provider === 'baidu_qianfan'" label="Endpoint" required>
          <n-input v-model:value="model.endpoint" :disabled="testing" />
        </n-form-item>
        <n-grid v-if="model.provider === 'volc_ark'" :cols="2" :x-gap="14" responsive="screen">
          <n-grid-item span="2 m:1">
            <n-form-item label="Base URL" required><n-input v-model:value="model.baseUrl" :disabled="testing" /></n-form-item>
          </n-grid-item>
          <n-grid-item span="2 m:1">
            <n-form-item label="Bot Model" required><n-input v-model:value="model.model" placeholder="bot-..." :disabled="testing" /></n-form-item>
          </n-grid-item>
        </n-grid>
        <n-form-item :label="t('测试查询')">
          <n-input v-model:value="model.query" :disabled="testing" />
        </n-form-item>
      </n-form>

      <div class="test-row">
        <n-button size="large" :loading="testing" :disabled="submitting" @click="$emit('test')">
          {{ t('测试搜索连接') }}
        </n-button>
        <span v-if="testMessage" class="test-message" :class="testState" role="status">{{ testMessage }}</span>
      </div>
    </template>

    <div class="actions">
      <n-button size="large" :disabled="submitting || testing" @click="$emit('back')">{{ t('上一步') }}</n-button>
      <n-button size="large" type="primary" :loading="submitting" :disabled="testing" @click="$emit('submit')">
        {{ model.enabled ? t('保存并完成初始化') : t('跳过并完成初始化') }}
      </n-button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import type { SetupSearchProvider } from '@/api/setup';
import { t } from '@/composables/i18n';
import SearchProviderGuide from '@/components/search-provider/SearchProviderGuide.vue';
import type { SearchTestState, SetupSearchForm } from './types';

const props = defineProps<{
  providers: SetupSearchProvider[];
  providersLoading: boolean;
  testState: SearchTestState;
  testMessage: string;
  submitting: boolean;
}>();
const model = defineModel<SetupSearchForm>({ required: true });
defineEmits<{ back: []; test: []; submit: [] }>();

const testing = computed(() => props.testState === 'testing');

function selectProvider(provider: SetupSearchProvider) {
  model.value.provider = provider.id;
  model.value.endpoint = provider.defaultEndpoint;
  model.value.baseUrl = provider.defaultBaseUrl;
  model.value.model = '';
  model.value.apiKey = '';
}
</script>

<style scoped>
.step-content { display: grid; gap: 16px; }
.step-kicker { color: #3568e8; font-size: 12px; font-weight: 700; letter-spacing: .08em; text-transform: uppercase; }
.step-heading h2 { margin: 6px 0; color: #10204a; font-size: 24px; }
.step-heading p { margin: 0; color: #64748b; line-height: 1.6; }
.enable-row { display: flex; min-height: 52px; align-items: center; justify-content: space-between; padding: 0 14px; border: 1px solid #e0e7f1; border-radius: 12px; }
.enable-row div { display: flex; align-items: center; gap: 8px; }
.enable-row span { padding: 2px 7px; border-radius: 999px; background: #e8f0ff; color: #2859cf; font-size: 11px; font-weight: 700; }
.provider-fieldset { display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; margin: 0; padding: 0; border: 0; }
.provider-fieldset legend { grid-column: 1 / -1; margin-bottom: 8px; color: #334155; font-size: 13px; font-weight: 700; }
.provider-card { display: grid; min-height: 88px; grid-template-columns: 20px 1fr; gap: 9px; padding: 13px; border: 1px solid #dce4f1; border-radius: 13px; background: #fff; color: #17233d; text-align: left; cursor: pointer; transition: border-color .2s ease, box-shadow .2s ease; }
.provider-card:hover { border-color: #9bb5f4; }
.provider-card:focus-visible { outline: 3px solid rgba(53, 104, 232, .24); outline-offset: 2px; }
.provider-card.selected { border-color: #3568e8; box-shadow: 0 6px 18px rgba(53, 104, 232, .1); }
.provider-card strong, .provider-card small { display: block; }
.provider-card small { margin-top: 5px; color: #64748b; font-size: 11px; line-height: 1.45; }
.provider-check { display: grid; width: 18px; height: 18px; place-items: center; border: 1px solid #cbd5e1; border-radius: 50%; color: #fff; }
.selected .provider-check { border-color: #3568e8; background: #3568e8; }
.provider-check svg { width: 12px; fill: none; stroke: currentColor; stroke-linecap: round; stroke-linejoin: round; stroke-width: 2.5; }
.search-form { padding: 16px 16px 0; border: 1px solid #e3eaf4; border-radius: 14px; background: #fafcff; }
.test-row { display: flex; min-height: 44px; align-items: center; gap: 12px; }
.test-message { color: #64748b; font-size: 13px; }
.test-message.success { color: #168461; }
.test-message.failed { color: #c2413d; }
.actions { display: grid; grid-template-columns: auto minmax(220px, 1fr); gap: 10px; }
@media (max-width: 680px) { .provider-fieldset { grid-template-columns: 1fr; } .actions { grid-template-columns: 1fr; } }
@media (prefers-reduced-motion: reduce) { .provider-card { transition: none; } }
</style>
