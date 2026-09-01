export type ChangeTone = 'added' | 'modified' | 'deleted' | 'renamed' | 'conflict' | 'neutral'

export interface ChangeStatusPresentation {
  label: string
  description: string
  tone: ChangeTone
}

export function changeStatusPresentation(status: string, locale: 'zh' | 'en' = 'zh'): ChangeStatusPresentation {
  const code = status.trim().toUpperCase()
  const english = locale === 'en'
  if (code === '??') return { label: 'U', description: english ? 'Untracked file' : '尚未被 Git 跟踪的新文件', tone: 'added' }
  if (code.includes('U') || code === 'AA' || code === 'DD') return { label: 'C', description: english ? 'Merge conflict' : '存在尚未解决的合并冲突', tone: 'conflict' }
  if (code.includes('D')) return { label: 'D', description: english ? 'Deleted file' : '已删除的文件', tone: 'deleted' }
  if (code.includes('R')) return { label: 'R', description: english ? 'Renamed file' : '已重命名的文件', tone: 'renamed' }
  if (code.includes('A')) return { label: 'A', description: english ? 'Added file' : '已添加到 Git 的新文件', tone: 'added' }
  if (code.includes('M')) return { label: 'M', description: english ? 'Modified file' : '内容已修改的文件', tone: 'modified' }
  return { label: code || (english ? 'Changed' : '变更'), description: english ? 'Changed file' : '发生变更的文件', tone: 'neutral' }
}

export type FileTone = 'typescript' | 'javascript' | 'python' | 'vue' | 'json' | 'web' | 'style' | 'markdown' | 'config' | 'shell' | 'database' | 'native' | 'generic'

export interface FileTypePresentation {
  label: string
  name: string
  tone: FileTone
}

const exactNames: Record<string, FileTypePresentation> = {
  dockerfile: { label: 'DK', name: 'Dockerfile', tone: 'config' },
  makefile: { label: 'MK', name: 'Makefile', tone: 'config' },
  license: { label: 'TXT', name: 'Text', tone: 'generic' },
}

const extensions: Record<string, FileTypePresentation> = {
  ts: { label: 'TS', name: 'TypeScript', tone: 'typescript' },
  tsx: { label: 'TSX', name: 'TypeScript React', tone: 'typescript' },
  js: { label: 'JS', name: 'JavaScript', tone: 'javascript' },
  jsx: { label: 'JSX', name: 'JavaScript React', tone: 'javascript' },
  mjs: { label: 'JS', name: 'JavaScript module', tone: 'javascript' },
  cjs: { label: 'JS', name: 'CommonJS', tone: 'javascript' },
  py: { label: 'PY', name: 'Python', tone: 'python' },
  vue: { label: 'V', name: 'Vue', tone: 'vue' },
  json: { label: '{}', name: 'JSON', tone: 'json' },
  jsonc: { label: '{}', name: 'JSON with comments', tone: 'json' },
  html: { label: '<>', name: 'HTML', tone: 'web' },
  htm: { label: '<>', name: 'HTML', tone: 'web' },
  css: { label: '#', name: 'CSS', tone: 'style' },
  scss: { label: 'S', name: 'SCSS', tone: 'style' },
  sass: { label: 'S', name: 'Sass', tone: 'style' },
  less: { label: 'L', name: 'Less', tone: 'style' },
  md: { label: 'MD', name: 'Markdown', tone: 'markdown' },
  mdx: { label: 'MDX', name: 'MDX', tone: 'markdown' },
  yaml: { label: 'YML', name: 'YAML', tone: 'config' },
  yml: { label: 'YML', name: 'YAML', tone: 'config' },
  toml: { label: 'T', name: 'TOML', tone: 'config' },
  xml: { label: '<>', name: 'XML', tone: 'config' },
  ini: { label: 'INI', name: 'Configuration', tone: 'config' },
  env: { label: 'ENV', name: 'Environment', tone: 'config' },
  sh: { label: '$', name: 'Shell', tone: 'shell' },
  bash: { label: '$', name: 'Bash', tone: 'shell' },
  zsh: { label: '$', name: 'Zsh', tone: 'shell' },
  sql: { label: 'DB', name: 'SQL', tone: 'database' },
  go: { label: 'GO', name: 'Go', tone: 'native' },
  rs: { label: 'RS', name: 'Rust', tone: 'native' },
  java: { label: 'JV', name: 'Java', tone: 'native' },
  kt: { label: 'KT', name: 'Kotlin', tone: 'native' },
  swift: { label: 'SW', name: 'Swift', tone: 'native' },
  c: { label: 'C', name: 'C', tone: 'native' },
  h: { label: 'H', name: 'C header', tone: 'native' },
  cc: { label: 'C++', name: 'C++', tone: 'native' },
  cpp: { label: 'C++', name: 'C++', tone: 'native' },
  cs: { label: 'C#', name: 'C#', tone: 'native' },
  rb: { label: 'RB', name: 'Ruby', tone: 'native' },
  php: { label: 'PHP', name: 'PHP', tone: 'native' },
}

export function fileTypePresentation(path: string): FileTypePresentation {
  const name = path.split('/').pop()?.toLowerCase() || path.toLowerCase()
  if (exactNames[name]) return exactNames[name]
  if (name.startsWith('.env')) return extensions.env
  const extension = name.includes('.') ? name.split('.').pop()! : ''
  return extensions[extension] || { label: '·', name: 'File', tone: 'generic' }
}
