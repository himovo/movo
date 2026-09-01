import hljs from 'highlight.js/lib/core'
import bash from 'highlight.js/lib/languages/bash'
import css from 'highlight.js/lib/languages/css'
import javascript from 'highlight.js/lib/languages/javascript'
import json from 'highlight.js/lib/languages/json'
import markdown from 'highlight.js/lib/languages/markdown'
import python from 'highlight.js/lib/languages/python'
import sql from 'highlight.js/lib/languages/sql'
import typescript from 'highlight.js/lib/languages/typescript'
import xml from 'highlight.js/lib/languages/xml'
import { fileTypePresentation } from './changePresentation'

hljs.registerLanguage('bash', bash)
hljs.registerLanguage('css', css)
hljs.registerLanguage('javascript', javascript)
hljs.registerLanguage('json', json)
hljs.registerLanguage('markdown', markdown)
hljs.registerLanguage('python', python)
hljs.registerLanguage('sql', sql)
hljs.registerLanguage('typescript', typescript)
hljs.registerLanguage('xml', xml)

const languageByTone = {
  typescript: 'typescript', javascript: 'javascript', python: 'python', vue: 'xml', json: 'json', web: 'xml', style: 'css', markdown: 'markdown', config: 'json', shell: 'bash', database: 'sql', native: 'javascript', generic: '',
} as const

function escapeHtml(value: string) {
  return value.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
}

export function syntaxLanguage(path: string, language?: string) {
  const requested = (language || '').toLowerCase()
  const aliases: Record<string, string> = { ts: 'typescript', typescript: 'typescript', js: 'javascript', javascript: 'javascript', py: 'python', python: 'python', html: 'xml', vue: 'xml', yml: 'json', yaml: 'json', md: 'markdown', sh: 'bash', shell: 'bash' }
  if (requested && aliases[requested]) return aliases[requested]
  return languageByTone[fileTypePresentation(path).tone]
}

export function highlightCode(value: string, path: string, language?: string) {
  const target = syntaxLanguage(path, language)
  if (!target) return escapeHtml(value)
  try { return hljs.highlight(value, { language: target, ignoreIllegals: true }).value }
  catch { return escapeHtml(value) }
}
