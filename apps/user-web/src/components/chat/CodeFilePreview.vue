<script setup lang="ts">
import { computed } from 'vue'
import { highlightCode, syntaxLanguage } from '../code/codeSyntax'

const props = defineProps<{ content: string; filename: string }>()
const lines = computed(() => props.content.split('\n'))
const language = computed(() => syntaxLanguage(props.filename) || 'text')
const highlighted = computed(() => lines.value.map(line => highlightCode(line || ' ', props.filename)))
</script>

<template>
  <div class="min-w-max bg-white font-mono text-[13px] leading-6" role="region" :aria-label="filename">
    <div class="sticky top-0 z-10 border-b border-slate-200 bg-slate-50 px-4 py-1 text-xs text-slate-500">{{ language }}</div>
    <div v-for="(line, index) in highlighted" :key="index" class="flex hover:bg-slate-50">
      <span class="sticky left-0 w-14 shrink-0 select-none border-r border-slate-100 bg-white pr-3 text-right text-slate-400">{{ index + 1 }}</span>
      <code class="block flex-1 whitespace-pre px-4 text-slate-800" v-html="line" />
    </div>
  </div>
</template>
