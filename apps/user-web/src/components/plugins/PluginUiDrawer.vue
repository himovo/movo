<template>
  <n-drawer :show="show" placement="right" :width="'min(96vw, 1360px)'" @update:show="emit('update:show', $event)">
    <n-drawer-content :title="name" closable body-content-style="padding: 0; overflow: hidden;">
      <iframe v-if="show && url" class="plugin-frame" :src="url" :title="name"
        ref="pluginFrame"
        sandbox="allow-scripts allow-same-origin allow-forms allow-downloads"
        referrerpolicy="no-referrer" />
    </n-drawer-content>
  </n-drawer>
</template>

<script setup lang="ts">
import { NDrawer, NDrawerContent } from 'naive-ui'
import { onMounted, onUnmounted, ref } from 'vue'

const props = defineProps<{ show: boolean; name: string; url: string }>()
const emit = defineEmits<{ 'update:show': [value: boolean]; openSession: [sessionId: string] }>()
const pluginFrame = ref<HTMLIFrameElement | null>(null)

function onPluginMessage(event: MessageEvent) {
  if (!props.show || !props.url || event.source !== pluginFrame.value?.contentWindow) return
  if (event.origin !== new URL(props.url).origin) return
  if (event.data?.type !== 'movo:plugin-open-session') return
  const sessionId = event.data.sessionId
  if (typeof sessionId !== 'string' || !sessionId || sessionId.length > 256 || /[\u0000-\u001f\u007f]/.test(sessionId)) return
  emit('openSession', sessionId)
}

onMounted(() => window.addEventListener('message', onPluginMessage))
onUnmounted(() => window.removeEventListener('message', onPluginMessage))
</script>

<style scoped>
.plugin-frame { display: block; width: 100%; height: 100%; min-height: calc(100vh - 64px); border: 0; background: #fff; }
</style>
