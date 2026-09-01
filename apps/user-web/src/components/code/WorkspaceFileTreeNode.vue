<script setup lang="ts">
import { ref } from 'vue'
import ChevronForwardOutline from '@vicons/ionicons5/es/ChevronForwardOutline'
import FolderOutline from '@vicons/ionicons5/es/FolderOutline'
import FolderOpenOutline from '@vicons/ionicons5/es/FolderOpenOutline'
import { listDshWorkspaceDirectory } from '../../platform'
import type { DshDirectoryEntry } from '../../platform/types'
import CodeFileTypeIcon from './CodeFileTypeIcon.vue'

defineOptions({ name: 'WorkspaceFileTreeNode' })
const props = defineProps<{ sessionId: string; entry: DshDirectoryEntry; selectedPath?: string }>()
const emit = defineEmits<{ (event: 'select', entry: DshDirectoryEntry): void }>()
const expanded = ref(false)
const loading = ref(false)
const children = ref<DshDirectoryEntry[] | null>(null)

async function activate() {
  if (props.entry.kind === 'file') return emit('select', props.entry)
  expanded.value = !expanded.value
  if (!expanded.value || children.value) return
  loading.value = true
  try { children.value = await listDshWorkspaceDirectory(props.sessionId, props.entry.path) }
  finally { loading.value = false }
}
</script>

<template>
  <div class="tree-node">
    <button type="button" :class="{ selected: selectedPath === entry.path }" @click="activate">
      <ChevronForwardOutline v-if="entry.kind === 'directory'" class="chevron" :class="{ expanded }" />
      <component :is="expanded ? FolderOpenOutline : FolderOutline" v-if="entry.kind === 'directory'" class="kind folder" />
      <CodeFileTypeIcon v-else :path="entry.path" />
      <span>{{ entry.name }}</span><small v-if="loading">…</small>
    </button>
    <div v-if="expanded && children" class="children">
      <WorkspaceFileTreeNode v-for="child in children" :key="child.path" :session-id="sessionId" :entry="child" :selected-path="selectedPath" @select="emit('select', $event)" />
    </div>
  </div>
</template>

<style scoped>
button{display:flex;width:100%;height:32px;align-items:center;gap:5px;border:0;border-radius:7px;background:transparent;padding:0 7px;color:#475569;text-align:left;cursor:pointer}button:focus{outline:0}button:hover{background:#eef4ff;color:#1e40af}button.selected{background:#dbeafe;color:#1d4ed8}.children{margin-left:15px}.chevron{width:12px;height:12px;flex:none;transition:transform .15s ease}.chevron.expanded{transform:rotate(90deg)}.kind{width:16px;height:16px;flex:none;color:#64748b}.folder{color:#2563eb}span{min-width:0;flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-size:12px}small{color:#94a3b8}
</style>
