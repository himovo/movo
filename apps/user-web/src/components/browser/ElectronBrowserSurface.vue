<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue'
import ArrowBackOutline from '@vicons/ionicons5/es/ArrowBackOutline'
import ArrowForwardOutline from '@vicons/ionicons5/es/ArrowForwardOutline'
import CloseOutline from '@vicons/ionicons5/es/CloseOutline'
import PlayOutline from '@vicons/ionicons5/es/PlayOutline'
import ReloadOutline from '@vicons/ionicons5/es/ReloadOutline'
import {
  attachEmbeddedBrowserSurface,
  closeEmbeddedBrowserTab,
  createEmbeddedBrowserTab,
  hideEmbeddedBrowser,
  hideEmbeddedBrowserSurface,
  navigateEmbeddedBrowserHistory,
  onEmbeddedBrowserLayoutRequest,
  openEmbeddedBrowser,
  reloadEmbeddedBrowser,
  selectEmbeddedBrowserTab,
  setEmbeddedBrowserSurfaceBounds,
  setEmbeddedBrowserOwner,
  showEmbeddedBrowserSurface,
  type BrowserOwner,
} from '../../platform'
import { useEmbeddedBrowserState } from '../../composables/browser/embeddedBrowserState'
import { useLocale } from '../../composables/i18n'
import BrowserAddressBar from './BrowserAddressBar.vue'
import BrowserTabs from './BrowserTabs.vue'
import RecordingReviewDialog from './RecordingReviewDialog.vue'
import { notifyBrowserAgentReturned } from '../../composables/browser/browserAgentReturn'
import {
  type RecordingEvent,
  type RecordingAnalysis,
  type StreamHandle,
  analyzeRecording,
  saveRecordingToCache,
  startRecording,
  stopRecording,
  streamRecording,
} from '../../api/recording'

const emit = defineEmits<{ (event: 'close'): void }>()
const props = defineProps<{ sessionId?: string; userId?: string; mainId?: string; showPanelClose?: boolean }>()
const surface = ref<HTMLElement | null>(null)
const state = useEmbeddedBrowserState()
const { locale } = useLocale()
let observer: ResizeObserver | null = null
let stopLayoutRequests: (() => void) | null = null
let disposed = false
const surfaceId = `browser-surface-${Date.now()}-${Math.random().toString(36).slice(2)}`
const recording = ref(false)
const recordingId = ref('')
const recordedEvents = ref<RecordingEvent[]>([])
const showRecordingReview = ref(false)
const analyzingRecording = ref(false)
const recordingAnalysis = ref<RecordingAnalysis | null>(null)
const recordingAnalysisError = ref('')
const recordingMessage = ref('')
const savingRecording = ref(false)
let recordingStream: StreamHandle | null = null

async function beginRecording() {
  if (!props.userId || recording.value) return
  recordingMessage.value = ''
  recordedEvents.value = []
  recordingStream?.close()
  recordingStream = streamRecording(props.userId, (event) => {
    if (!recordingId.value || event.recording_id === recordingId.value) recordedEvents.value.push(event)
  }, () => { recordingMessage.value = locale.value === 'zh' ? '录制事件流已中断' : 'Recording stream interrupted' })
  try {
    const result = await startRecording(props.userId, '', state.value.session_id || props.sessionId || 'default')
    if (!result.ok) throw new Error(locale.value === 'zh' ? '本地浏览器 Agent 未连接' : 'Local browser agent is not connected')
    recordingId.value = result.recording_id
    recording.value = true
    showRecordingReview.value = false
    await setEmbeddedBrowserOwner('human')
  } catch (error) {
    recordingStream?.close()
    recordingStream = null
    recordingMessage.value = String((error as Error)?.message || error)
  }
}

async function finishRecording() {
  if (!props.userId || !recording.value) return
  await stopRecording(
    props.userId,
    state.value.session_id || props.sessionId || 'default',
    recordingId.value,
  ).catch(() => false)
  recording.value = false
  recordingStream?.close()
  recordingStream = null
  await suspendBrowserSurfaceForReview()
  showRecordingReview.value = true
  await refreshRecordingAnalysis()
}

async function refreshRecordingAnalysis() {
  if (!props.userId || !recordingId.value) return
  analyzingRecording.value = true
  recordingAnalysis.value = null
  recordingAnalysisError.value = ''
  await suspendBrowserSurfaceForReview()
  try {
    const result = await analyzeRecording({
      user_id: props.userId,
      recording_id: recordingId.value,
    })
    if (!result.ok || !result.analysis) throw new Error(result.reason || 'recording_analysis_failed')
    recordingAnalysis.value = result.analysis
  } catch (error) {
    recordingAnalysisError.value = String((error as Error)?.message || error)
  } finally {
    analyzingRecording.value = false
  }
}

