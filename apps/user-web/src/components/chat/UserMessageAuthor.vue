<script setup lang="ts">
import { computed } from 'vue'
import { resolveAuthorPresentation } from './userMessageAuthor'

// T9 shared-session author strip: avatar (image or deterministic initials) plus
// display name above a user-authored row. This component is a thin delegation to
// the pure `resolveAuthorPresentation` helper — all branching on avatar safety
// and initials lives there, so the headless suite can assert it without a DOM.
const props = defineProps<{
  displayName: string | null
  avatarUrl: string | null
}>()

const presentation = computed(() =>
  resolveAuthorPresentation({ display_name: props.displayName, avatar_url: props.avatarUrl }),
)
const image = computed(() => (presentation.value.kind === 'image' ? presentation.value : null))
const initials = computed(() => (presentation.value.kind === 'initials' ? presentation.value : null))
const label = computed(() => (props.displayName ?? '').trim())
</script>

<template>
  <div class="flex min-w-0 items-center gap-2" data-user-message-author>
    <img
      v-if="image"
      :src="image.src"
      :alt="image.alt"
      class="h-6 w-6 shrink-0 rounded-full border border-slate-200 object-cover"
      loading="lazy"
    />
    <span
      v-else-if="initials"
      class="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-slate-200 text-[11px] font-semibold text-slate-600"
      role="img"
      :aria-label="initials.ariaLabel"
    >{{ initials.text }}</span>
    <span v-if="label" class="max-w-[12rem] truncate text-xs font-medium text-slate-500">{{ label }}</span>
  </div>
</template>
