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
  tool: BuildOutline,
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
