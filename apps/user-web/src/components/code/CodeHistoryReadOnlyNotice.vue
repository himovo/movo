<script setup lang="ts">
import { computed } from 'vue'
import { useLocale } from '../../composables/i18n'

const props = defineProps<{
  executionLocation: 'desktop' | 'remote_sandbox'
  project?: { workspace_id: string; git_branch: string; worktree: boolean } | null
}>()

const { locale } = useLocale()
const title = computed(() => locale.value === 'zh' ? '项目会话历史（只读）' : 'Project task history (read only)')
const detail = computed(() => {
  if (props.executionLocation === 'remote_sandbox') {
    return locale.value === 'zh'
      ? '该会话绑定到企业远程沙箱；当前客户端没有可用执行面，但历史记录和审计信息仍可查看。'
      : 'This task is bound to an enterprise remote sandbox. No execution surface is available here, but history and audit remain readable.'
  }
  return locale.value === 'zh'
    ? '该会话绑定到创建它的 MOVO Desktop 与本地项目。请在绑定的桌面端继续执行；Web 不会访问本地文件或命令。'
    : 'This task is bound to its MOVO Desktop and local project. Continue on the bound desktop; Web never accesses local files or commands.'
})
</script>

<template>
  <div class="mx-auto w-full max-w-4xl px-4 pb-3 md:px-6" role="status">
    <div class="rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 shadow-sm">
      <div class="flex items-center gap-2 text-sm font-semibold text-slate-800">
        <svg aria-hidden="true" width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8">
          <rect x="3" y="5" width="18" height="14" rx="2"/><path d="M8 12h8M12 8v8"/>
        </svg>
        {{ title }}
      </div>
      <p class="mt-1 text-xs leading-5 text-slate-600">{{ detail }}</p>
      <p v-if="props.project?.git_branch" class="mt-2 truncate font-mono text-[11px] text-slate-500">
        {{ props.project.git_branch }}
      </p>
    </div>
  </div>
</template>
