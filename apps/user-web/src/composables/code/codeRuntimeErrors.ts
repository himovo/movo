export function codeRuntimeErrorMessage(error: unknown, locale: 'zh' | 'en'): string {
  const raw = String(error instanceof Error ? error.message : error || '')
  const normalized = raw.toLowerCase()
  if (normalized.includes('another desktop device')) {
    return locale === 'zh'
      ? '此项目会话绑定在另一台桌面设备。历史记录可查看，但请回到原设备继续执行。'
      : 'This project task is bound to another desktop device. History remains readable; continue on the original device.'
  }
  if (normalized.includes('workspace') && (normalized.includes('unavailable') || normalized.includes('missing'))) {
    return locale === 'zh'
      ? '原项目目录已丢失或不可访问。历史记录仍可查看；请恢复原目录后重试。'
      : 'The original project folder is missing or unavailable. History remains readable; restore the folder and retry.'
  }
  if (normalized.includes('profile') && (normalized.includes('compatible') || normalized.includes('changed'))) {
    return locale === 'zh'
      ? '当前 DSH Runtime Profile 与该历史会话不兼容。为保护原会话，系统未自动切换执行环境。'
      : 'The current DSH Runtime Profile is incompatible with this historical task. Execution was not silently moved.'
  }
  if (normalized.includes('runtime') && (normalized.includes('unavailable') || normalized.includes('ready'))) {
    return locale === 'zh'
      ? '本地 DSH Runtime 当前不可用。历史记录仍可查看，请恢复桌面 Runtime 后重试。'
      : 'The local DSH Runtime is unavailable. History remains readable; restore the desktop Runtime and retry.'
  }
  return raw || (locale === 'zh' ? '本地 Code 会话暂时不可用。' : 'The local Code task is unavailable.')
}
