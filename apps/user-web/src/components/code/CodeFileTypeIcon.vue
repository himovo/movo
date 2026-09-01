<script setup lang="ts">
import { computed } from 'vue'
import CodeOutline from '@vicons/ionicons5/es/CodeOutline'
import DocumentOutline from '@vicons/ionicons5/es/DocumentOutline'
import LogoCss3 from '@vicons/ionicons5/es/LogoCss3'
import LogoHtml5 from '@vicons/ionicons5/es/LogoHtml5'
import LogoJavascript from '@vicons/ionicons5/es/LogoJavascript'
import LogoMarkdown from '@vicons/ionicons5/es/LogoMarkdown'
import LogoNodejs from '@vicons/ionicons5/es/LogoNodejs'
import LogoPython from '@vicons/ionicons5/es/LogoPython'
import LogoVue from '@vicons/ionicons5/es/LogoVue'
import { fileTypePresentation } from './changePresentation'

const props = defineProps<{ path: string }>()
const type = computed(() => fileTypePresentation(props.path))
const icon = computed(() => ({
  javascript: LogoJavascript,
  python: LogoPython,
  vue: LogoVue,
  web: LogoHtml5,
  style: LogoCss3,
  markdown: LogoMarkdown,
  shell: LogoNodejs,
  native: CodeOutline,
}[type.value.tone]))
</script>

<template>
  <span class="file-type" :class="`tone-${type.tone}`" :title="type.name" :aria-label="type.name"><component :is="icon" v-if="icon" /><DocumentOutline v-else-if="type.tone === 'generic'" /><template v-else>{{ type.label }}</template></span>
</template>

<style scoped>
.file-type{display:grid;width:20px;height:20px;flex:none;place-items:center;border-radius:4px;font:800 8px/1 ui-monospace,SFMono-Regular,Menlo,monospace;letter-spacing:-.07em}.file-type svg{width:15px;height:15px}.tone-typescript{background:#e6f0ff;color:#2763bb}.tone-javascript{background:#fff4c9;color:#806000}.tone-python{background:#e8f4ff;color:#276e9f}.tone-vue{background:#e6f7ef;color:#17855e}.tone-json{background:#edf1f5;color:#586779}.tone-web{background:#fff0e8;color:#bd5424}.tone-style{background:#f2eaff;color:#7145b6}.tone-markdown{background:#e9edf2;color:#405166}.tone-config{background:#edf1f5;color:#586779}.tone-shell{background:#e6f6e9;color:#257a3f}.tone-database{background:#e3f7fa;color:#127a93}.tone-native{background:#fff0e8;color:#a64f21}.tone-generic{color:#8290a3}
</style>