async function persistRecording() {
  const analysis = recordingAnalysis.value
  if (!props.userId || !recordingId.value || !analysis?.complete) return
  savingRecording.value = true
  recordingMessage.value = ''
  try {
    const result = await saveRecordingToCache({
      user_id: props.userId,
      main_id: props.mainId || 'default',
      recording_id: recordingId.value,
      operation: analysis.operation,
      display_name: analysis.display_name,
      capability_id: analysis.capability_id,
    })
    if (!result.ok) throw new Error(result.reason || 'cache_rejected')
    recordingMessage.value = locale.value === 'zh' ? '流程已保存，下次会优先本地执行' : 'Workflow saved for local-first replay'
    showRecordingReview.value = false
    recordingAnalysis.value = null
    recordingId.value = ''
    recordedEvents.value = []
    await restoreBrowserSurface()
  } catch (error) {
    recordingMessage.value = locale.value === 'zh'
      ? `流程未保存：${String((error as Error)?.message || error)}`
      : `Workflow not saved: ${String((error as Error)?.message || error)}`
  } finally {
    savingRecording.value = false
  }
}

async function discardRecording() {
  showRecordingReview.value = false
  recordingId.value = ''
  recordedEvents.value = []
  recordingAnalysis.value = null
  recordingAnalysisError.value = ''
  recordingMessage.value = ''
  await restoreBrowserSurface()
}

async function restoreBrowserSurface() {
  if (disposed) return
  const sessionId = state.value.session_id || props.sessionId
  if (sessionId) await attachEmbeddedBrowserSurface(surfaceId, sessionId).catch(() => {})
  await syncBounds()
  await showEmbeddedBrowserSurface(surfaceId).catch(() => {})
}

async function suspendBrowserSurfaceForReview() {
  // A native WebContentsView is always composited above renderer DOM, so CSS
  // z-index cannot place the review dialog over it. Surface ownership may have
  // changed during task/tab transitions; the global hide is the safe fallback.
  await hideEmbeddedBrowserSurface(surfaceId).catch(() => {})
  await hideEmbeddedBrowser().catch(() => {})
}

async function syncBounds() {
  if (disposed) return
  const rect = surface.value?.getBoundingClientRect()
  if (!rect || rect.width <= 0 || rect.height <= 0) return
  await setEmbeddedBrowserSurfaceBounds(surfaceId, {
    x: rect.left,
    y: rect.top,
    width: rect.width,
    height: rect.height,
  })
}

async function setOwner(owner: BrowserOwner) {
  await setEmbeddedBrowserOwner(owner)
  if (owner === 'agent') notifyBrowserAgentReturned(state.value.session_id || '')
}

async function navigate(url: string) {
  await setEmbeddedBrowserOwner('human')
  await openEmbeddedBrowser(url, 'automation')
}

async function newTab() {
  await createEmbeddedBrowserTab()
}

async function selectTab(tabId: string) {
  await selectEmbeddedBrowserTab(tabId)
}

async function closeTab(tabId: string) {
  await closeEmbeddedBrowserTab(tabId)
}

function close() {
  void hideEmbeddedBrowserSurface(surfaceId)
  emit('close')
}

onMounted(async () => {
  disposed = false
  observer = new ResizeObserver(() => void syncBounds())
  stopLayoutRequests = onEmbeddedBrowserLayoutRequest(() => void syncBounds())
  if (surface.value) observer.observe(surface.value)
  window.addEventListener('resize', syncBounds)
  if (!props.sessionId) return
  try {
    await attachEmbeddedBrowserSurface(surfaceId, props.sessionId)
    if (disposed) return
    await syncBounds()
    if (disposed) return
    await showEmbeddedBrowserSurface(surfaceId)
  } catch (error) {
    console.warn('[electron-browser] surface activation failed', {
      sessionId: props.sessionId,
      error,
    })
    void hideEmbeddedBrowserSurface(surfaceId)
  }
})

onBeforeUnmount(() => {
  disposed = true
  observer?.disconnect()
  stopLayoutRequests?.()
  window.removeEventListener('resize', syncBounds)
  void hideEmbeddedBrowserSurface(surfaceId)
  recordingStream?.close()
  if (recording.value && props.userId) {
    void stopRecording(props.userId, state.value.session_id || props.sessionId || 'default', recordingId.value)
  }
})
</script>

