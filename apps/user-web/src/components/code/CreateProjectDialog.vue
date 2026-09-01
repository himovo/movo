<script setup lang="ts">
import { computed } from 'vue'
import { NButton, NModal, NRadio, NRadioGroup } from 'naive-ui'
import type { DshWorkspace } from '../../platform/types'

const props = defineProps<{ show: boolean; workspace: DshWorkspace | null; worktree: boolean; busy?: boolean; locale?: 'zh' | 'en' }>()
const emit = defineEmits<{ (event: 'update:worktree', value: boolean): void; (event: 'choose-folder'): void; (event: 'create'): void; (event: 'close'): void }>()

const projectName = computed(() => {
  if (!props.workspace) return ''
  const normalizedPath = props.workspace.path.replace(/[\\/]+$/, '')
  return normalizedPath.split(/[\\/]/).pop() || props.workspace.title
})
const canCreate = computed(() => Boolean(props.workspace && !props.busy))
</script>

<template>
  <NModal :show="show" preset="card" :mask-closable="!busy" :closable="!busy" style="width:440px" :title="locale === 'en' ? 'Create project' : '创建项目'" @update:show="(value) => !value && emit('close')">
    <div class="project-dialog">
      <section class="field-group">
        <span class="field-label">{{ locale === 'en' ? 'Local folder' : '本地目录' }}</span>
        <div class="folder-row">
          <div class="folder-details">
            <strong>{{ projectName || (locale === 'en' ? 'No folder selected' : '尚未选择目录') }}</strong>
            <span :title="workspace?.path">{{ workspace?.path || (locale === 'en' ? 'The project will use the folder name' : '项目将自动使用目录名称') }}</span>
          </div>
          <NButton size="small" :disabled="busy" @click="emit('choose-folder')">{{ locale === 'en' ? 'Choose folder' : '选择文件夹' }}</NButton>
        </div>
      </section>
      <section class="field-group">
        <span class="field-label">{{ locale === 'en' ? 'Change mode' : '修改方式' }}</span>
        <NRadioGroup :value="worktree" :disabled="busy" @update:value="(value) => emit('update:worktree', Boolean(value))">
          <div class="mode-options">
            <NRadio :value="false"><span class="mode-copy"><strong>{{ locale === 'en' ? 'Edit locally' : '本地修改' }}</strong><small>{{ locale === 'en' ? 'Use the current branch' : '直接在当前分支中修改' }}</small></span></NRadio>
            <NRadio :value="true"><span class="mode-copy"><strong>{{ locale === 'en' ? 'New local worktree' : '新建本地工作树' }}</strong><small>{{ locale === 'en' ? 'Create an isolated folder; create a branch only when keeping changes' : '创建隔离目录；保留成果时再创建分支' }}</small></span></NRadio>
          </div>
        </NRadioGroup>
      </section>
    </div>
    <template #footer><div class="dialog-actions"><NButton :disabled="busy" @click="emit('close')">{{ locale === 'en' ? 'Cancel' : '取消' }}</NButton><NButton type="primary" :loading="busy" :disabled="!canCreate" @click="emit('create')">{{ locale === 'en' ? 'Create project' : '创建项目' }}</NButton></div></template>
  </NModal>
</template>

<style scoped>
.project-dialog{display:flex;flex-direction:column;gap:18px}.field-group{display:flex;flex-direction:column;gap:8px}.field-label{color:#475569;font-size:13px;font-weight:600}.folder-row{display:flex;min-width:0;align-items:center;gap:8px}.folder-details{display:flex;min-width:0;flex:1;flex-direction:column;gap:2px;overflow:hidden;border:1px solid #e2e8f0;border-radius:8px;background:#f8fafc;padding:8px 10px}.folder-details strong{overflow:hidden;color:#334155;font-size:13px;text-overflow:ellipsis;white-space:nowrap}.folder-details span{overflow:hidden;color:#94a3b8;font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:10px;text-overflow:ellipsis;white-space:nowrap}.mode-options{display:grid;grid-template-columns:1fr 1fr;gap:8px}.mode-options :deep(.n-radio){align-items:flex-start;margin:0;border:1px solid #e2e8f0;border-radius:8px;padding:9px;transition:border-color .15s,background-color .15s}.mode-options :deep(.n-radio--checked){border-color:#93c5fd;background:#eff6ff}.mode-options :deep(.n-radio__label){min-width:0}.mode-copy{display:flex;flex-direction:column;gap:2px}.mode-copy strong{color:#334155;font-size:12px;line-height:18px}.mode-copy small{color:#94a3b8;font-size:10px;line-height:14px}.dialog-actions{display:flex;justify-content:flex-end;gap:8px}
</style>
