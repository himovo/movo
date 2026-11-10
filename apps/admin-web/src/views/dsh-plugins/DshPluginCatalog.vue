<template>
  <n-card class="list-card" :bordered="false" size="large">
    <div class="filter-row">
      <div class="filter-toolbar">
        <n-space align="center" :size="10" class="filter-left">
          <n-input v-model:value="keyword" clearable :placeholder="t('dshPlugins.search')" class="keyword-input" />
          <n-select v-model:value="status" :options="statusOptions" class="status-select" />
        </n-space>
        <n-space :size="10" class="filter-right">
          <n-button secondary @click="emit('reload')">
            <template #icon><svg viewBox="0 0 24 24"><path d="M21 12a9 9 0 0 0-9-9 9.75 9.75 0 0 0-6.74 2.74L3 8M3 3v5h5M3 12a9 9 0 0 0 9 9 9.75 9.75 0 0 0 6.74-2.74L21 16M16 16h5v5" /></svg></template>
            {{ t('dshPlugins.refresh') }}
          </n-button>
          <n-button type="primary" strong @click="emit('add')">
            <template #icon><svg viewBox="0 0 24 24"><path d="M5 12h14M12 5v14" /></svg></template>
            {{ t('dshPlugins.add') }}
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
                <n-tag size="small" :bordered="false" type="info">{{ t('dshPlugins.engine') }}</n-tag>
                <span class="card-version">v{{ plugin.version }}</span>
              </div>
              <span v-if="plugin.updatedAt" class="card-time">{{ formatAdminDateTime(plugin.updatedAt) }}</span>
            </div>
            <div class="card-title">{{ plugin.name }}</div>
            <n-tooltip trigger="hover" :delay="350"><template #trigger><div class="card-desc">{{ plugin.description || plugin.spec }}</div></template>{{ plugin.description || plugin.spec }}</n-tooltip>
            <PluginAvailability :availability="plugin.availability" :enabled="plugin.enabled" :busy="busyId === plugin.id" @verify="emit('verify', plugin)" />
            <div class="card-footrow">
              <span class="card-scope"><n-icon :component="BusinessOutline" />{{ t('dshPlugins.enterprise') }}</span>
              <div class="card-actions">
                <n-button v-if="canManageAccess" size="small" quaternary :title="t('dshPlugins.access')" @click="emit('access', plugin)">{{ t('dshPlugins.access') }}</n-button>
                <div class="card-switch"><span>{{ t(plugin.enabled ? 'dshPlugins.running' : 'dshPlugins.disabled') }}</span><n-switch size="small" :value="plugin.enabled" :loading="busyId === plugin.id" :disabled="!plugin.enabled && !['session_exposed', 'runtime_active', 'verified'].includes(plugin.availability?.status || '')" @update:value="value => emit('toggle', plugin, value)" /></div>
                <n-popconfirm @positive-click="emit('remove', plugin)">
                  <template #trigger><n-button class="delete-btn" size="small" quaternary circle :title="t('dshPlugins.remove')" :aria-label="t('dshPlugins.remove')"><svg viewBox="0 0 24 24"><path d="M3 6h18M8 6V4h8v2M6 6l1 14h10l1-14M10 11v6M14 11v6" /></svg></n-button></template>
                  {{ t('dshPlugins.confirmRemove') }}
                </n-popconfirm>
              </div>
            </div>
          </article>
        </div>
        <div v-else class="empty-shell"><DshPluginsIcon class="empty-icon" /><div class="empty-title">{{ t(plugins.length ? 'dshPlugins.noMatches' : 'dshPlugins.empty') }}</div><div class="empty-desc">{{ t(plugins.length ? 'dshPlugins.adjustFilters' : 'dshPlugins.emptyHint') }}</div><n-button v-if="!plugins.length" type="primary" @click="emit('add')">{{ t('dshPlugins.add') }}</n-button></div>
      </n-spin>
    </div>
  </n-card>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { NButton, NCard, NIcon, NInput, NPopconfirm, NSelect, NSpace, NSpin, NSwitch, NTag, NTooltip } from 'naive-ui'
import { BusinessOutline } from '@vicons/ionicons5'
import type { DshPlugin } from '@/api/dsh-plugins'
import { t } from '@/composables/i18n'
import { formatAdminDateTime } from '@/composables/adminTimezone'
import { DshPluginsIcon } from '@/icons/DshPluginsIcon'
import PluginAvailability from './PluginAvailability.vue'

