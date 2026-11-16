<script setup lang="ts">
import { computed } from 'vue'
import { t } from '../../composables/i18n'
import type { QuotaNotice } from '../../composables/useQuotaNotice'

const props = defineProps<{ kind: Exclude<QuotaNotice, null>; interrupted?: boolean; running?: boolean }>()
const title = computed(() => t(props.kind === 'enterprise' ? 'chat.quota.enterprise_title' : 'chat.quota.personal_title'))
const detail = computed(() => t(props.kind === 'enterprise'
  ? (props.interrupted ? 'chat.quota.enterprise_interrupted' : props.running ? 'chat.quota.enterprise_running' : 'chat.quota.enterprise_action')
  : (props.interrupted ? 'chat.quota.personal_interrupted' : props.running ? 'chat.quota.personal_running' : 'chat.quota.personal_action')))
</script>

<template>
  <div class="quota-notice" role="alert">
    <span class="quota-notice__icon" aria-hidden="true">!</span>
    <div>
      <strong>{{ title }}</strong>
      <p>{{ detail }}</p>
    </div>
  </div>
</template>

<style scoped>
.quota-notice { display:flex; align-items:flex-start; gap:12px; margin:0 auto 10px; width:min(100%, 880px); padding:13px 16px; border:1px solid #f3d18b; border-radius:14px; background:#fffbeb; color:#78350f; box-shadow:0 3px 14px #78350f0b; }
.quota-notice__icon { display:grid; place-items:center; flex:none; width:20px; height:20px; border-radius:50%; background:#f59e0b; color:white; font-size:13px; font-weight:700; }
strong { display:block; font-size:13px; line-height:20px; }
p { margin:2px 0 0; color:#92400e; font-size:12px; line-height:18px; }
</style>
