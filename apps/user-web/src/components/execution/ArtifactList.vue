<script setup lang="ts">
// Separate artifact card group. Rendered by ChatWindow after the assistant
// text so deliverables appear below the answer, like Claude Code.

import type { ArtifactItem } from '../../features/execution-v3/domain/delivery'
import ArtifactRow from './ArtifactRow.vue'

defineProps<{ store: { state: { artifacts: ArtifactItem[] } } }>()
const emit = defineEmits<{
  (e: 'open',     a: ArtifactItem): void
  (e: 'edit',     a: ArtifactItem): void
  (e: 'preview',  a: ArtifactItem): void
  (e: 'export',   a: ArtifactItem): void
  (e: 'download', a: ArtifactItem): void
  (e: 'copy',     a: ArtifactItem): void
}>()
</script>

<template>
  <div v-if="store.state.artifacts.length" class="space-y-2">
    <ArtifactRow
      v-for="a in store.state.artifacts"
      :key="a.id"
      :artifact="a"
      @open="emit('open', $event)"
      @edit="emit('edit', $event)"
      @preview="emit('preview', $event)"
      @export="emit('export', $event)"
      @download="emit('download', $event)"
      @copy="emit('copy', $event)"
    />
  </div>
</template>
