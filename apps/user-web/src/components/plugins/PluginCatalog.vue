<template>
  <n-card class="list-card" :bordered="false" size="large">
    <div class="list-heading-row"><span class="list-heading">{{ t('plugins.listTitle') }}</span></div>
    <div class="list-filter-row">
      <div class="filter-toolbar">
        <n-space align="center" :size="10" class="filter-left">
          <n-input v-model:value="keyword" clearable :placeholder="t('plugins.search')" class="keyword-input" />
          <n-select v-model:value="scope" :options="scopeOptions" class="scope-select" />
        </n-space>
        <n-space :size="10" class="filter-right">
          <n-button secondary @click="emit('reload')">
            <template #icon><svg viewBox="0 0 24 24"><path d="M21 12a9 9 0 0 0-9-9 9.75 9.75 0 0 0-6.74 2.74L3 8M3 3v5h5M3 12a9 9 0 0 0 9 9 9.75 9.75 0 0 0 6.74-2.74L21 16M16 16h5v5" /></svg></template>
            {{ t('ui.refresh') }}
          </n-button>
          <n-button type="primary" strong :disabled="!executionAllowed" @click="emit('add')">
            <template #icon><svg viewBox="0 0 24 24"><path d="M5 12h14M12 5v14" /></svg></template>
            {{ t('plugins.add') }}
          </n-button>
        </n-space>
      </div>
    </div>
    <div class="list-body">
      <n-spin :show="loading">
        <div v-if="filtered.length" class="plugin-grid">
          <article v-for="plugin in filtered" :key="plugin.id" class="plugin-card" :class="{ 'plugin-card-disabled': !plugin.enabled }">
            <div class="card-head">
              <div class="card-tags">
                <n-tag size="small" :bordered="false" type="info">{{ t('plugins.dsh') }}</n-tag>
                <span class="card-version">v{{ plugin.version }}</span>
              </div>
              <span v-if="plugin.updatedAt" class="card-time">{{ formatAppDateTime(plugin.updatedAt) }}</span>
            </div>
            <div class="card-title">{{ plugin.name }}</div>
            <n-tooltip trigger="hover" :delay="350"><template #trigger><div class="card-desc">{{ plugin.description || plugin.spec }}</div></template>{{ plugin.description || plugin.spec }}</n-tooltip>
            <PluginAvailability :availability="plugin.availability" :busy="verifyBusyId === plugin.id" :can-verify="plugin.scope === 'personal' && executionAllowed" :card-status="pluginCardStatus(plugin, executionAllowed)" :conversation-available="plugin.enabled && executionAllowed && pluginConversationAvailable(plugin)" :execution-allowed="executionAllowed" @verify="emit('verify', plugin)" />
            <div class="card-footrow">
              <span class="card-scope"><n-icon :component="plugin.scope === 'organization' ? BusinessOutline : PersonOutline" />{{ t(plugin.scope === 'organization' ? 'plugins.enterprise' : 'plugins.mine') }}</span>
              <div class="card-actions">
                <n-button v-if="canOpenUi(plugin)" size="small" quaternary circle :type="shortcutIds.includes(plugin.id) ? 'primary' : 'default'" :title="t(shortcutIds.includes(plugin.id) ? 'plugins.removeShortcut' : 'plugins.addShortcut')" :aria-label="t(shortcutIds.includes(plugin.id) ? 'plugins.removeShortcut' : 'plugins.addShortcut')" :aria-pressed="shortcutIds.includes(plugin.id)" @click="emit('toggleShortcut', plugin)"><n-icon :component="shortcutIds.includes(plugin.id) ? Bookmark : BookmarkOutline" /></n-button>
                <n-button v-if="canOpenUi(plugin)" size="small" secondary type="primary" :loading="uiOpeningId === plugin.id" :disabled="Boolean(verifyBusyId || toggleBusyId || uiOpeningId)" @click="emit('openUi', plugin)"><template #icon><n-icon :component="DesktopOutline" /></template>{{ t('plugins.openUi') }}</n-button>
                <n-switch v-if="plugin.scope === 'personal'" size="small" :value="plugin.enabled" :loading="toggleBusyId === plugin.id" :aria-label="t(plugin.enabled ? 'plugins.enabled' : 'plugins.disabled')" :disabled="Boolean(verifyBusyId || toggleBusyId) || (!executionAllowed && !plugin.enabled) || (!plugin.enabled && !['session_exposed', 'runtime_active', 'verified'].includes(plugin.availability?.status || ''))" @update:value="enabled => emit('toggle', plugin, enabled)" />
                <n-popover v-if="plugin.scope === 'personal'" trigger="click" placement="bottom-end">
                  <template #trigger><n-button size="small" quaternary circle :title="t('plugins.moreActions')" :aria-label="t('plugins.moreActions')"><n-icon :component="EllipsisHorizontal" /></n-button></template>
                  <n-popconfirm @positive-click="emit('remove', plugin)">
                    <template #trigger><n-button size="small" text type="error">{{ t('plugins.remove') }}</n-button></template>
                    {{ t('plugins.confirmRemove') }}
                  </n-popconfirm>
                </n-popover>
              </div>
            </div>
          </article>
        </div>
        <div v-else class="empty-shell">
          <div class="empty-visual">DSH</div>
          <div class="empty-title">{{ t(plugins.length ? 'plugins.noMatches' : 'plugins.empty') }}</div>
          <div class="empty-desc">{{ t(plugins.length ? 'plugins.adjustFilters' : 'plugins.emptyHint') }}</div>
          <n-button v-if="!plugins.length" type="primary" :disabled="!executionAllowed" @click="emit('add')">{{ t('plugins.add') }}</n-button>
        </div>
      </n-spin>
    </div>
  </n-card>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { NButton, NCard, NIcon, NInput, NPopconfirm, NPopover, NSelect, NSpace, NSpin, NSwitch, NTag, NTooltip } from 'naive-ui'
