<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import GitBranchOutline from '@vicons/ionicons5/es/GitBranchOutline'
import GitCommitOutline from '@vicons/ionicons5/es/GitCommitOutline'
import SearchOutline from '@vicons/ionicons5/es/SearchOutline'
import { commitDshWorkspaceChanges, getDshWorkspaceFileDiff, getDshWorkspaceSummary, pushDshWorkspaceChanges } from '../../platform'
import type { DshFileDiff, DshGitCommitResult, DshGitPushResult, DshWorkspaceSummary } from '../../platform/types'
import CodeFileTypeIcon from './CodeFileTypeIcon.vue'
import GitCommitDialog from './GitCommitDialog.vue'
import GitPublishStatus from './GitPublishStatus.vue'
import UnifiedDiffView from './UnifiedDiffView.vue'
import WorkspaceChangeTreeNode from './WorkspaceChangeTreeNode.vue'
import { changeStatusPresentation } from './changePresentation'
import { buildWorkspaceChangeTree } from './changeTree'
import { suggestCommitMessage } from './commitMessageSuggestion'

const props = defineProps<{ sessionId: string; locale?: 'zh' | 'en'; running?: boolean; requestedPath?: string }>()
const emit = defineEmits<{ (event: 'committed', result: DshGitCommitResult): void }>()
const summary = ref<DshWorkspaceSummary | null>(null)
const selected = ref('')
const fileDiff = ref<DshFileDiff | null>(null)
const loading = ref(false)
const filter = ref('')
const error = ref('')
const commitDialogOpen = ref(false)
const committing = ref(false)
const commitAction = ref<'commit' | 'commit-push'>('commit')
const commitError = ref('')
const lastCommit = ref<DshGitCommitResult | null>(null)
const lastPush = ref<DshGitPushResult | null>(null)
const pushing = ref(false)
const pushError = ref('')
const filtered = computed(() => (summary.value?.changes || []).filter(item => item.path.toLowerCase().includes(filter.value.trim().toLowerCase())))
const tree = computed(() => buildWorkspaceChangeTree(filtered.value))
const totals = computed(() => filtered.value.reduce((value, item) => ({ additions: value.additions + (item.additions || 0), deletions: value.deletions + (item.deletions || 0) }), { additions: 0, deletions: 0 }))
const selectedChange = computed(() => summary.value?.changes.find(item => item.path === selected.value))
const selectedName = computed(() => selected.value.split('/').pop() || selected.value)
const selectedDirectory = computed(() => selected.value.includes('/') ? selected.value.slice(0, selected.value.lastIndexOf('/')) : '')
const selectedStatus = computed(() => changeStatusPresentation(selectedChange.value?.status || '', props.locale))
const commitSuggestion = computed(() => summary.value ? suggestCommitMessage(summary.value, props.locale) : '')
const detached = computed(() => Boolean(summary.value?.git_available && !summary.value.branch))
const branchSuggestion = computed(() => {
  const suffix = props.sessionId.replace(/^dsh-code-/, '').replace(/[^a-zA-Z0-9_-]/g, '-').slice(0, 32)
  return `askai/${suffix || 'task'}`
})
const canCommit = computed(() => Boolean(summary.value?.git_available && summary.value.changes.length && !props.running && !committing.value))

function readableError(value: unknown): string {
  if (value instanceof Error) return value.message
  if (typeof value === 'string') return value
  try { return JSON.stringify(value) } catch { return String(value) }
}

