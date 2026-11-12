<script setup lang="ts">
// Separate artifact card group. Rendered by ChatWindow after the assistant
// text so deliverables appear below the answer, like Claude Code.

import { computed } from 'vue'
import type { ArtifactItem } from '../../features/execution-v3/domain/delivery'
import { visibleAnswerArtifacts } from '../../features/execution-v3/domain/artifactVisibility'
import { withoutCodeChangeArtifacts } from '../chat/codeChangeArtifacts'
import type { DshTaskChangeSet } from '../../platform/types'
import ArtifactRow from './ArtifactRow.vue'

const props = defineProps<{ store: { state: { artifacts: ArtifactItem[]; runStatus: string } }; codeChanges?: DshTaskChangeSet }>()
const visibleArtifacts = computed(() => withoutCodeChangeArtifacts(visibleAnswerArtifacts(
  props.store.state.artifacts, props.store.state.runStatus,
), props.codeChanges))
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
  <div v-if="visibleArtifacts.length" class="space-y-2">
    <ArtifactRow
      v-for="a in visibleArtifacts"
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
