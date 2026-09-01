<script setup lang="ts">
import { computed } from 'vue'
import { resolveArtifactPresentation } from '../../registries'
import { t } from '../../composables/i18n'
import type { ArtifactItem } from '../../features/execution-v3/domain/delivery'

const props = defineProps<{ artifact: ArtifactItem }>()
const emit = defineEmits<{
  (e: 'open',     a: ArtifactItem): void
  (e: 'edit',     a: ArtifactItem): void
  (e: 'preview',  a: ArtifactItem): void
  (e: 'export',   a: ArtifactItem): void
  (e: 'download', a: ArtifactItem): void
  (e: 'copy',     a: ArtifactItem): void
}>()

const desc = computed(() => resolveArtifactPresentation(props.artifact))
const title = computed(() => props.artifact.title || props.artifact.filename || t(desc.value.labelKey))
const subtitle = computed(() => props.artifact.filename || t(desc.value.labelKey))
const has = (action: string) => desc.value.actions.includes(action as any)
</script>

<template>
  <div
    class="flex items-center gap-3 rounded-2xl border border-slate-200 bg-white px-4 py-3 shadow-sm hover:shadow-md transition cursor-pointer"
    @click="emit('open', artifact)"
  >
    <div class="h-10 w-10 rounded-xl bg-slate-50 flex items-center justify-center">
      <img :src="desc.icon" :alt="t(desc.labelKey)" class="h-8 w-8 object-contain" loading="lazy" />
    </div>
    <div class="flex-1 min-w-0">
      <div class="text-sm font-semibold text-slate-800 truncate">{{ title }}</div>
      <div class="text-xs text-slate-400 truncate">{{ subtitle }}</div>
    </div>
    <button v-if="has('edit')"     type="button" class="min-h-11 px-2 text-xs text-blue-600 hover:text-blue-700 font-medium focus-visible:outline focus-visible:outline-2 focus-visible:outline-blue-500" @click.stop="emit('edit', artifact)">{{ t('ui.edit') }}</button>
    <button v-if="has('preview')"  type="button" class="min-h-11 px-2 text-xs text-slate-600 hover:text-slate-800 font-medium focus-visible:outline focus-visible:outline-2 focus-visible:outline-blue-500" @click.stop="emit('preview', artifact)">{{ t('ui.preview') }}</button>
    <button v-if="has('export')"   type="button" class="min-h-11 px-2 text-xs text-emerald-700 hover:text-emerald-800 font-medium focus-visible:outline focus-visible:outline-2 focus-visible:outline-blue-500" @click.stop="emit('export', artifact)">{{ t('ui.export') }}</button>
    <button v-if="has('download')" type="button" class="min-h-11 px-2 text-xs text-blue-600 hover:text-blue-700 font-medium focus-visible:outline focus-visible:outline-2 focus-visible:outline-blue-500" @click.stop="emit('download', artifact)">{{ t('ui.download') }}</button>
    <button v-if="has('copy')"     type="button" class="min-h-11 px-2 text-xs text-slate-600 hover:text-slate-800 font-medium focus-visible:outline focus-visible:outline-2 focus-visible:outline-blue-500" @click.stop="emit('copy', artifact)">{{ t('ui.copy') }}</button>
  </div>
</template>