async function refresh() {
  error.value = ''
  try {
    summary.value = await getDshWorkspaceSummary(props.sessionId)
    const changes = summary.value.changes
    const requested = props.requestedPath && changes.some(item => item.path === props.requestedPath) ? props.requestedPath : ''
    if (requested && requested !== selected.value) await select(requested)
    else if (changes.length && !changes.some(item => item.path === selected.value)) await select(changes[0].path)
    if (!changes.length) { selected.value = ''; fileDiff.value = null }
  }
  catch (value) { error.value = String(value) }
}
function openCommitDialog() {
  if (!canCommit.value) return
  commitError.value = ''
  commitDialogOpen.value = true
}
async function commit(message: string, push: boolean, branchName?: string) {
  if (props.running) {
    commitError.value = props.locale === 'en' ? 'Wait for the current Code task to finish before committing.' : '请等待当前 Code 任务完成后再提交。'
    return
  }
  committing.value = true
  commitAction.value = push ? 'commit-push' : 'commit'
  commitError.value = ''
  pushError.value = ''
  try {
    const effectiveMessage = message.trim() || commitSuggestion.value
    const result = await commitDshWorkspaceChanges(props.sessionId, effectiveMessage, push, branchName)
    lastCommit.value = result
    lastPush.value = result.push || null
    commitDialogOpen.value = false
    await refresh()
    emit('committed', result)
  } catch (value) {
    commitError.value = readableError(value)
  } finally {
    committing.value = false
  }
}
async function push(expectedCommitHash: string) {
  if (props.running || pushing.value) return
  pushing.value = true
  pushError.value = ''
  try {
    const result = await pushDshWorkspaceChanges(props.sessionId, expectedCommitHash)
    lastPush.value = result
    if (lastCommit.value?.commit_hash === result.commit_hash) {
      lastCommit.value = { ...lastCommit.value, push: result, push_error: undefined }
    }
    await refresh()
    emit('committed', lastCommit.value || {
      commit_hash: result.commit_hash, short_hash: result.commit_hash.slice(0, 8), branch: result.branch,
      message: '', changed_files: 0, push: result,
    })
  } catch (value) {
    pushError.value = readableError(value)
  } finally {
    pushing.value = false
  }
}
async function select(path: string) {
  selected.value = path; loading.value = true; error.value = ''
  try { fileDiff.value = await getDshWorkspaceFileDiff(props.sessionId, path) }
  catch (value) { error.value = String(value); fileDiff.value = null }
  finally { loading.value = false }
}
watch(() => props.sessionId, refresh)
watch(() => props.requestedPath, path => { if (path && summary.value?.changes.some(item => item.path === path)) void select(path) })
onMounted(refresh)
</script>

