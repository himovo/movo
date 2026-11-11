<script setup lang="ts">
import type { PendingDocument } from './types'

interface PendingImage {
  file: File
  previewUrl: string
}

defineProps<{
  images: PendingImage[]
  documents: PendingDocument[]
  docIcon: (type: string) => string
}>()
const emit = defineEmits<{
  (e: 'image-preview', src: string, alt: string): void
  (e: 'remove-image', index: number): void
  (e: 'remove-document', index: number): void
  (e: 'document-preview', document: PendingDocument): void
}>()
</script>

<template>
  <div v-if="images.length" class="mb-2 flex flex-wrap gap-2">
    <div v-for="(item, index) in images" :key="`${item.file.name}-${index}`" class="relative">
      <img
        :src="item.previewUrl"
        :alt="item.file.name"
        class="h-16 w-24 cursor-zoom-in rounded-lg border border-gray-200 object-cover"
        @click="emit('image-preview', item.previewUrl, item.file.name)"
      />
      <button
        class="absolute -right-1 -top-1 h-5 w-5 rounded-full bg-black/70 text-xs text-white"
        @click="emit('remove-image', index)"
      >x</button>
    </div>
  </div>
  <div v-if="documents.length" class="mb-2 flex flex-wrap gap-2">
    <div
      v-for="(item, index) in documents"
      :key="`${item.file.name}-${index}`"
      class="relative flex cursor-pointer items-center gap-2 rounded-xl border border-gray-200 bg-white px-3 py-2 shadow-sm hover:bg-blue-50"
      role="button"
      tabindex="0"
      @click="emit('document-preview', item)"
      @keydown.enter.prevent="emit('document-preview', item)"
      @keydown.space.prevent="emit('document-preview', item)"
    >
      <img :src="docIcon(item.kind)" :alt="item.kind" class="h-8 w-8 object-contain" />
      <div class="max-w-[180px]">
        <div class="truncate text-sm font-medium text-slate-700">{{ item.file.name }}</div>
        <div class="text-xs text-slate-400">{{ item.kind.toUpperCase() }}</div>
      </div>
      <button
        type="button"
        class="absolute -right-1 -top-1 h-5 w-5 rounded-full bg-black/70 text-xs text-white"
        @click.stop="emit('remove-document', index)"
      >x</button>
    </div>
  </div>
</template>
