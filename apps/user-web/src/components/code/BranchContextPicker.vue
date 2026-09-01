<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import GitBranchOutline from '@vicons/ionicons5/es/GitBranchOutline'
import ChevronDownOutline from '@vicons/ionicons5/es/ChevronDownOutline'
import GitBranchSelector from './GitBranchSelector.vue'
import type { DshWorkspace } from '../../platform/types'

const props = withDefaults(defineProps<{
  workspace: DshWorkspace
  locked?: boolean
  busy?: boolean
  worktree?: boolean
  detached?: boolean
  compact?: boolean
  branch?: string
  sourceRef?: string
  modelId?: string
  locale?: 'zh' | 'en'
}>(), { branch: '', sourceRef: '', locale: 'zh' })

const emit = defineEmits<{
  (event: 'source-ref', fullRef: string): void
  (event: 'branch-updated', branch: string): void
}>()

const root = ref<HTMLElement | null>(null)
const open = ref(false)
const sourceLabel = computed(() => (props.sourceRef || 'HEAD')
  .replace(/^refs\/heads\//, '')
  .replace(/^refs\/remotes\//, ''))
const currentLabel = computed(() => props.branch || props.workspace.git_branch || '')
const label = computed(() => {
  if (props.worktree) {
    if (props.locked && props.detached && !currentLabel.value) {
      return props.locale === 'en' ? `Based on ${sourceLabel.value} · no branch` : `基于 ${sourceLabel.value} · 未建分支`
    }
    if (props.locked && currentLabel.value) return currentLabel.value
    return props.locale === 'en' ? `Start: ${sourceLabel.value}` : `起始：${sourceLabel.value}`
  }
  return currentLabel.value || (props.locale === 'en' ? 'Branch' : '分支')
})
const title = computed(() => props.locked
  ? (props.locale === 'en' ? 'The branch context is fixed after this task starts.' : '任务开始后，分支上下文保持固定。')
  : (props.worktree
    ? (props.locale === 'en' ? 'Choose the Worktree starting branch' : '选择 Worktree 的起始分支')
    : (props.locale === 'en' ? 'Switch or create a local branch' : '切换或创建本地分支')))

function closeOnOutside(event: PointerEvent) {
  const target = event.target as Node | null
  if (open.value && target && !root.value?.contains(target)) open.value = false
}
function closeOnEscape(event: KeyboardEvent) { if (event.key === 'Escape') open.value = false }

onMounted(() => {
  document.addEventListener('pointerdown', closeOnOutside)
  document.addEventListener('keydown', closeOnEscape)
})
onBeforeUnmount(() => {
  document.removeEventListener('pointerdown', closeOnOutside)
  document.removeEventListener('keydown', closeOnEscape)
})
</script>

<template>
  <div ref="root" class="branch-context" :class="{ compact }">
    <button
      type="button"
      class="branch-trigger"
      :disabled="busy"
      :aria-expanded="open"
      :title="title"
      @click="open = !open"
    >
      <GitBranchOutline />
      <span>{{ label }}</span>
      <ChevronDownOutline class="chevron" />
    </button>
    <div v-if="open" class="branch-popover" role="dialog" :aria-label="title">
      <GitBranchSelector
        v-if="!locked"
        :workspace="workspace"
        :worktree="worktree"
        :selected-ref="sourceRef"
        :model-id="modelId"
        :locale="locale"
        @select="(fullRef) => { emit('source-ref', fullRef); open = false }"
        @branch-updated="(value) => emit('branch-updated', value)"
      />
      <div v-else class="branch-locked">
        <GitBranchOutline />
        <div><strong>{{ label }}</strong><span>{{ title }}</span></div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.branch-context{position:relative;display:flex;min-width:0;align-items:center}.branch-trigger{display:flex;min-width:0;min-height:40px;align-items:center;gap:7px;border:1px solid #e5e7eb;border-bottom:0;border-left:0;border-radius:0 14px 0 0;background:#f6f7f8;padding:5px 10px;color:#475569;font-size:12px;cursor:pointer;transition:background-color 160ms ease,color 160ms ease}.branch-trigger:hover:not(:disabled){background:#eaf2ff;color:#1d4ed8}.branch-trigger:focus-visible{outline:2px solid #93c5fd;outline-offset:-2px}.branch-trigger:disabled{cursor:default;opacity:.55}.branch-trigger>svg{width:16px;flex:none}.branch-trigger span{max-width:190px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.branch-trigger .chevron{width:12px}.branch-popover{position:absolute;z-index:72;top:calc(100% + 8px);right:0;width:min(360px,calc(100vw - 32px));overflow:hidden;border:1px solid #e2e8f0;border-radius:14px;background:#fff;box-shadow:0 20px 54px rgba(15,23,42,.18)}.branch-popover :deep(.branch-selector){border-top:0}.branch-locked{display:flex;align-items:flex-start;gap:10px;padding:14px;color:#475569}.branch-locked>svg{width:18px;flex:none;margin-top:1px;color:#2563eb}.branch-locked>div{display:flex;min-width:0;flex-direction:column;gap:3px}.branch-locked strong{overflow:hidden;color:#0f172a;font-size:12px;text-overflow:ellipsis;white-space:nowrap}.branch-locked span{color:#64748b;font-size:10px;line-height:1.5}.branch-context.compact .branch-trigger{min-height:36px;border:0;border-radius:9px;background:transparent;padding:0 8px}.branch-context.compact .branch-trigger:hover:not(:disabled){background:#f1f5f9}.branch-context.compact .branch-popover{top:calc(100% + 6px);left:0;right:auto}:global(html.theme-dark) .branch-trigger{border-color:#334155;background:#111827;color:#cbd5e1}:global(html.theme-dark) .branch-trigger:hover:not(:disabled),:global(html.theme-dark) .branch-context.compact .branch-trigger:hover:not(:disabled){background:#1e293b;color:#93c5fd}:global(html.theme-dark) .branch-popover{border-color:#334155;background:#111827}:global(html.theme-dark) .branch-locked strong{color:#f8fafc}
</style>
