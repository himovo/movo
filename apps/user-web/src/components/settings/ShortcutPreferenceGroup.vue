<script setup lang="ts">
import type { ShortcutEntry, ShortcutGroup } from '../../api/shortcuts'
import { promptGuideIcons } from '../chat/promptGuideConfig'
import { t, translateSourceText } from '../../composables/i18n'

defineProps<{ group: ShortcutGroup; entries: ShortcutEntry[] }>()
const emit = defineEmits<{
  move: [groupKey: string, index: number, offset: number]
  remove: [id: string]
  add: []
  rename: []
  removeGroup: []
}>()

function groupIcon(group: ShortcutGroup): string {
  return group.iconSvg || promptGuideIcons[group.iconKey as keyof typeof promptGuideIcons] || promptGuideIcons.grid
}
</script>

<template>
  <section class="group-card" :class="{ locked: group.locked }">
    <header>
      <span class="group-icon" v-html="groupIcon(group)" />
      <strong>{{ translateSourceText(group.label) }}</strong>
      <span class="count">{{ entries.length }} / 6</span>
      <span v-if="group.locked" class="lock-label">{{ t('shortcuts.locked') }}</span>
      <n-button v-if="group.personal" class="shortcut-action-button" size="tiny" secondary :disabled="entries.length >= 6" @click="emit('add')">{{ t('shortcuts.add') }}</n-button>
      <n-button v-if="group.personal" class="shortcut-action-button" size="tiny" quaternary @click="emit('rename')">{{ t('shortcuts.rename_group') }}</n-button>
      <n-button v-if="group.personal" class="shortcut-action-button" size="tiny" quaternary type="error" @click="emit('removeGroup')">{{ t('shortcuts.remove_group') }}</n-button>
    </header>
    <div v-for="(entry, index) in entries" :key="entry.id" class="entry-row">
      <div class="entry-icon" v-html="entry.iconSvg || promptGuideIcons[entry.iconKey as keyof typeof promptGuideIcons] || promptGuideIcons.document" />
      <div class="entry-name"><strong>{{ translateSourceText(entry.label) }}</strong><small>{{ entry.type === 'skill' ? 'Skill' : 'Prompt' }}</small></div>
      <template v-if="!group.locked">
        <button type="button" class="shortcut-icon-button" :disabled="index === 0" :aria-label="t('shortcuts.move_up')" @click="emit('move', group.key, index, -1)">↑</button>
        <button type="button" class="shortcut-icon-button" :disabled="index === entries.length - 1" :aria-label="t('shortcuts.move_down')" @click="emit('move', group.key, index, 1)">↓</button>
        <n-button v-if="entry.personal" class="shortcut-action-button" quaternary size="tiny" type="error" @click="emit('remove', entry.id)">{{ t('shortcuts.remove') }}</n-button>
      </template>
    </div>
  </section>
</template>

<style scoped>
.group-card{overflow:hidden;border:1px solid #dfe7f4;border-radius:14px;background:#fff}.group-card.locked{background:#fbfcff}
header{display:flex;align-items:center;gap:10px;min-height:50px;padding:10px 14px;background:#f7f9ff;border-bottom:1px solid #e8edf7}
header strong{flex:1;color:#26344a}.count,.lock-label{font-size:12px;color:#71809b}.lock-label{border-radius:20px;background:#e9eef9;padding:3px 9px}
.group-icon,.entry-icon{display:flex;width:24px;height:24px;align-items:center;justify-content:center;color:#3769d4}.group-icon :deep(svg),.entry-icon :deep(svg){width:18px;height:18px}
.entry-row{display:flex;align-items:center;gap:8px;min-height:52px;padding:8px 14px;border-bottom:1px solid #edf1f7}.entry-row:last-child{border-bottom:0}
.entry-name{display:grid;flex:1;min-width:0}.entry-name strong{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-size:13px;color:#29364b}.entry-name small{font-size:11px;color:#91a0b5}
.group-card :deep(button),.group-card :deep(.n-button),.group-card :deep(.n-button__content){cursor:pointer!important}.group-card :deep(button:disabled),.group-card :deep(.n-button--disabled),.group-card :deep(.n-button--disabled .n-button__content){cursor:not-allowed!important}
.group-card :deep(.shortcut-action-button){border-radius:6px;cursor:pointer!important}.group-card :deep(.shortcut-action-button:hover){background:#eef4ff;color:#2563eb}.group-card :deep(.shortcut-action-button.n-button--error-type:hover){background:#fff1f2;color:#dc2626}.shortcut-icon-button{display:inline-flex;width:28px;min-width:28px;height:28px;align-items:center;justify-content:center;padding:0;border:0;border-radius:6px;color:#334155;background:transparent;font:inherit;line-height:1;cursor:pointer}.shortcut-icon-button:hover{background:#eef4ff;color:#2563eb}.shortcut-icon-button:disabled{cursor:not-allowed;opacity:.35}
</style>
