<script setup lang="ts">
import WorkspaceContextPicker from './WorkspaceContextPicker.vue'
import BranchContextPicker from './BranchContextPicker.vue'
import type { DshCodeSession, DshWorkspace } from '../../platform/types'

defineProps<{
  workspace: DshWorkspace | null
  session?: DshCodeSession | null
  busy?: boolean
  worktree?: boolean
  sourceRef?: string
  modelId?: string
  locale?: 'zh' | 'en'
}>()

const emit = defineEmits<{
  (event: 'choose'): void
  (event: 'clear'): void
  (event: 'worktree', enabled: boolean): void
  (event: 'source-ref', fullRef: string): void
  (event: 'branch-updated', branch: string): void
}>()
</script>

<template>
  <div class="code-draft-context" :class="{ 'has-workspace': workspace }">
    <WorkspaceContextPicker
      class="workspace-control"
      :workspace="workspace"
      :locked="Boolean(session)"
      :busy="busy"
      :worktree="worktree"
      :locale="locale"
      @choose="emit('choose')"
      @clear="emit('clear')"
      @worktree="(enabled) => emit('worktree', enabled)"
    />
    <BranchContextPicker
      v-if="workspace"
      class="branch-control"
      :workspace="workspace"
      :locked="Boolean(session)"
      :busy="busy"
      :worktree="worktree"
      :detached="session?.detached_head"
      :branch="session?.git_branch || workspace.git_branch || ''"
      :source-ref="sourceRef"
      :model-id="modelId"
      :locale="locale"
      @source-ref="(fullRef) => emit('source-ref', fullRef)"
      @branch-updated="(branch) => emit('branch-updated', branch)"
    />
  </div>
</template>

<style scoped>
.code-draft-context{display:flex;width:100%;min-width:0;min-height:40px;align-items:stretch;justify-content:flex-start;border:1px solid #e5e7eb;border-bottom:0;border-radius:14px 14px 0 0;background:#f6f7f8}.workspace-control{min-width:0;flex:0 1 auto}.branch-control{flex:none}.code-draft-context :deep(.workspace-picker:not(.compact)){width:auto;margin-bottom:0}.code-draft-context :deep(.workspace-picker:not(.compact) .composer-context){border:0;border-radius:0;background:transparent}.code-draft-context :deep(.branch-trigger){border:0;border-radius:8px;background:transparent}.code-draft-context :deep(.workspace-picker:not(.compact) .workspace-menu){left:0}:global(html.theme-dark) .code-draft-context{border-color:#334155;background:#111827}
@media(max-width:640px){.branch-control{max-width:46%}.code-draft-context :deep(.branch-trigger span){max-width:110px}}
</style>
