<template>
  <aside v-if="guide" class="provider-guide">
    <div class="guide-heading">
      <div>
        <strong>{{ t('如何获取 API Key') }}</strong>
        <span>{{ t('仅需配置任意一个搜索服务') }}</span>
      </div>
      <a :href="guide.url" target="_blank" rel="noopener noreferrer">
        {{ t('打开官方申请页面') }}
        <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M14 5h5v5M10 14 19 5M19 14v5H5V5h5" /></svg>
      </a>
    </div>
    <ol>
      <li v-for="step in guide.steps" :key="step">{{ t(step) }}</li>
    </ol>
    <p v-if="guide.note">{{ t(guide.note) }}</p>
  </aside>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import { t } from '@/composables/i18n';
import { isSearchProviderId, searchProviderGuides } from './providerGuides';

const props = defineProps<{ provider: string }>();
const guide = computed(() => isSearchProviderId(props.provider) ? searchProviderGuides[props.provider] : null);
</script>

<style scoped>
.provider-guide { padding: 14px 16px; border: 1px solid #dbe6f7; border-radius: 13px; background: #f8fbff; color: #475569; }
.guide-heading { display: flex; align-items: flex-start; justify-content: space-between; gap: 16px; }
.guide-heading div { display: grid; gap: 3px; }
.guide-heading strong { color: #1e293b; font-size: 13px; }
.guide-heading span { font-size: 12px; }
.guide-heading a { display: inline-flex; min-height: 44px; align-items: center; gap: 5px; color: #2457d6; font-size: 13px; font-weight: 600; text-decoration: none; }
.guide-heading a:hover { text-decoration: underline; }
.guide-heading a:focus-visible { border-radius: 5px; outline: 3px solid rgba(37, 87, 214, .22); outline-offset: 2px; }
.guide-heading svg { width: 15px; fill: none; stroke: currentColor; stroke-linecap: round; stroke-linejoin: round; stroke-width: 2; }
ol { margin: 9px 0 0; padding-left: 20px; font-size: 12px; line-height: 1.75; }
p { margin: 8px 0 0; color: #8a5a12; font-size: 12px; line-height: 1.55; }
@media (max-width: 600px) { .guide-heading { display: grid; gap: 5px; } }
</style>
