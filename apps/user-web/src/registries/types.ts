// Shared descriptor types for the three execution-rendering registries.

export interface ToolDescriptor {
  /** Emoji or short text shown as the row icon */
  icon: string
  /** i18n key used as the row title */
  labelKey: string
  /** Phase reported while this tool is running (drives top status pill) */
  phase: string
  /** Single-line summary derived from args. Returns '' if nothing useful. */
  formatArgs?: (args: Record<string, any>) => string
  /** Optional renderer hint for the result body ('terminal' | 'json' | 'text') */
  resultRenderer?: 'terminal' | 'json' | 'text' | 'links'
}

export interface TaskKindDescriptor {
  icon: string
  labelKey: string
  phase: string
}

export interface ArtifactDescriptor {
  icon: string
  labelKey: string
  /** Available actions on the artifact card */
  actions: Array<'open' | 'edit' | 'preview' | 'export' | 'download' | 'copy'>
}