import { Bookmark, BookmarkOutline, BusinessOutline, DesktopOutline, EllipsisHorizontal, PersonOutline } from '@vicons/ionicons5'
import type { DshPlugin } from '../../api/dshPlugins'
import { t } from '../../composables/i18n'
import { formatAppDateTime } from '../../composables/appTimezone'
import PluginAvailability from './PluginAvailability.vue'
import { pluginCardStatus, pluginConversationAvailable } from './pluginCardState'
import { hasStandalonePluginUi } from './pluginUiSurface'

const props = defineProps<{ plugins: DshPlugin[]; loading: boolean; verifyBusyId: string; toggleBusyId: string; uiOpeningId: string; executionAllowed: boolean; shortcutIds: string[] }>()
const emit = defineEmits<{ reload: []; add: []; toggle: [plugin: DshPlugin, enabled: boolean]; remove: [plugin: DshPlugin]; verify: [plugin: DshPlugin]; openUi: [plugin: DshPlugin]; toggleShortcut: [plugin: DshPlugin] }>()
function canOpenUi(plugin: DshPlugin): boolean {
  return props.executionAllowed && plugin.enabled &&
    ['verified', 'session_exposed', 'runtime_active'].includes(plugin.availability?.status || '') &&
    hasStandalonePluginUi(plugin)
}
const keyword = ref('')
const scope = ref('all')
const scopeOptions = computed(() => [
  { label: t('plugins.allScopes'), value: 'all' },
  { label: t('plugins.mine'), value: 'personal' },
  { label: t('plugins.enterprise'), value: 'organization' },
])
const filtered = computed(() => {
  const query = keyword.value.trim().toLocaleLowerCase()
  return props.plugins.filter(plugin =>
    (scope.value === 'all' || plugin.scope === scope.value) &&
    (!query || `${plugin.name} ${plugin.description} ${plugin.spec}`.toLocaleLowerCase().includes(query)),
  )
})
</script>

