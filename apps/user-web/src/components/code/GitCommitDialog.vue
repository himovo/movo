<script setup lang="ts">
import { nextTick, ref, watch } from 'vue'
import CloseOutline from '@vicons/ionicons5/es/CloseOutline'

const props = defineProps<{
  show: boolean
  fileCount: number
  busy?: boolean
  blocked?: boolean
  pushAvailable?: boolean
  detached?: boolean
  branchSuggestion?: string
  busyAction?: 'commit' | 'commit-push'
  error?: string
  locale?: 'zh' | 'en'
}>()
const emit = defineEmits<{
  (event: 'close'): void
  (event: 'commit', message: string, push: boolean, branchName?: string): void
}>()
const message = ref('')
const branchName = ref('')
const textarea = ref<HTMLTextAreaElement | null>(null)

watch(() => props.show, async show => {
  if (!show) return
  message.value = ''
  branchName.value = props.branchSuggestion || ''
  await nextTick()
  textarea.value?.focus()
})

function close() {
  if (!props.busy) emit('close')
}
function submit(push: boolean) {
  if (props.detached && !branchName.value.trim()) return
  if (!props.busy && !props.blocked && (!push || props.pushAvailable)) emit('commit', message.value.trim(), push, branchName.value.trim() || undefined)
}
</script>

<template>
  <Teleport to="body">
    <div v-if="show" class="commit-backdrop" role="presentation" @mousedown.self="close">
      <section class="commit-dialog" role="dialog" aria-modal="true" :aria-label="locale === 'en' ? 'Commit changes' : '提交代码变更'" @keydown.esc="close">
        <header>
          <div>
            <strong>{{ locale === 'en' ? 'Commit changes' : '提交代码变更' }}</strong>
            <span>{{ locale === 'en' ? `All ${fileCount} changed files will be committed` : `将提交当前工作区的全部 ${fileCount} 个变更文件` }}</span>
          </div>
          <button type="button" class="icon-button" :disabled="busy" :aria-label="locale === 'en' ? 'Close' : '关闭'" @click="close"><CloseOutline /></button>
        </header>
        <div class="commit-body">
          <div v-if="detached" class="branch-field">
            <label for="git-commit-branch">{{ locale === 'en' ? 'Branch for these changes' : '保存到新分支' }}</label>
            <input id="git-commit-branch" v-model="branchName" :disabled="busy" maxlength="240" placeholder="feature/example" />
            <span>{{ locale === 'en' ? 'This isolated Worktree has no branch yet. It will be created when you commit.' : '当前隔离 Worktree 尚无分支；提交时才会创建。' }}</span>
          </div>
          <div class="field-heading">
            <label for="git-commit-message">{{ locale === 'en' ? 'Commit message (optional)' : '提交说明（可选）' }}</label>
          </div>
          <textarea id="git-commit-message" ref="textarea" v-model="message" maxlength="2000" rows="4" :disabled="busy" :placeholder="locale === 'en' ? 'Enter a message, or leave blank to generate one automatically' : '输入提交说明；留空将根据本次变更自动生成'" @keydown.meta.enter.prevent="submit(false)" @keydown.ctrl.enter.prevent="submit(false)"></textarea>
          <div class="field-foot"><span>{{ locale === 'en' ? 'Leave blank to generate from the changed files.' : '不填写也可以直接提交。' }}</span><span>{{ message.length }}/2000</span></div>
          <p v-if="error" class="commit-error">{{ error }}</p>
        </div>
        <footer>
          <button type="button" class="cancel" :disabled="busy" @click="close">{{ locale === 'en' ? 'Cancel' : '取消' }}</button>
          <span class="footer-spacer"></span>
          <button type="button" class="secondary" :disabled="busy || blocked || (detached && !branchName.trim())" @click="submit(false)">{{ busy && busyAction === 'commit' ? (locale === 'en' ? 'Committing…' : '正在提交…') : (locale === 'en' ? 'Commit' : '提交') }}</button>
          <button type="button" class="primary" :disabled="busy || blocked || !pushAvailable || (detached && !branchName.trim())" :title="!pushAvailable ? (locale === 'en' ? 'No Git remote is configured' : '当前仓库尚未配置远程地址') : ''" @click="submit(true)">{{ busy && busyAction === 'commit-push' ? (locale === 'en' ? 'Committing and pushing…' : '正在提交并推送…') : (locale === 'en' ? 'Commit & Push' : '提交并推送') }}</button>
        </footer>
      </section>
    </div>
  </Teleport>
