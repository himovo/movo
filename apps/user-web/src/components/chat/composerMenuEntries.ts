import type { SelectableSkillItem } from '../../api/skills'
import { t } from '../../composables/i18n'
import { COMPACTION_COMMAND_ID, SKILL_MENU_ID } from './compactionCommand'

export function composerMenuEntries(keyword: string, pluginCommands: SelectableSkillItem[] = []): SelectableSkillItem[] {
  const commands = [{
    id: COMPACTION_COMMAND_ID, name: t('context.compactAction'),
    description: t('context.compactDescription'), search: 'compact',
  }]
  const matches = commands.filter(command =>
    `${command.name} ${command.search}`.toLowerCase().includes(keyword.toLowerCase()))
  return [
    ...matches,
    ...pluginCommands,
    { id: SKILL_MENU_ID, name: t('context.browseSkills'), description: t('context.browseSkillsHint') },
  ].map<SelectableSkillItem>(item => ({
    mainId: '', scenario: '', type: 'ordinary', sourceScope: 'user',
    enabled: true, available: true,
    ...item,
  }))
}