<template>
  <section class="electron-browser">
    <BrowserTabs :tabs="state.tabs" :active-id="state.active_tab_id" @new="newTab" @select="selectTab" @close="closeTab">
      <template #actions>
        <span v-if="state.controllable" class="owner-label"><span class="status-dot" :class="{ loading: state.loading }"></span>{{ state.owner === 'human' ? (locale === 'zh' ? '人工' : 'Human') : 'Agent' }}</span>
        <button
          v-if="state.controllable && props.userId"
          class="record-command"
          :class="{ active: recording }"
          type="button"
          :disabled="savingRecording"
          :title="recording ? (locale === 'zh' ? '停止录制' : 'Stop recording') : (locale === 'zh' ? '录制人工流程' : 'Record manual workflow')"
          @click="recording ? finishRecording() : beginRecording()"
        ><span class="record-dot"></span>{{ recording ? (locale === 'zh' ? '停止' : 'Stop') : (locale === 'zh' ? '录制' : 'Record') }}</button>
        <button v-if="state.controllable && state.owner === 'human'" class="resume-command" type="button" :title="locale === 'zh' ? '交还 Agent 执行' : 'Resume agent'" @click="setOwner('agent')"><PlayOutline /></button>
        <button v-if="showPanelClose !== false" class="panel-close" type="button" :title="locale === 'zh' ? '关闭浏览器面板' : 'Close browser panel'" @click="close"><CloseOutline /></button>
      </template>
    </BrowserTabs>
    <header class="browser-toolbar">
      <div class="navigation-controls">
        <button class="icon-command" type="button" :disabled="!state.canGoBack" title="后退" @click="navigateEmbeddedBrowserHistory('back')"><ArrowBackOutline /></button>
        <button class="icon-command" type="button" :disabled="!state.canGoForward" title="前进" @click="navigateEmbeddedBrowserHistory('forward')"><ArrowForwardOutline /></button>
        <button class="icon-command" type="button" title="刷新" @click="reloadEmbeddedBrowser"><ReloadOutline /></button>
      </div>
      <div class="address-container">
        <BrowserAddressBar :url="state.url" @navigate="navigate" />
      </div>
    </header>
    <RecordingReviewDialog
      :show="showRecordingReview"
      :loading="analyzingRecording"
      :saving="savingRecording"
      :analysis="recordingAnalysis"
      :error="recordingAnalysisError"
      :locale="locale"
      @save="persistRecording"
      @discard="discardRecording"
      @retry="refreshRecordingAnalysis"
    />
    <div v-if="recordingMessage" class="recording-message" role="status">{{ recordingMessage }}</div>
    <div ref="surface" class="browser-surface"></div>
  </section>
</template>

<style scoped>
.electron-browser { display: flex; height: 100%; min-width: 0; flex-direction: column; background: white; color: #334155; container-type: inline-size; }
.browser-toolbar { display: flex; min-height: 48px; align-items: center; gap: 7px; border-bottom: 1px solid #e2e8f0; padding: 7px 9px; background: white; }
.navigation-controls { display: flex; gap: 4px; }
.address-container { min-width: 0; flex: 1; }
.status-dot { width: 7px; height: 7px; flex: none; border-radius: 50%; background: #22c55e; }
.status-dot.loading { background: #f59e0b; }
.owner-label { display: inline-flex; height: 26px; align-items: center; gap: 5px; border: 1px solid #e2e8f0; border-radius: 6px; padding: 0 7px; color: #64748b; font-size: 10px; }
.resume-command, .panel-close, .icon-command { display: inline-flex; width: 32px; height: 32px; flex: none; align-items: center; justify-content: center; border: 0; border-radius: 7px; background: transparent; padding: 0; color: #64748b; cursor: pointer; }
.record-command { display: inline-flex; min-height: 32px; align-items: center; gap: 5px; border: 1px solid #e2e8f0; border-radius: 7px; background: white; padding: 0 9px; color: #475569; font-size: 11px; cursor: pointer; }
.record-command:hover { border-color: #cbd5e1; background: #f8fafc; color: #0f172a; }
.record-command.active { border-color: #fecaca; background: #fef2f2; color: #b91c1c; }
.record-command:focus-visible { outline: 2px solid #93c5fd; outline-offset: 1px; }
.record-dot { width: 8px; height: 8px; border-radius: 50%; background: #ef4444; }
.record-command.active .record-dot { animation: recording-pulse 1.2s ease-in-out infinite; }
.record-command:disabled { cursor: default; opacity: .5; }
.recording-message { border-bottom: 1px solid #e2e8f0; background: #f8fafc; padding: 5px 10px; color: #475569; font-size: 11px; }
@keyframes recording-pulse { 50% { opacity: .35; } }
@media (prefers-reduced-motion: reduce) { .record-command.active .record-dot { animation: none; } }
.resume-command:hover, .panel-close:hover, .icon-command:hover { background: #f1f5f9; color: #0f172a; }
.resume-command:focus-visible, .panel-close:focus-visible, .icon-command:focus-visible { outline: 2px solid #bfdbfe; outline-offset: 1px; }
.resume-command svg, .panel-close svg, .icon-command svg { width: 17px; height: 17px; }
.icon-command:disabled { cursor: default; opacity: .35; }
.browser-surface { min-height: 0; flex: 1; background: white; }
@media (max-width: 620px) { .owner-label { display: none; } .navigation-controls { gap: 1px; } .browser-toolbar { padding-inline: 5px; } }
@container (max-width: 420px) { .owner-label { display: none; } }
</style>