<style scoped>
.list-card{width:100%;margin:0;flex:1;min-height:0;overflow:hidden;border:1px solid #e6ebf5;border-radius:8px;background:#fff;box-shadow:0 6px 20px rgba(16,38,84,.05)}
.list-card :deep(.n-card-content){height:100%;display:flex;flex-direction:column}
.list-heading-row{display:flex;align-items:center;margin-bottom:14px;padding-bottom:10px;border-bottom:1px solid #edf1f7}
.list-heading{padding:8px 14px;border-radius:8px;background:#edf3ff;color:#2459e8;font-size:14px;font-weight:650}
.list-filter-row{padding:0 44px 12px;margin:0 -44px 12px;border-bottom:1px solid #edf1f7}
.filter-toolbar{display:flex;align-items:center;justify-content:space-between;gap:14px}.filter-left,.filter-right{flex-wrap:wrap}
.keyword-input{width:360px}.scope-select{width:160px}
.filter-toolbar svg{width:18px;height:18px;fill:none;stroke:currentColor;stroke-width:2;stroke-linecap:round;stroke-linejoin:round}
.list-body{flex:1;min-height:0;overflow:auto}
.plugin-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:12px}
.plugin-card{min-height:188px;padding:14px;border:1px solid rgba(28,45,82,.08);border-radius:8px;background:#fff;box-shadow:0 8px 18px rgba(15,31,69,.06),0 1px 2px rgba(15,31,69,.04);display:flex;flex-direction:column;gap:10px;transition:border-color .2s,box-shadow .2s,transform .2s}
.plugin-card:hover{border-color:rgba(54,106,255,.36);box-shadow:0 14px 34px rgba(33,58,126,.14),0 4px 10px rgba(33,58,126,.08);transform:translateY(-2px)}
.plugin-card-disabled{background:linear-gradient(180deg,#fbfcfe,#f6f8fc)}
.card-head,.card-footrow{display:flex;align-items:center;justify-content:space-between;gap:10px}.card-tags{display:inline-flex;align-items:center;gap:6px;flex-wrap:wrap}
.card-time{color:#7a8797;font-size:12px;white-space:nowrap}.card-version{color:#63816d;font-size:12px;font-weight:650}.card-title{color:#17233d;font-size:16px;font-weight:800;overflow-wrap:anywhere}
.card-desc{color:#5f6f85;font-size:13px;line-height:1.55;display:-webkit-box;-webkit-box-orient:vertical;-webkit-line-clamp:2;overflow:hidden}
.card-footrow{margin-top:auto}.card-actions{display:inline-flex;align-items:center;gap:6px}
.card-scope{display:inline-flex;align-items:center;gap:4px;white-space:nowrap;color:#547563;font-size:12px}.card-scope .n-icon{font-size:15px}.card-actions .n-button{font-size:12px}
.delete-btn svg{width:15px;height:15px;fill:none;stroke:currentColor;stroke-width:2;stroke-linecap:round}.delete-btn:hover{color:#d03050}
.empty-shell{min-height:320px;border:1px dashed #d8e2f2;border-radius:12px;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:12px;text-align:center;background:linear-gradient(180deg,#fbfdff,#fff)}
.empty-visual{width:54px;height:36px;border:1px solid #d8e2f2;border-radius:10px;display:grid;place-items:center;color:#2d63ff;font-size:11px;font-weight:700;box-shadow:0 4px 10px rgba(45,99,255,.06)}
.empty-title{color:#1a2744;font-size:15px;font-weight:700}.empty-desc{color:#6c7c94;font-size:13px}
@media(max-width:768px){.filter-toolbar{flex-direction:column;align-items:stretch}.keyword-input{width:100%}.plugin-grid{grid-template-columns:minmax(0,1fr)}.list-filter-row{padding:0 16px 12px;margin:0 -16px 12px}.card-time{display:none}}
</style>
