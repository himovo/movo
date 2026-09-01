import type { DshWorkspaceSummary } from '../../platform/types'

function displayPath(path: string): string {
  const parts = path.split('/').filter(Boolean)
  return parts.at(-1) || path
}

export function suggestCommitMessage(summary: DshWorkspaceSummary, locale: 'zh' | 'en' = 'zh'): string {
  const changes = summary.changes
  if (!changes.length) return ''
  const first = displayPath(changes[0].path)
  const added = changes.filter(item => item.status === '??' || item.status.includes('A')).length
  const deleted = changes.filter(item => item.status.includes('D')).length
  const onlyAdded = added === changes.length
  const onlyDeleted = deleted === changes.length

  if (changes.length === 1) {
    if (onlyAdded) return locale === 'en' ? `Add ${first}` : `新增 ${first}`
    if (onlyDeleted) return locale === 'en' ? `Remove ${first}` : `删除 ${first}`
    return locale === 'en' ? `Update ${first}` : `更新 ${first}`
  }
  if (onlyAdded) return locale === 'en' ? `Add ${changes.length} project files` : `新增 ${changes.length} 个项目文件`
  if (onlyDeleted) return locale === 'en' ? `Remove ${changes.length} obsolete files` : `删除 ${changes.length} 个旧文件`
  return locale === 'en'
    ? `Update ${first} and ${changes.length - 1} related files`
    : `更新 ${first} 等 ${changes.length} 个文件`
}