<template>
  <div class="changes">
    <nav>
      <div class="overview">
        <div class="branch">
          <div class="branch-label"><GitBranchOutline /><span>{{ summary?.branch || (locale === 'en' ? 'No branch' : '无分支') }}</span></div>
          <button type="button" class="commit-button" :disabled="!canCommit" :title="running ? (locale === 'en' ? 'Wait for the current task to finish' : '请等待当前任务完成') : ''" @click="openCommitDialog"><GitCommitOutline />{{ locale === 'en' ? 'Commit' : '提交' }}</button>
        </div>
        <div class="metrics">
          <div><strong>{{ filtered.length }}</strong><span>{{ locale === 'en' ? 'files' : '个文件' }}</span></div>
          <div class="metric-add"><strong>+{{ totals.additions }}</strong><span>{{ locale === 'en' ? 'lines added' : '增加行' }}</span></div>
          <div class="metric-delete"><strong>-{{ totals.deletions }}</strong><span>{{ locale === 'en' ? 'lines removed' : '删除行' }}</span></div>
        </div>
      </div>
      <label class="filter"><SearchOutline /><input v-model="filter" :placeholder="locale === 'en' ? 'Filter changed files…' : '筛选变更文件…'" /></label>
      <div class="tree-scroll">
        <WorkspaceChangeTreeNode v-for="node in tree" :key="node.path" :node="node" :selected-path="selected" :locale="locale" @select="select" />
        <div v-if="!filtered.length" class="empty tree-empty">{{ locale === 'en' ? 'No matching changes' : '没有匹配的变更' }}</div>
      </div>
      <div v-if="summary && !summary.git_available" class="git-warning">{{ locale === 'en' ? 'Git information unavailable' : '无法读取 Git 信息' }}</div>
      <GitPublishStatus v-else :commit="lastCommit" :push="lastPush" :summary="summary" :busy="pushing" :error="pushError" :locale="locale" @push="push" />
    </nav>
    <main>
      <div v-if="selected" class="diff-heading">
        <CodeFileTypeIcon :path="selected" />
        <div class="file-title"><strong>{{ selectedName }}</strong><span v-if="selectedDirectory">{{ selectedDirectory }}</span></div>
        <span class="selected-status" :class="`tone-${selectedStatus.tone}`">{{ selectedStatus.label }}</span>
        <span v-if="selectedChange?.binary" class="diff-stat">BIN</span>
        <span v-else-if="selectedChange && ((selectedChange.additions || 0) > 0 || (selectedChange.deletions || 0) > 0)" class="diff-stat"><b v-if="(selectedChange.additions || 0) > 0">+{{ selectedChange.additions }}</b><i v-if="(selectedChange.deletions || 0) > 0">-{{ selectedChange.deletions }}</i></span>
      </div>
      <div v-if="error" class="empty error">{{ error }}</div>
      <div v-else-if="loading" class="empty">{{ locale === 'en' ? 'Loading diff…' : '正在读取变更…' }}</div>
      <UnifiedDiffView v-else-if="fileDiff?.diff" :diff="fileDiff.diff" :path="selected" />
      <div v-else class="empty">{{ locale === 'en' ? 'Select a changed file.' : '选择文件后查看具体代码变更。' }}</div>
      <div v-if="fileDiff?.truncated" class="notice">{{ locale === 'en' ? 'Diff truncated for safety.' : '变更较大，仅显示安全范围内的内容。' }}</div>
    </main>
    <GitCommitDialog :show="commitDialogOpen" :file-count="summary?.changes.length || 0" :busy="committing" :busy-action="commitAction" :blocked="running" :push-available="Boolean(summary?.remote_names.length)" :detached="detached" :branch-suggestion="branchSuggestion" :error="commitError" :locale="locale" @close="commitDialogOpen = false" @commit="commit" />
  </div>
</template>

