<script setup lang="ts">
// Separate artifact card group. Rendered by ChatWindow after the assistant
// text so deliverables appear below the answer, like Claude Code.

import { computed } from 'vue'
import type { ArtifactItem } from '../../features/execution-v3/domain/delivery'
import { visibleAnswerArtifacts } from '../../features/execution-v3/domain/artifactVisibility'
import { withoutCodeChangeArtifacts } from '../chat/codeChangeArtifacts'
import type { DshTaskChangeSet } from '../../platform/types'
import ArtifactRow from './ArtifactRow.vue'
import ImageArtifactCard from './ImageArtifactCard.vue'
import { isImageArtifact } from '../../features/execution-v3/domain/artifactKind'
import { inlineImageUrls, imageIsInline } from '../../features/execution-v3/domain/inlineImageArtifacts'

const props = defineProps<{ store: { state: { artifacts: ArtifactItem[]; runStatus: string } }; codeChanges?: DshTaskChangeSet; content?: string }>()
const inlineImages = computed(() => inlineImageUrls(props.content || ''))
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
    <template v-for="a in visibleArtifacts" :key="a.id">
      <ImageArtifactCard v-if="isImageArtifact(a)" :artifact="a" :compact="imageIsInline(a, inlineImages)" @download="emit('download', $event)" />
      <ArtifactRow v-else
        :artifact="a"
        @open="emit('open', $event)"
        @edit="emit('edit', $event)"
        @preview="emit('preview', $event)"
        @export="emit('export', $event)"
        @download="emit('download', $event)"
        @copy="emit('copy', $event)"
      />
    </template>
  </div>
</template>
