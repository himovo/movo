<script setup lang="ts">
import AddOutline from '@vicons/ionicons5/es/AddOutline'
import CloseOutline from '@vicons/ionicons5/es/CloseOutline'
import type { BrowserTabState } from '../../platform/types'
import { t } from '../../composables/i18n'

defineProps<{ tabs: readonly BrowserTabState[]; activeId: string }>()
const emit = defineEmits<{
  (event: 'new'): void
  (event: 'select', tabId: string): void
  (event: 'close', tabId: string): void
}>()

function label(tab: BrowserTabState): string {
  if (tab.title) return tab.title
  if (!tab.url || tab.url === 'about:blank') return t('新标签页')
  try { return new URL(tab.url).hostname || tab.url } catch { return tab.url }
}
</script>

<template>
  <div class="tab-strip">
    <div class="tab-scroll">
      <div
        v-for="tab in tabs"
        :key="tab.id"
        class="browser-tab"
        :class="{ active: tab.id === activeId }"
        role="tab"
        tabindex="0"
        :aria-selected="tab.id === activeId"
        @click="emit('select', tab.id)"
        @keydown.enter.prevent="emit('select', tab.id)"
        @keydown.space.prevent="emit('select', tab.id)"
      >
        <span class="tab-label">{{ label(tab) }}</span>
        <button
          class="tab-close"
          type="button"
          :aria-label="t('关闭标签页')"
          @click.stop="emit('close', tab.id)"
        ><CloseOutline /></button>
      </div>
    </div>
    <button class="new-tab" type="button" :title="t('新建标签页')" @click="emit('new')"><AddOutline /></button>
    <span class="tab-spacer"></span>
    <div class="tab-actions"><slot name="actions" /></div>
  </div>
</template>

<style scoped>
.tab-strip { display: flex; height: 42px; min-width: 0; align-items: center; border-bottom: 1px solid #e2e8f0; background: #f8fafc; padding: 5px 7px 0; }
.tab-scroll { display: flex; min-width: 0; flex: 0 1 auto; align-self: stretch; align-items: center; gap: 3px; overflow-x: auto; scrollbar-width: none; }
.tab-scroll::-webkit-scrollbar { display: none; }
.browser-tab { display: flex; width: 150px; min-width: 88px; max-width: 180px; height: 32px; flex: none; align-items: center; gap: 5px; border-radius: 7px 7px 0 0; outline: none; background: transparent; padding: 0 6px 0 10px; color: #64748b; cursor: pointer; }
.browser-tab:hover { background: #f1f5f9; color: #334155; }
.browser-tab.active { background: white; color: #0f172a; box-shadow: inset 0 0 0 1px #e2e8f0; }
.browser-tab:focus-visible { box-shadow: inset 0 0 0 2px #93c5fd; }
.tab-label { min-width: 0; flex: 1; overflow: hidden; text-align: left; text-overflow: ellipsis; white-space: nowrap; font-size: 11px; }
.tab-close, .new-tab { display: inline-flex; width: 26px; height: 26px; flex: none; align-items: center; justify-content: center; border: 0; border-radius: 5px; background: transparent; color: inherit; cursor: pointer; }
.tab-close svg, .new-tab svg { width: 14px; height: 14px; }
.tab-close:hover, .new-tab:hover { background: #e2e8f0; color: #0f172a; }
.new-tab { color: #64748b; }
.tab-spacer { min-width: 0; flex: 1; }
.tab-actions { display: flex; flex: none; align-items: center; gap: 5px; padding: 0 1px 5px 8px; }
</style>
