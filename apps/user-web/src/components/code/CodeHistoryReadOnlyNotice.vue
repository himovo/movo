<script setup lang="ts">
import { computed } from 'vue'
import { t } from '../../composables/i18n'

const props = defineProps<{
  executionLocation: 'desktop' | 'remote_sandbox'
  project?: { workspace_id: string; git_branch: string; worktree: boolean } | null
  localFolderUnavailable?: boolean
  canStartLocal?: boolean
}>()
const emit = defineEmits<{ (e: 'start-local'): void }>()

const title = computed(() => t('code.history_read_only.title'))
const detail = computed(() => {
  if (props.executionLocation === 'remote_sandbox') {
    return t('code.history_read_only.remote_detail')
  }
  if (props.localFolderUnavailable) {
    return t('code.history_read_only.missing_folder_detail')
  }
  return t('code.history_read_only.local_detail')
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
      <button v-if="props.canStartLocal && props.localFolderUnavailable" type="button" class="mt-2 rounded-lg border border-slate-300 px-3 py-1.5 text-xs font-medium text-slate-700 hover:bg-slate-100" @click="emit('start-local')">
        {{ t('code.history_read_only.start_local') }}
      </button>
    </div>
  </div>
</template>
