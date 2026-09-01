// Task-kind registry. Drives the "section header" + section icon + the
// phase pill while a task of this kind is the active one.

import type { TaskKindDescriptor } from './types'

export const DEFAULT_TASK: TaskKindDescriptor = {
  icon: '⏺', labelKey: 'task.generic', phase: 'working',
}

const REGISTRY: Record<string, TaskKindDescriptor> = {}

export function registerTaskKind(kind: string, d: TaskKindDescriptor): void {
  REGISTRY[kind] = d
}

export function resolveTaskKind(kind: string): TaskKindDescriptor {
  return REGISTRY[kind] || DEFAULT_TASK
}

// ---- Built-in registrations ----
registerTaskKind('root',     { icon: '⏺',  labelKey: 'task.root',     phase: 'thinking' })
registerTaskKind('research', { icon: '🔬', labelKey: 'task.research', phase: 'searching' })
registerTaskKind('compose',  { icon: '✍️', labelKey: 'task.compose',  phase: 'composing' })
registerTaskKind('render',   { icon: '📄', labelKey: 'task.render',   phase: 'rendering' })
registerTaskKind('verify',   { icon: '✔️', labelKey: 'task.verify',   phase: 'verifying' })
registerTaskKind('browser',  { icon: '🌐', labelKey: 'task.browser',  phase: 'browsing' })
registerTaskKind('coding',   { icon: '💻', labelKey: 'task.coding',   phase: 'coding' })
registerTaskKind('plan',     { icon: '🧭', labelKey: 'task.plan',     phase: 'thinking' })
registerTaskKind('repair',   { icon: '🛠', labelKey: 'task.repair',   phase: 'working' })

// Activity-kind aliases (emitted by backend ActivityEmitter). Reused here so
// progress breadcrumbs contribute meaningful labels + phase transitions.
registerTaskKind('start',    { icon: '⏺',  labelKey: 'task.root',     phase: 'thinking' })
registerTaskKind('search',   { icon: '🔍', labelKey: 'task.research', phase: 'searching' })
registerTaskKind('browse',   { icon: '🌐', labelKey: 'task.browser',  phase: 'browsing' })
registerTaskKind('analyze',  { icon: '🧠', labelKey: 'task.verify',   phase: 'analyzing' })
registerTaskKind('write',    { icon: '✍️', labelKey: 'task.compose',  phase: 'composing' })
registerTaskKind('tool',     { icon: '🔧', labelKey: 'task.generic',  phase: 'working' })
registerTaskKind('complete', { icon: '✓',  labelKey: 'task.generic',  phase: 'done' })
registerTaskKind('error',    { icon: '⚠',  labelKey: 'task.generic',  phase: 'working' })
registerTaskKind('review',   { icon: '🔍', labelKey: 'task.verify',   phase: 'verifying' })
registerTaskKind('verdict',  { icon: '⚖',  labelKey: 'task.verify',   phase: 'verifying' })
registerTaskKind('repair',   { icon: '🛠', labelKey: 'task.repair',   phase: 'working' })
