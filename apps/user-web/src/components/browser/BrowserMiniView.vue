<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { captureEmbeddedBrowserPreview, type BrowserOwner, type BrowserPreviewFrame } from '../../platform'

const props = defineProps<{
  sessionId: string
  active: boolean
  title?: string
  url?: string
  loading?: boolean
  owner?: BrowserOwner
  locale?: 'zh' | 'en'
}>()
const emit = defineEmits<{
  (event: 'expand'): void
  (event: 'close'): void
}>()

const frame = ref<BrowserPreviewFrame | null>(null)
const failed = ref(false)
let timer: ReturnType<typeof setTimeout> | null = null
let requestVersion = 0

const zh = computed(() => props.locale !== 'en')
const displayTitle = computed(() => frame.value?.title || props.title || (zh.value ? '浏览器任务' : 'Browser task'))
const ownerLabel = computed(() => props.owner === 'human'
  ? (zh.value ? '人工操作中' : 'Human in control')
  : (zh.value ? 'Agent 操作中' : 'Agent working'))

function stopPolling() {
  requestVersion += 1
  if (timer) clearTimeout(timer)
  timer = null
}

function schedule(version: number) {
  if (!props.active || version !== requestVersion) return
  timer = setTimeout(() => void capture(version), 1_000)
}

async function capture(version: number) {
  if (!props.active || version !== requestVersion) return
  try {
    const next = await captureEmbeddedBrowserPreview(props.sessionId)
    if (version !== requestVersion) return
    if (next) frame.value = next
    failed.value = !next && !frame.value
  } catch {
    if (version === requestVersion) failed.value = !frame.value
  } finally {
    schedule(version)
  }
}

function startPolling() {
  stopPolling()
  failed.value = false
  const version = requestVersion
  void capture(version)
}

watch(() => [props.active, props.sessionId] as const, ([active], previous) => {
  const previousSession = previous?.[1]
  if (previousSession && previousSession !== props.sessionId) frame.value = null
  if (active) startPolling()
  else stopPolling()
}, { immediate: true })

onBeforeUnmount(stopPolling)
</script>

<template>
  <aside class="browser-mini" :aria-label="zh ? '浏览器实时画面' : 'Live browser preview'">
    <header class="browser-mini__header">
      <div class="browser-mini__identity">
        <span class="browser-mini__status" :class="{ loading }" aria-hidden="true"></span>
        <div class="browser-mini__heading">
          <strong>{{ displayTitle }}</strong>
          <span>{{ ownerLabel }}</span>
        </div>
      </div>
      <div class="browser-mini__actions">
        <button
          type="button"
          :aria-label="zh ? '展开浏览器侧栏' : 'Open browser side panel'"
          :title="zh ? '展开' : 'Expand'"
          @click="emit('expand')"
        >
          <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M8 3H3v5M16 3h5v5M8 21H3v-5m13 5h5v-5M3 8l6-6m6 0 6 6M3 16l6 6m6 0 6-6" /></svg>
        </button>
        <button
          type="button"
          :aria-label="zh ? '关闭浏览器画中画' : 'Close browser preview'"
          :title="zh ? '关闭' : 'Close'"
          @click="emit('close')"
        >
          <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 6l12 12M18 6 6 18" /></svg>
        </button>
      </div>
    </header>
    <button
      class="browser-mini__stage"
      type="button"
      :aria-label="zh ? '双击展开浏览器侧栏' : 'Double-click to open browser side panel'"
      @dblclick="emit('expand')"
    >
      <img v-if="frame" :src="frame.data_url" :alt="displayTitle" draggable="false" />
      <span v-else class="browser-mini__placeholder">
        <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 5h16v12H4zM8 21h8M12 17v4" /></svg>
        {{ failed ? (zh ? '暂时无法获取画面' : 'Preview unavailable') : (zh ? '正在获取浏览器画面…' : 'Loading browser preview…') }}
      </span>
      <span class="browser-mini__hint">{{ zh ? '双击展开' : 'Double-click to expand' }}</span>
    </button>
  </aside>
</template>

<style scoped>
.browser-mini {
  position: absolute;
  right: 24px;
  bottom: 104px;
  z-index: 24;
  width: min(352px, calc(100% - 48px));
  overflow: hidden;
  border: 1px solid rgba(148, 163, 184, .52);
  border-radius: 14px;
  background: #fff;
  box-shadow: 0 18px 44px rgba(15, 23, 42, .2), 0 3px 10px rgba(15, 23, 42, .1);
}
.browser-mini__header { display: flex; min-height: 52px; align-items: center; justify-content: space-between; gap: 8px; padding: 4px 4px 4px 14px; border-bottom: 1px solid #e2e8f0; }
.browser-mini__identity { display: flex; min-width: 0; align-items: center; gap: 9px; }
.browser-mini__status { width: 8px; height: 8px; flex: none; border-radius: 50%; background: #22c55e; box-shadow: 0 0 0 3px #dcfce7; }
.browser-mini__status.loading { animation: browser-mini-pulse 1.3s ease-in-out infinite; }
.browser-mini__heading { min-width: 0; line-height: 1.2; }
.browser-mini__heading strong, .browser-mini__heading span { display: block; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.browser-mini__heading strong { max-width: 205px; color: #0f172a; font-size: 13px; font-weight: 650; }
.browser-mini__heading span { margin-top: 3px; color: #64748b; font-size: 11px; }
.browser-mini__actions { display: flex; flex: none; }
.browser-mini__actions button { display: grid; width: 44px; height: 44px; place-items: center; border: 0; border-radius: 9px; color: #64748b; background: transparent; cursor: pointer; }
.browser-mini__actions button:hover { color: #0f172a; background: #f1f5f9; }
.browser-mini__actions button:focus-visible, .browser-mini__stage:focus-visible { outline: 2px solid #2563eb; outline-offset: -2px; }
.browser-mini__actions svg { width: 18px; height: 18px; fill: none; stroke: currentColor; stroke-width: 1.8; stroke-linecap: round; stroke-linejoin: round; }
.browser-mini__stage { position: relative; display: block; width: 100%; aspect-ratio: 16 / 10; padding: 0; overflow: hidden; border: 0; background: #0f172a; cursor: zoom-in; }
.browser-mini__stage img { display: block; width: 100%; height: 100%; object-fit: cover; object-position: top center; user-select: none; }
.browser-mini__placeholder { display: flex; height: 100%; align-items: center; justify-content: center; gap: 8px; color: #cbd5e1; font-size: 12px; }
.browser-mini__placeholder svg { width: 20px; height: 20px; fill: none; stroke: currentColor; stroke-width: 1.6; stroke-linecap: round; stroke-linejoin: round; }
.browser-mini__hint { position: absolute; right: 9px; bottom: 9px; padding: 4px 7px; border-radius: 6px; color: #fff; background: rgba(15, 23, 42, .72); font-size: 10px; opacity: 0; transition: opacity .16s ease; }
.browser-mini__stage:hover .browser-mini__hint, .browser-mini__stage:focus-visible .browser-mini__hint { opacity: 1; }
@keyframes browser-mini-pulse { 50% { opacity: .35; } }
@media (max-width: 700px) {
  .browser-mini { right: 12px; bottom: 88px; width: min(320px, calc(100% - 24px)); }
}
@media (prefers-reduced-motion: reduce) {
  .browser-mini__status.loading { animation: none; }
  .browser-mini__hint { transition: none; }
}
</style>
