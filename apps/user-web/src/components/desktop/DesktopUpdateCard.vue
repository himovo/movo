<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { NAlert, NButton, NCard, NProgress, NSpace, NTag } from 'naive-ui'
import {
  checkDesktopUpdate,
  downloadDesktopUpdate,
  getDesktopUpdateState,
  installDesktopUpdate,
  onDesktopUpdateState,
  type DesktopUpdateState,
} from '../../platform'
import { t } from '../../composables/i18n'

const state = ref<DesktopUpdateState>({ phase: 'idle', current_version: '' })
let stopListening: (() => void) | undefined

const busy = computed(() => ['checking', 'downloading', 'installing'].includes(state.value.phase))
const progress = computed(() => Math.max(0, Math.min(100, state.value.progress_percent || 0)))
const progressLabel = computed(() => Math.round(progress.value))
const statusText = computed(() => t(`settings.update.phase.${state.value.phase}`))

onMounted(async () => {
  state.value = await getDesktopUpdateState()
  stopListening = onDesktopUpdateState(next => { state.value = next })
})
onBeforeUnmount(() => stopListening?.())

async function check() { state.value = await checkDesktopUpdate() }
async function download() { state.value = await downloadDesktopUpdate() }
async function install() { await installDesktopUpdate() }
</script>

<template>
  <n-card :title="t('settings.update.title')" :bordered="false" size="small" class="!rounded-xl">
    <n-space vertical :size="14">
      <div class="flex flex-wrap items-center gap-2 text-xs text-slate-500">
        <n-tag size="small" :bordered="false">v{{ state.current_version }}</n-tag>
        <span>{{ statusText }}</span>
        <span v-if="state.available_version">· v{{ state.available_version }}</span>
      </div>

      <div v-if="state.phase === 'downloading'" class="space-y-2">
        <div class="flex items-center justify-end text-xs font-medium tabular-nums text-slate-600">
          {{ progressLabel }}%
        </div>
        <n-progress
          type="line"
          :percentage="progress"
          :show-indicator="false"
          :height="8"
          processing
        />
      </div>

      <n-alert v-if="state.phase === 'error' && state.message" type="error" :show-icon="true">
        {{ state.message }}
      </n-alert>
      <n-alert v-else-if="state.phase === 'downloaded'" type="success" :show-icon="true">
        {{ t('settings.update.ready_help') }}
      </n-alert>

      <n-space :size="8">
        <n-button
          v-if="state.phase !== 'available' && state.phase !== 'downloaded'"
          size="small"
          :loading="state.phase === 'checking'"
          :disabled="busy || state.phase === 'disabled'"
          @click="check"
        >
          {{ t('settings.update.check') }}
        </n-button>
        <n-button v-if="state.phase === 'available'" size="small" type="primary" @click="download">
          {{ t('settings.update.download') }}
        </n-button>
        <n-button
          v-if="state.phase === 'downloaded' || state.phase === 'installing'"
          size="small"
          type="primary"
          :loading="state.phase === 'installing'"
          :disabled="state.phase === 'installing'"
          @click="install"
        >
          {{ t('settings.update.restart') }}
        </n-button>
      </n-space>
    </n-space>
  </n-card>
</template>
