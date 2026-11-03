import type { ExecutionStateV3 } from './model'

type RunStatus = ExecutionStateV3['runStatus']

/** A failed tool attempt is not the same as a failed assistant task. */
export function toolAttemptStateKey(runStatus: RunStatus): string {
  if (runStatus === 'completed') return 'execution.v3.tool_attempt_continued'
  if (runStatus === 'running') return 'execution.v3.tool_attempt_adjusting'
  return 'execution.v3.tool_attempt_failed'
}

export function toolGroupFailureKey(runStatus: RunStatus): string {
  if (runStatus === 'completed') return 'execution.v3.tool_group_completed_with_attempts'
  if (runStatus === 'running') return 'execution.v3.tool_group_adjusting'
  return 'execution.v3.repeated_failed'
}


/** Only classify generated-code errors; infrastructure failures retain their own details. */
export function scriptAttemptReasonKey(name: unknown, error: unknown): string {
  if (String(name || '') !== 'run_script') return ''
  const detail = String(error || '')
  if (/SyntaxError|IndentationError|TabError/.test(detail)) return 'execution.v3.script_syntax'
  if (/ModuleNotFoundError|ImportError|No module named/.test(detail)) return 'execution.v3.script_dependency'
  if (/OSError:.*(?:\[Errno 30\]|Read-only file system)/i.test(detail)) return 'execution.v3.script_output_path'
  if (/PermissionError:.*(?:\[Errno 13\]|Permission denied|\[WinError 5\]|Access is denied)/i.test(detail)) return 'execution.v3.script_file_access'
  if (/FileNotFoundError|IndexError|KeyError/.test(detail)) return 'execution.v3.script_input'
  if (/NameError|TypeError|ValueError|AttributeError|ZeroDivisionError|AssertionError/.test(detail)) return 'execution.v3.script_logic'
  return ''
}
