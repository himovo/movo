<script setup lang="ts">
import { ref } from 'vue'
import ChevronForwardOutline from '@vicons/ionicons5/es/ChevronForwardOutline'
import FolderOpenOutline from '@vicons/ionicons5/es/FolderOpenOutline'
import CodeFileTypeIcon from './CodeFileTypeIcon.vue'
import { changeStatusPresentation } from './changePresentation'
import type { WorkspaceChangeNode } from './changeTree'

defineOptions({ name: 'WorkspaceChangeTreeNode' })
const props = defineProps<{ node: WorkspaceChangeNode; selectedPath?: string; locale?: 'zh' | 'en' }>()
const emit = defineEmits<{ (event: 'select', path: string): void }>()
const expanded = ref(true)
const status = (value: string) => changeStatusPresentation(value, props.locale)
</script>

<template>
  <div>
    <button type="button" :class="{ selected: selectedPath === node.path }" @click="node.kind === 'directory' ? (expanded = !expanded) : emit('select', node.path)">
      <ChevronForwardOutline v-if="node.kind === 'directory'" class="chevron" :class="{ expanded }" />
      <FolderOpenOutline v-if="node.kind === 'directory'" class="kind folder" />
      <CodeFileTypeIcon v-else :path="node.path" />
      <span class="name">{{ node.name }}</span>
      <template v-if="node.change">
        <small class="status" :class="`tone-${status(node.change.status).tone}`" :title="status(node.change.status).description">{{ status(node.change.status).label }}</small>
        <small v-if="node.change.binary" class="binary">BIN</small>
        <small v-else-if="(node.change.additions || 0) > 0 || (node.change.deletions || 0) > 0" class="counts"><b v-if="(node.change.additions || 0) > 0">+{{ node.change.additions }}</b><i v-if="(node.change.deletions || 0) > 0">-{{ node.change.deletions }}</i></small>
      </template>
    </button>
    <div v-if="expanded" class="children"><WorkspaceChangeTreeNode v-for="child in node.children" :key="child.path" :node="child" :selected-path="selectedPath" :locale="locale" @select="emit('select', $event)" /></div>
  </div>
</template>

<style scoped>
button{display:flex;width:100%;min-height:34px;align-items:center;gap:5px;border:0;border-radius:8px;background:transparent;padding:4px 7px;color:#475569;text-align:left;cursor:pointer;transition:background-color .15s,color .15s}button:focus{outline:0}button:hover{background:#f1f5f9;color:#1e293b}button.selected{background:#e8f0ff;color:#1d4ed8}.children{margin-left:15px}.chevron{width:11px;height:11px;flex:none;transition:transform .15s}.chevron.expanded{transform:rotate(90deg)}.kind{width:17px;height:17px;flex:none;color:#64748b}.folder{color:#3b82f6}.name{min-width:0;flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-size:12px}.status{padding:1px 2px;color:#64748b;font:700 10px ui-monospace,SFMono-Regular,Menlo,monospace}.status.tone-added{color:#15803d}.status.tone-modified{color:#9a6700}.status.tone-deleted,.status.tone-conflict{color:#c2413b}.status.tone-renamed{color:#6d5bd0}.counts{display:flex;gap:4px;font-variant-numeric:tabular-nums}.binary{color:#64748b}small{flex:none;font-size:9px}small b{color:#15803d}small i{color:#dc2626;font-style:normal}
</style>
