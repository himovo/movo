// Tool registry. Add a new tool here once; UI auto-renders it.
// Anything not registered uses DEFAULT_TOOL — so new tools work day-1.

import type { ToolDescriptor } from './types'

export const DEFAULT_TOOL: ToolDescriptor = {
  icon: '',
  labelKey: 'tool.generic',
  phase: 'working',
  formatArgs: (a) => {
    if (!a || typeof a !== 'object') return ''
    try { return JSON.stringify(a).slice(0, 80) } catch { return '' }
  },
}

const REGISTRY: Record<string, ToolDescriptor> = {}

function safeUrl(raw: any): string {
  const s = String(raw || '')
  if (!s) return ''
  try {
    const u = new URL(s)
    u.searchParams.delete('token')
    const hash = u.hash || ''
    const route = hash.startsWith('#/') ? hash : ''
    return `${u.origin}/${route}`.replace(/\/#/, '#')
  } catch {
    return s.replace(/([?&]token=)[^&#]+/i, '$1***').slice(0, 120)
  }
}

export function registerTool(name: string, d: ToolDescriptor): void {
  REGISTRY[name] = d
}

/** Bulk register an alias map → same descriptor. */
export function registerToolAliases(names: string[], d: ToolDescriptor): void {
  for (const n of names) REGISTRY[n] = d
}

export function resolveTool(name: string): ToolDescriptor {
  return REGISTRY[name] || DEFAULT_TOOL
}

// ---------------------------------------------------------------------------
// Built-in registrations (project-known tools). Adding a new one is a one-liner.
// ---------------------------------------------------------------------------

registerToolAliases(['web_search', 'tavily_search', 'baidu_web_search', 'search'], {
  icon: '', labelKey: 'tool.search', phase: 'searching',
  formatArgs: (a) => String(a?.q || a?.query || a?.keyword || ''),
  resultRenderer: 'links',
})

registerTool('kb_search', {
  icon: '', labelKey: 'tool.kb_search', phase: 'searching',
  formatArgs: (a) => String(a?.q || a?.query || ''),
})

registerToolAliases(['read_page', 'crawl_page', 'fetch_url'], {
  icon: '', labelKey: 'tool.read', phase: 'reading',
  formatArgs: (a) => String(a?.url || ''),
})

registerToolAliases(['browser_open', 'browser_goto'], {
  icon: '', labelKey: 'tool.browse', phase: 'browsing',
  formatArgs: (a) => String(a?.url || ''),
})

registerToolAliases(['shell_exec', 'bash', 'run_command'], {
  icon: '', labelKey: 'tool.shell', phase: 'working',
  formatArgs: (a) => String(a?.command || a?.cmd || ''),
  resultRenderer: 'terminal',
})

registerTool('email_send', {
  icon: '', labelKey: 'tool.email_send', phase: 'sending',
  formatArgs: (a) => `${a?.to || ''} · ${a?.subject || ''}`.replace(/^ · /, '').replace(/ · $/, ''),
})

registerToolAliases(['render_pptx', 'create_ppt_from_html'], {
  icon: '', labelKey: 'tool.render_pptx', phase: 'rendering',
  formatArgs: (a) => a?.slides ? `${a.slides} slides` : '',
})
registerToolAliases(['render_docx', 'create_docx_from_markdown'], {
  icon: '', labelKey: 'tool.render_docx', phase: 'rendering',
})
registerTool('render_pdf', { icon: '', labelKey: 'tool.render_pdf', phase: 'rendering' })

registerToolAliases(
  ['get_stock_quote', 'get_stock_daily', 'get_stock_financial', 'get_stock_basic_info',
   'get_top10_holders', 'get_stock_forecast', 'get_stock_concepts', 'get_stock_moneyflow',
   'search_stock_code', 'get_main_business', 'get_report_dates', 'get_financials'],
  { icon: '', labelKey: 'tool.stock', phase: 'working',
    formatArgs: (a) => String(a?.symbol || a?.code || a?.ts_code || '') },
)

registerToolAliases(
  ['get_company_info', 'get_company_registry', 'search_company_v2'],
  { icon: '', labelKey: 'tool.company', phase: 'working',
    formatArgs: (a) => String(a?.name || a?.keyword || '') },
)

registerTool('get_current_time', {
  icon: '', labelKey: 'tool.generic', phase: 'working',
})

registerTool('infographic_generate', {
  icon: '', labelKey: 'tool.generic', phase: 'rendering',
})

registerTool('publish_article', {
  icon: '', labelKey: 'tool.generic', phase: 'sending',
})

// ---------------------------------------------------------------------------
// Browser automation tools dispatched to the native-CDP local agent.
// Names mirror backend/app/browser/tools.py.
// ---------------------------------------------------------------------------

registerTool('browser_navigate', {
  icon: '', labelKey: 'tool.browse', phase: 'browsing',
  formatArgs: (a) => safeUrl(a?.url),
})
registerTool('browser_observe', {
  icon: '', labelKey: 'tool.read', phase: 'reading',
})
registerTool('browser_click', {
  icon: '', labelKey: 'tool.browse', phase: 'browsing',
  formatArgs: () => '',
})
registerTool('browser_fill', {
  icon: '', labelKey: 'tool.browse', phase: 'composing',
  formatArgs: (a) => {
    const v = String(a?.value || '')
    return v.length > 50 ? v.slice(0, 50) + '...' : v
  },
})
registerTool('browser_select', {
  icon: '', labelKey: 'tool.browse', phase: 'browsing',
  formatArgs: (a) => String(a?.value || ''),
})
registerTool('browser_press', {
  icon: '', labelKey: 'tool.browse', phase: 'browsing',
  formatArgs: (a) => String(a?.key || ''),
})
registerTool('browser_scroll', {
  icon: '', labelKey: 'tool.browse', phase: 'browsing',
  formatArgs: (a) => String(a?.direction || ''),
})
registerTool('browser_wait_for', {
  icon: '', labelKey: 'tool.browse', phase: 'browsing',
  formatArgs: (a) => a?.text ? `text: "${a.text}"` : a?.ref ? `ref: ${a.ref}` : '',
})
registerTool('browser_screenshot', {
  icon: '', labelKey: 'tool.browse', phase: 'browsing',
})
registerTool('browser_read_text', {
  icon: '', labelKey: 'tool.read', phase: 'reading',
  formatArgs: (a) => a?.ref ? `ref: ${a.ref}` : 'body',
})
registerTool('browser_tab_new', {
  icon: '', labelKey: 'tool.browse', phase: 'browsing',
  formatArgs: (a) => safeUrl(a?.url),
})
registerTool('browser_back', {
  icon: '', labelKey: 'tool.browse', phase: 'browsing',
})
registerTool('browser_forward', {
  icon: '', labelKey: 'tool.browse', phase: 'browsing',
})