<style scoped>
.changes{display:grid;min-height:0;height:100%;grid-template-columns:minmax(270px,38%) minmax(0,1fr)}nav{display:flex;min-width:0;min-height:0;flex-direction:column;border-right:1px solid #e2e8f0;background:#fbfcfe}.overview{padding:14px 14px 12px;border-bottom:1px solid #edf0f4}.branch{display:flex;align-items:center;gap:7px;margin-bottom:12px;color:#475569;font-size:11px}.branch svg{width:14px;height:14px;color:#64748b}.branch span{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.metrics{display:grid;grid-template-columns:repeat(3,1fr);gap:6px}.metrics>div{display:flex;min-width:0;flex-direction:column;gap:1px;border:1px solid #e6eaf0;border-radius:8px;background:#fff;padding:7px 8px}.metrics strong{color:#334155;font-size:12px;font-variant-numeric:tabular-nums}.metrics span{color:#94a3b8;font-size:9px}.metrics .metric-add strong{color:#15803d}.metrics .metric-delete strong{color:#dc2626}.filter{display:flex;height:34px;flex:none;align-items:center;gap:7px;margin:10px 10px 7px;border:1px solid #dbe3ee;border-radius:8px;background:#fff;padding:0 9px;color:#94a3b8;transition:border-color .15s,box-shadow .15s}.filter:focus-within{border-color:#93b4f8;box-shadow:0 0 0 3px #dbeafe80}.filter svg{width:14px;flex:none}.filter input{min-width:0;width:100%;border:0;outline:0;background:transparent;color:#334155;font-size:11px}.filter input::placeholder{color:#a5b0c0}.tree-scroll{min-height:0;flex:1;overflow:auto;padding:0 7px 12px}.tree-empty{min-height:100px}.git-warning{border-top:1px solid #fed7aa;background:#fff7ed;padding:8px 12px;color:#9a3412;font-size:10px}main{position:relative;min-width:0;overflow:auto;background:#fff}.diff-heading{position:sticky;z-index:3;top:0;display:flex;height:52px;box-sizing:border-box;align-items:center;gap:9px;border-bottom:1px solid #e2e8f0;background:#fff;padding:7px 14px;color:#334155}.file-title{display:flex;min-width:0;flex:1;flex-direction:column;gap:2px}.file-title strong,.file-title span{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.file-title strong{color:#1e293b;font:600 12px/1.2 ui-sans-serif,system-ui}.file-title span{color:#94a3b8;font:9px/1.2 ui-monospace,SFMono-Regular,Menlo,monospace}.selected-status{flex:none;padding:1px 2px;color:#64748b;font:700 10px ui-monospace,SFMono-Regular,Menlo,monospace}.selected-status.tone-added{color:#15803d}.selected-status.tone-modified{color:#a16207}.selected-status.tone-deleted,.selected-status.tone-conflict{color:#dc2626}.selected-status.tone-renamed{color:#7c3aed}.diff-stat{display:flex;flex:none;gap:5px;color:#64748b;font:10px ui-monospace,monospace}.diff-stat b{color:#15803d}.diff-stat i{color:#dc2626;font-style:normal}.empty{display:grid;min-height:120px;place-items:center;padding:20px;color:#94a3b8;font-size:12px}.error{color:#dc2626}.notice{position:sticky;bottom:0;background:#fff7ed;padding:7px 12px;color:#9a3412;font-size:11px}:global(html.theme-dark) main{background:#0b1220}:global(html.theme-dark) .diff-heading{border-color:#263248;background:#111a2a;color:#cbd5e1}:global(html.theme-dark) .file-title strong{color:#e2e8f0}:global(html.theme-dark) .file-title span{color:#718096}:global(html.theme-dark) .selected-status{color:#94a3b8}:global(html.theme-dark) .selected-status.tone-added,:global(html.theme-dark) .diff-stat b{color:#4ade80}:global(html.theme-dark) .selected-status.tone-modified{color:#facc15}:global(html.theme-dark) .selected-status.tone-deleted,:global(html.theme-dark) .selected-status.tone-conflict,:global(html.theme-dark) .diff-stat i{color:#f87171}:global(html.theme-dark) .selected-status.tone-renamed{color:#a78bfa}:global(html.theme-dark) .diff-stat{color:#94a3b8}:global(html.theme-dark) .error{color:#fca5a5}:global(html.theme-dark) .notice{background:#7c2d12;color:#ffedd5}@media(max-width:680px){.changes{grid-template-columns:minmax(210px,44%) minmax(0,1fr)}.metrics span{display:none}}
.branch{justify-content:space-between;gap:8px}
.branch-label{display:flex;min-width:0;align-items:center;gap:7px}
.branch-label span{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.commit-button{display:flex;height:27px;flex:none;align-items:center;gap:5px;border:1px solid #cbd5e1;border-radius:7px;background:#fff;padding:0 9px;color:#334155;font-size:10px;font-weight:650;cursor:pointer}
.commit-button svg{width:13px;height:13px;color:#475569}
.commit-button:hover:not(:disabled){border-color:#93b4f8;background:#eff6ff;color:#1d4ed8}
.commit-button:disabled{cursor:not-allowed;opacity:.45}
:global(html.theme-dark) .commit-button{border-color:#3b485d;background:#172033;color:#cbd5e1}
:global(html.theme-dark) .commit-button svg{color:#94a3b8}
:global(html.theme-dark) .commit-button:hover:not(:disabled){border-color:#3b82f6;background:#172554;color:#bfdbfe}
</style>
