import type { SkillPreparationRecord } from '@/api/skills'

export function downloadPreparationLog(record: SkillPreparationRecord, skillName: string): void {
  const safeName = skillName.trim().replace(/[^\p{L}\p{N}._-]+/gu, '-').slice(0, 80) || 'skill'
  const filename = `skill-preparation-${safeName}-${record.id}.txt`
  const url = URL.createObjectURL(new Blob([record.log || ''], { type: 'text/plain;charset=utf-8' }))
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  document.body.appendChild(link)
  link.click()
  link.remove()
  setTimeout(() => URL.revokeObjectURL(url), 60_000)
}