</template>

<style scoped>
.commit-backdrop{position:fixed;z-index:1000;inset:0;display:grid;place-items:center;background:#0f172a52;padding:24px;backdrop-filter:blur(2px)}
.commit-dialog{width:min(520px,100%);overflow:hidden;border:1px solid #dbe3ee;border-radius:14px;background:#fff;box-shadow:0 24px 64px #0f172a38;color:#1e293b}
header{display:flex;align-items:flex-start;justify-content:space-between;border-bottom:1px solid #e8edf3;padding:18px 18px 14px}
header>div{display:flex;min-width:0;flex-direction:column;gap:5px}header strong{font-size:15px}header span{color:#64748b;font-size:11px}
.icon-button{display:grid;width:30px;height:30px;flex:none;place-items:center;border:0;border-radius:8px;background:transparent;color:#64748b;cursor:pointer}.icon-button:hover{background:#f1f5f9}.icon-button svg{width:17px}
.commit-body{padding:16px 18px 12px}.field-heading,.field-foot{display:flex;align-items:center;justify-content:space-between}.field-heading{margin-bottom:7px}.field-heading label{font-size:12px;font-weight:650}
.branch-field{display:flex;flex-direction:column;gap:6px;margin-bottom:15px;border-radius:9px;background:#f8fafc;padding:10px}.branch-field label{color:#334155;font-size:11px;font-weight:650}.branch-field input{height:34px;border:1px solid #cbd5e1;border-radius:8px;background:#fff;padding:0 9px;color:#334155;font:11px ui-monospace,SFMono-Regular,Menlo,monospace;outline:0}.branch-field input:focus{border-color:#60a5fa;box-shadow:0 0 0 3px #dbeafe}.branch-field span{color:#64748b;font-size:10px;line-height:1.45}
textarea{box-sizing:border-box;width:100%;resize:vertical;border:1px solid #cfd8e5;border-radius:9px;outline:0;background:#fff;padding:10px 11px;color:#1e293b;font:12px/1.55 ui-sans-serif,system-ui;transition:border-color .15s,box-shadow .15s}textarea:focus{border-color:#7aa2f7;box-shadow:0 0 0 3px #dbeafe}textarea:disabled{background:#f8fafc}
.field-foot{margin-top:5px;color:#94a3b8;font-size:10px}.commit-error{margin:10px 0 0;border-radius:7px;background:#fef2f2;padding:8px 9px;color:#b91c1c;font-size:11px;white-space:pre-wrap}
footer{display:flex;justify-content:flex-end;gap:8px;border-top:1px solid #e8edf3;padding:12px 18px 14px}.footer-spacer{flex:1}footer button{height:32px;border-radius:8px;padding:0 14px;font-size:12px;font-weight:600;cursor:pointer}footer button:disabled{cursor:not-allowed;opacity:.55}.cancel{border:0;background:transparent;color:#64748b}.secondary{border:1px solid #d5dde8;background:#fff;color:#475569}.primary{border:1px solid #2563eb;background:#2563eb;color:#fff}.primary:hover:not(:disabled){background:#1d4ed8}
:global(html.theme-dark) .commit-backdrop{background:#02061799}:global(html.theme-dark) .commit-dialog{border-color:#334155;background:#111827;color:#e2e8f0}:global(html.theme-dark) header,:global(html.theme-dark) footer{border-color:#293548}:global(html.theme-dark) header span{color:#94a3b8}:global(html.theme-dark) .icon-button{color:#94a3b8}:global(html.theme-dark) .icon-button:hover{background:#263248}:global(html.theme-dark) textarea{border-color:#3b485d;background:#0b1220;color:#e2e8f0}:global(html.theme-dark) textarea:focus{border-color:#60a5fa;box-shadow:0 0 0 3px #1e3a5f}:global(html.theme-dark) textarea:disabled{background:#172033}:global(html.theme-dark) .secondary{border-color:#475569;background:#172033;color:#cbd5e1}:global(html.theme-dark) .cancel{color:#94a3b8}:global(html.theme-dark) .commit-error{background:#451a1a;color:#fecaca}
:global(html.theme-dark) .branch-field{background:#172033}:global(html.theme-dark) .branch-field label{color:#e2e8f0}:global(html.theme-dark) .branch-field input{border-color:#3b485d;background:#0b1220;color:#e2e8f0}:global(html.theme-dark) .branch-field span{color:#94a3b8}
</style>
