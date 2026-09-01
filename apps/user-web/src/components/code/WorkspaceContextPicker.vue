<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import type { DshWorkspace } from '../../platform/types'

const props = withDefaults(defineProps<{
  workspace: DshWorkspace | null
  locked?: boolean
  busy?: boolean
  worktree?: boolean
  locale?: 'zh' | 'en'
  compact?: boolean
}>(), { locale: 'zh' })

const emit = defineEmits<{
  (event: 'choose'): void
  (event: 'clear'): void
  (event: 'worktree', enabled: boolean): void
}>()

const open = ref(false)
const copied = ref(false)
const pickerRef = ref<HTMLElement | null>(null)
let copiedTimer: ReturnType<typeof setTimeout> | null = null
const generatedTitleSuffix = /\s+·\s+[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i
const label = computed(() => props.workspace?.title.replace(generatedTitleSuffix, '') || (props.locale === 'en' ? 'Choose project' : '选择项目'))
const modeLabel = computed(() => props.worktree
  ? (props.locale === 'en' ? 'New local worktree' : '新建本地工作树')
  : (props.locale === 'en' ? 'Edit locally' : '本地修改'))

function closeOnOutsidePointer(event: PointerEvent) {
  const target = event.target as Node | null
  if (open.value && target && !pickerRef.value?.contains(target)) open.value = false
}
function closeOnEscape(event: KeyboardEvent) { if (event.key === 'Escape') open.value = false }

async function copyPath() {
  const path = props.workspace?.path
  if (!path) return
  try { await navigator.clipboard.writeText(path) }
  catch {
    const input = document.createElement('textarea')
    input.value = path
    input.style.cssText = 'position:fixed;opacity:0'
    document.body.appendChild(input)
    input.select()
    document.execCommand('copy')
    input.remove()
  }
  copied.value = true
  if (copiedTimer) clearTimeout(copiedTimer)
  copiedTimer = setTimeout(() => { copied.value = false }, 1600)
}

function setMode(enabled: boolean) {
  if (!props.locked) emit('worktree', enabled)
}

onMounted(() => {
  document.addEventListener('pointerdown', closeOnOutsidePointer)
  document.addEventListener('keydown', closeOnEscape)
})
onBeforeUnmount(() => {
  document.removeEventListener('pointerdown', closeOnOutsidePointer)
  document.removeEventListener('keydown', closeOnEscape)
  if (copiedTimer) clearTimeout(copiedTimer)
})
</script>

<template>
  <div ref="pickerRef" class="workspace-picker" :class="{ compact }">
    <button
      v-if="compact"
      type="button"
      class="header-trigger"
      :class="{ selected: workspace }"
      :disabled="busy"
      :aria-expanded="open"
      :aria-label="label"
      :title="workspace?.path || label"
      @click="workspace ? (open = !open) : emit('choose')"
    >
      <svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M3 7.5h6l2 2h10v9.5a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7.5Z"/><path d="M3 7.5V6a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v1.5"/></svg>
      <span v-if="locked" class="bound-dot" aria-hidden="true"></span>
    </button>

    <div v-else class="composer-context" aria-label="Project context">
      <button type="button" class="context-segment project" :disabled="busy" :title="workspace?.path || label" @click="workspace ? (open = !open) : emit('choose')">
        <svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M3 7.5h6l2 2h10v9.5a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7.5Z"/></svg>
        <span>{{ busy && !workspace ? (locale === 'en' ? 'Preparing…' : '准备中…') : label }}</span>
        <svg v-if="workspace" class="chevron" aria-hidden="true" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.8"><path d="m6 8 4 4 4-4"/></svg>
      </button>
      <button v-if="workspace && !locked" type="button" class="context-segment" :disabled="busy" :title="modeLabel" @click="open = !open">
        <svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><rect x="3" y="5" width="18" height="13" rx="2"/><path d="M8 21h8M12 18v3"/></svg>
        <span>{{ modeLabel }}</span>
      </button>
    </div>

    <div v-if="open && workspace" class="workspace-menu" role="dialog" :aria-label="locale === 'en' ? 'Project details' : '项目详情'">
      <div class="workspace-heading">
        <div class="project-mark"><svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M3 7.5h6l2 2h10v9.5a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7.5Z"/></svg></div>
        <div class="project-title"><strong>{{ label }}</strong><span>{{ locale === 'en' ? 'Project folder' : '项目目录' }}</span></div>
        <button class="heading-copy" type="button" :title="workspace.path" :aria-label="locale === 'en' ? 'Copy project path' : '复制项目地址'" @click="copyPath">
          <svg v-if="!copied" aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><rect x="8" y="8" width="11" height="11" rx="2"/><path d="M16 8V5a2 2 0 0 0-2-2H5a2 2 0 0 0-2 2v9a2 2 0 0 0 2 2h3"/></svg>
          <svg v-else aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="m5 12 4 4L19 6"/></svg>
          <span>{{ copied ? (locale === 'en' ? 'Copied' : '已复制') : (locale === 'en' ? 'Copy path' : '复制路径') }}</span>
        </button>
      </div>
      <div class="detail-grid detail-grid--single">
        <div><span>{{ locale === 'en' ? 'Run mode' : '修改方式' }}</span><strong>{{ modeLabel }}</strong></div>
      </div>
      <fieldset v-if="!locked" class="mode-options">
        <legend>{{ locale === 'en' ? 'Choose how this task changes files' : '选择本任务的文件修改方式' }}</legend>
        <button type="button" :class="{ active: !worktree }" @click="setMode(false)"><span class="radio"><i></i></span><span><strong>{{ locale === 'en' ? 'Edit locally' : '本地修改' }}</strong><small>{{ locale === 'en' ? 'Make changes directly in the current project and branch.' : '直接在当前项目和当前分支中修改。' }}</small></span></button>
        <button type="button" :class="{ active: worktree }" @click="setMode(true)"><span class="radio"><i></i></span><span><strong>{{ locale === 'en' ? 'New local worktree' : '新建本地工作树' }}</strong><small>{{ locale === 'en' ? 'Create an isolated folder from the selected starting branch; no branch is created yet.' : '从所选起始分支创建隔离目录，暂不创建新分支。' }}</small></span></button>
      </fieldset>
      <div v-if="!locked" class="menu-actions">
        <button type="button" @click="emit('choose'); open = false">{{ locale === 'en' ? 'Choose another folder…' : '选择其他文件夹…' }}</button>
        <button type="button" class="clear" @click="emit('clear'); open = false">{{ locale === 'en' ? 'Remove project' : '移除项目' }}</button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.workspace-picker{position:relative;display:flex;min-width:0;align-items:center}.composer-context{display:flex;width:100%;min-height:40px;align-items:center;overflow:hidden;border:1px solid #e5e7eb;border-bottom:0;border-radius:14px 14px 0 0;background:#f6f7f8;padding:3px 7px;color:#3f4650}.context-segment{display:inline-flex;min-width:0;min-height:34px;align-items:center;gap:7px;border:0;border-radius:8px;background:transparent;padding:5px 9px;color:inherit;font-size:13px;cursor:pointer;transition:background-color 160ms ease,color 160ms ease}.context-segment:hover:not(:disabled){background:#e9ebee;color:#111827}.context-segment:focus-visible,.header-trigger:focus-visible,.workspace-menu button:focus-visible{outline:2px solid #2563eb;outline-offset:1px}.context-segment:disabled{cursor:default}.context-segment.project{max-width:240px}.context-segment span{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.context-segment>svg{width:18px;height:18px;flex:none}.context-segment .chevron{width:13px;height:13px}.context-segment.branch{max-width:270px;cursor:default;color:#525966}.header-trigger{position:relative;display:grid;width:36px;height:36px;place-items:center;border:0;border-radius:9px;background:transparent;color:#475569;cursor:pointer;transition:background-color 160ms ease,color 160ms ease}.header-trigger:hover:not(:disabled),.header-trigger.selected{background:#f1f5f9;color:#2563eb}.header-trigger>svg{width:18px;height:18px}.bound-dot{position:absolute;right:5px;bottom:5px;width:7px;height:7px;border:1.5px solid #fff;border-radius:99px;background:#22c55e}.workspace-menu{position:absolute;z-index:70;top:calc(100% + 8px);left:0;width:min(380px,calc(100vw - 32px));overflow:hidden;border:1px solid #e2e8f0;border-radius:16px;background:#fff;box-shadow:0 20px 54px rgba(15,23,42,.18);color:#334155}.workspace-heading{display:flex;align-items:center;gap:10px;padding:14px 15px 10px}.workspace-heading>div:last-child{display:flex;min-width:0;flex-direction:column}.workspace-heading strong{overflow:hidden;color:#0f172a;font-size:14px;text-overflow:ellipsis;white-space:nowrap}.workspace-heading span{margin-top:1px;color:#94a3b8;font-size:11px}.project-mark{display:grid;width:34px;height:34px;flex:none;place-items:center;border-radius:9px;background:#eff6ff;color:#2563eb}.project-mark svg{width:18px;height:18px}.path-row{display:flex;align-items:center;gap:8px;margin:0 14px 12px;border:1px solid #e2e8f0;border-radius:10px;background:#f8fafc;padding:6px 6px 6px 10px}.path-row>span{min-width:0;flex:1;overflow:hidden;color:#64748b;font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:11px;text-overflow:ellipsis;white-space:nowrap}.path-row button{display:flex;min-height:32px;align-items:center;gap:5px;border:0;border-radius:7px;background:#fff;padding:0 8px;color:#475569;font-size:11px;cursor:pointer;box-shadow:0 0 0 1px #e2e8f0}.path-row button:hover{color:#2563eb}.path-row svg{width:14px;height:14px}.detail-grid{display:grid;grid-template-columns:1fr 1fr;gap:1px;border-block:1px solid #edf0f4;background:#edf0f4}.detail-grid--single{grid-template-columns:1fr}.detail-grid>div{display:flex;min-width:0;flex-direction:column;gap:3px;background:#fff;padding:10px 14px}.detail-grid span{color:#94a3b8;font-size:10px}.detail-grid strong{overflow:hidden;color:#334155;font-size:12px;text-overflow:ellipsis;white-space:nowrap}.mode-options{display:flex;flex-direction:column;gap:5px;margin:0;border:0;padding:12px 10px}.mode-options legend{padding:0 4px 7px;color:#64748b;font-size:11px}.mode-options button{display:flex;width:100%;min-height:54px;align-items:flex-start;gap:10px;border:1px solid transparent;border-radius:10px;background:transparent;padding:8px 9px;text-align:left;color:#334155;cursor:pointer}.mode-options button:hover:not(:disabled){background:#f8fafc}.mode-options button.active{border-color:#bfdbfe;background:#eff6ff}.mode-options button>span:last-child{display:flex;min-width:0;flex-direction:column}.mode-options strong{font-size:12px}.mode-options small{margin-top:2px;color:#64748b;font-size:10px;line-height:1.45}.radio{display:grid;width:16px;height:16px;flex:none;place-items:center;margin-top:1px;border:1.5px solid #94a3b8;border-radius:99px}.active .radio{border-color:#2563eb}.active .radio i{width:8px;height:8px;border-radius:99px;background:#2563eb}.menu-actions{display:grid;grid-template-columns:1fr auto;border-top:1px solid #eef2f7}.menu-actions button{min-height:44px;border:0;background:#fff;padding:8px 14px;text-align:left;color:#334155;font-size:12px;cursor:pointer}.menu-actions button:hover{background:#f8fafc}.menu-actions button.clear{color:#b45309}.workspace-picker:not(.compact){width:100%;margin-bottom:-1px}.workspace-picker:not(.compact)+*{border-top-left-radius:0!important;border-top-right-radius:0!important}@media(max-width:640px){.context-segment.branch{display:none}.context-segment.project{max-width:55%}.detail-grid{grid-template-columns:1fr}}:global(html.theme-dark) .composer-context{border-color:#334155;background:#111827;color:#cbd5e1}:global(html.theme-dark) .context-segment:hover:not(:disabled),:global(html.theme-dark) .header-trigger:hover,:global(html.theme-dark) .header-trigger.selected{background:#1e293b;color:#93c5fd}:global(html.theme-dark) .workspace-menu,:global(html.theme-dark) .detail-grid>div,:global(html.theme-dark) .menu-actions button,:global(html.theme-dark) .path-row button{border-color:#334155;background:#111827;color:#cbd5e1}:global(html.theme-dark) .workspace-heading strong{color:#f8fafc}:global(html.theme-dark) .path-row{border-color:#334155;background:#0f172a}:global(html.theme-dark) .mode-options button.active{border-color:#1d4ed8;background:#172554}
</style>

<style scoped>
.workspace-picker:not(.compact) .workspace-menu {
  top: calc(100% + 8px);
  bottom: auto;
  max-height: calc(50vh - 24px);
  overflow-y: auto;
}

.project-title {
  display: flex;
  min-width: 0;
  flex: 1;
  flex-direction: column;
}

.heading-copy {
  display: inline-flex;
  min-height: 36px;
  flex: none;
  align-items: center;
  gap: 6px;
  border: 0;
  border-radius: 8px;
  background: transparent;
  padding: 0 8px;
  color: #64748b;
  font-size: 11px;
  cursor: pointer;
  transition: background-color 160ms ease, color 160ms ease;
}

.heading-copy:hover {
  background: #f1f5f9;
  color: #2563eb;
}

.heading-copy svg {
  width: 15px;
  height: 15px;
}

.context-segment.branch:not(:disabled) {
  cursor: pointer;
}
</style>
