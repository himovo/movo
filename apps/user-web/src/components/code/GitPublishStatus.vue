<script setup lang="ts">
import { computed } from 'vue'
import CloudUploadOutline from '@vicons/ionicons5/es/CloudUploadOutline'
import type { DshGitCommitResult, DshGitPushResult, DshWorkspaceSummary } from '../../platform/types'

const props = defineProps<{
  commit?: DshGitCommitResult | null
  push?: DshGitPushResult | null
  summary?: DshWorkspaceSummary | null
  busy?: boolean
  error?: string
  locale?: 'zh' | 'en'
}>()
const emit = defineEmits<{ (event: 'push', expectedCommitHash: string): void }>()
const expectedHash = computed(() => props.commit?.commit_hash || props.summary?.head_commit || '')
const pushed = computed(() => props.commit?.push || props.push)
const unpublished = computed(() => Boolean(
  props.commit && !props.commit.push
  || (props.summary?.ahead || 0) > 0,
))
const remoteAvailable = computed(() => Boolean(props.summary?.remote_names.length))
</script>

<template>
  <div v-if="pushed" class="publish-state success">
    <span>{{ locale === 'en' ? 'Committed and pushed' : '已提交并推送' }} <code>{{ pushed.commit_hash.slice(0, 8) }}</code></span>
    <small>{{ pushed.upstream }}</small>
  </div>
  <div v-else-if="commit || (summary?.ahead || 0) > 0 || error" class="publish-state" :class="commit?.push_error || error ? 'warning' : 'success'">
    <div class="publish-copy">
      <span v-if="commit">{{ locale === 'en' ? 'Committed locally' : '已提交到本地' }} <code>{{ commit.short_hash }}</code></span>
      <span v-else>{{ locale === 'en' ? `${summary?.ahead} local commit(s) not pushed` : `有 ${summary?.ahead} 个本地提交尚未推送` }}</span>
      <small v-if="commit?.push_error || error">{{ commit?.push_error || error }}</small>
      <small v-else-if="!remoteAvailable">{{ locale === 'en' ? 'No Git remote is configured' : '当前仓库尚未配置远程地址' }}</small>
    </div>
    <button v-if="unpublished && remoteAvailable && expectedHash" type="button" :disabled="busy" @click="emit('push', expectedHash)"><CloudUploadOutline />{{ busy ? (locale === 'en' ? 'Pushing…' : '正在推送…') : (commit?.push_error || error ? (locale === 'en' ? 'Retry push' : '重新推送') : (locale === 'en' ? 'Push' : '推送')) }}</button>
  </div>
</template>

<style scoped>
.publish-state{display:flex;align-items:center;justify-content:space-between;gap:8px;border-top:1px solid #bbf7d0;background:#f0fdf4;padding:8px 10px;color:#166534;font-size:10px}.publish-state.warning{border-color:#fed7aa;background:#fff7ed;color:#9a3412}.publish-state>span,.publish-copy{min-width:0}.publish-state>span{display:flex;flex-direction:column;gap:2px}.publish-copy{display:flex;flex:1;flex-direction:column;gap:3px}.publish-state code{margin-left:3px;font-family:ui-monospace,SFMono-Regular,Menlo,monospace}.publish-state small{overflow:hidden;color:inherit;opacity:.82;text-overflow:ellipsis;white-space:nowrap}.publish-state button{display:flex;height:27px;flex:none;align-items:center;gap:4px;border:1px solid currentColor;border-radius:7px;background:#fff;padding:0 8px;color:inherit;font-size:10px;font-weight:650;cursor:pointer}.publish-state button:disabled{cursor:not-allowed;opacity:.55}.publish-state button svg{width:13px}
:global(html.theme-dark) .publish-state{border-color:#166534;background:#052e16;color:#bbf7d0}:global(html.theme-dark) .publish-state.warning{border-color:#9a3412;background:#431407;color:#fed7aa}:global(html.theme-dark) .publish-state button{background:#172033}
</style>