const props = defineProps<{ plugins: DshPlugin[]; loading: boolean; busyId: string; canManageAccess: boolean }>()
const emit = defineEmits<{ reload: []; add: []; toggle: [plugin: DshPlugin, enabled: boolean]; remove: [plugin: DshPlugin]; verify: [plugin: DshPlugin]; access: [plugin: DshPlugin] }>()
const keyword = ref('')
const status = ref('all')
const statusOptions = computed(() => [
  { label: t('dshPlugins.allStatuses'), value: 'all' },
  { label: t('dshPlugins.enabled'), value: 'enabled' },
  { label: t('dshPlugins.disabled'), value: 'disabled' },
])
const filtered = computed(() => {
  const query = keyword.value.trim().toLocaleLowerCase()
  return props.plugins.filter(plugin =>
    (status.value === 'all' || plugin.enabled === (status.value === 'enabled')) &&
    (!query || `${plugin.name} ${plugin.description} ${plugin.spec}`.toLocaleLowerCase().includes(query)),
  )
})
</script>

<style scoped>
.list-card{width:calc(100% - 24px);margin:-16px 12px 0;flex:1;min-height:0;overflow:hidden;border:1px solid #e6ebf5;border-radius:8px;background:#fff;box-shadow:0 6px 20px rgba(16,38,84,.05)}
.list-card :deep(.n-card__content){height:100%;display:flex;flex-direction:column}.filter-row{padding:0 44px 12px;margin:0 -44px 12px;border-bottom:1px solid #edf1f7}.filter-toolbar{display:flex;align-items:center;justify-content:space-between;gap:14px}.filter-left,.filter-right{flex-wrap:wrap}.keyword-input{width:360px}.status-select{width:160px}.filter-toolbar svg{width:18px;height:18px;fill:none;stroke:currentColor;stroke-width:2;stroke-linecap:round;stroke-linejoin:round}
.list-body{flex:1;min-height:0;overflow:auto}.plugin-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:12px}.plugin-card{min-height:188px;padding:14px;border:1px solid rgba(28,45,82,.08);border-radius:8px;background:#fff;box-shadow:0 8px 18px rgba(15,31,69,.06),0 1px 2px rgba(15,31,69,.04);display:flex;flex-direction:column;gap:10px;transition:border-color .2s,box-shadow .2s,transform .2s}.plugin-card:hover{border-color:rgba(54,106,255,.36);box-shadow:0 14px 34px rgba(33,58,126,.14),0 4px 10px rgba(33,58,126,.08);transform:translateY(-2px)}.plugin-card-disabled{background:linear-gradient(180deg,#fbfcfe,#f6f8fc)}.card-head{display:flex;align-items:center;justify-content:space-between;gap:10px}.card-tags{display:inline-flex;align-items:center;gap:6px;flex-wrap:wrap}.card-time{color:#7a8797;font-size:12px;white-space:nowrap}.card-version{color:#63816d;font-size:12px;font-weight:650}.card-title{color:#17233d;font-size:16px;font-weight:800;overflow-wrap:anywhere}.card-desc{color:#5f6f85;font-size:13px;line-height:1.55;display:-webkit-box;-webkit-box-orient:vertical;-webkit-line-clamp:2;overflow:hidden}.card-footrow{margin-top:auto;display:flex;align-items:center;justify-content:space-between;gap:10px}.card-actions{display:inline-flex;align-items:center;gap:6px}.card-scope{display:inline-flex;align-items:center;gap:4px;white-space:nowrap;color:#547563;font-size:12px}.card-scope .n-icon{font-size:15px}.card-switch{display:inline-flex;align-items:center;gap:8px;padding:4px 10px;border-radius:999px;background:#f6f9ff;border:1px solid #e3ebfb;color:#4a5d7c;font-size:12px}.delete-btn svg{width:15px;height:15px;fill:none;stroke:currentColor;stroke-width:2;stroke-linecap:round}.delete-btn:hover{color:#d03050}
.empty-shell{min-height:320px;border:1px dashed #d8e2f2;border-radius:12px;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:12px;text-align:center;background:linear-gradient(180deg,#fbfdff,#fff)}.empty-icon{width:36px;height:36px;color:#2d63ff}.empty-title{color:#101c3d;font-size:24px;font-weight:800}.empty-desc{color:#65748c;font-size:14px}
@media(max-width:768px){.filter-row{padding:0 16px 12px;margin:0 -16px 12px}.keyword-input{width:min(360px,100%)}.plugin-grid{grid-template-columns:1fr}.card-time{display:none}}
</style>
