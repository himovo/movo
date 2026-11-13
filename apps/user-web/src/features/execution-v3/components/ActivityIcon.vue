<script setup lang="ts">
import { computed, type Component } from 'vue'
import { NIcon } from 'naive-ui'
import {
  AlertCircleOutline,
  BulbOutline,
  BuildOutline,
  ConstructOutline,
  DocumentOutline,
  GlobeOutline,
  LockClosedOutline,
  PeopleOutline,
  PencilOutline,
  SearchOutline,
  ShieldCheckmarkOutline,
  SparklesOutline,
  TerminalOutline,
} from '@vicons/ionicons5'

const props = defineProps<{ category?: string; kind?: string }>()

const icons: Record<string, Component> = {
  analyze: BulbOutline,
  search: SearchOutline,
  read: DocumentOutline,
  browser: GlobeOutline,
  browse: GlobeOutline,
  write: PencilOutline,
  render: DocumentOutline,
  document: DocumentOutline,
  quality: ShieldCheckmarkOutline,
  verify: ShieldCheckmarkOutline,
  repair: ConstructOutline,
  visual: SparklesOutline,
  skill: SparklesOutline,
  tool: BuildOutline,
  'execution.v3.activity.read_files': DocumentOutline,
  'execution.v3.activity.edit_files': PencilOutline,
  'execution.v3.activity.run_commands': TerminalOutline,
  'execution.v3.activity.search_code': SearchOutline,
  'execution.v3.activity.use_browser': GlobeOutline,
  'execution.v3.activity.search_web': GlobeOutline,
  'execution.v3.activity.install_skill': SparklesOutline,
  'execution.v3.activity.update_plan': DocumentOutline,
  subagent: PeopleOutline,
  approval: LockClosedOutline,
  warning: AlertCircleOutline,
  error: AlertCircleOutline,
  browser_handoff: LockClosedOutline,
}

const icon = computed(() => icons[String(props.category || props.kind || 'tool')] || BuildOutline)
</script>

<template>
  <NIcon class="activity-icon" :component="icon" aria-hidden="true" />
</template>

<style scoped>
.activity-icon { width:18px; height:18px; font-size:18px; }
</style>
