import assert from 'node:assert/strict'
import test from 'node:test'
import { toolAttemptStateKey, toolGroupFailureKey } from '../src/features/execution-v3/domain/toolAttemptPresentation'

test('an intermediate tool failure does not label a completed task as failed', () => {
  assert.equal(toolAttemptStateKey('completed'), 'execution.v3.tool_attempt_continued')
  assert.equal(toolGroupFailureKey('completed'), 'execution.v3.tool_group_completed_with_attempts')
})

test('running and failed tasks retain distinct attempt context', () => {
  assert.equal(toolAttemptStateKey('running'), 'execution.v3.tool_attempt_adjusting')
  assert.equal(toolGroupFailureKey('failed'), 'execution.v3.repeated_failed')
})

test('generated Python issues are explained without calling them application failures', async () => {
  const { scriptAttemptReasonKey } = await import('../src/features/execution-v3/domain/toolAttemptPresentation')
  assert.equal(scriptAttemptReasonKey('run_script', 'SyntaxError: invalid syntax'), 'execution.v3.script_syntax')
  assert.equal(scriptAttemptReasonKey('run_script', "ModuleNotFoundError: No module named 'pptx'"), 'execution.v3.script_dependency')
  assert.equal(scriptAttemptReasonKey('run_script', 'IndexError: list index out of range'), 'execution.v3.script_input')
  assert.equal(scriptAttemptReasonKey('run_script', 'TypeError: wrong arguments'), 'execution.v3.script_logic')
  assert.equal(scriptAttemptReasonKey('run_script', 'Sandbox manager connection refused'), '')
  assert.equal(scriptAttemptReasonKey('browser_task', 'IndexError'), '')
})


test('sandbox file restrictions explain how the code attempt needs adjustment', async () => {
  const { scriptAttemptReasonKey } = await import('../src/features/execution-v3/domain/toolAttemptPresentation')
  assert.equal(scriptAttemptReasonKey('run_script', "OSError: [Errno 30] Read-only file system: '/app/outputs'"), 'execution.v3.script_output_path')
  assert.equal(scriptAttemptReasonKey('run_script', "PermissionError: [Errno 13] Permission denied: '/data/output'"), 'execution.v3.script_file_access')
  assert.equal(scriptAttemptReasonKey('run_script', 'PermissionError: [WinError 5] Access is denied'), 'execution.v3.script_file_access')
  assert.equal(scriptAttemptReasonKey('run_script', 'Docker socket connection refused'), '')
  assert.equal(scriptAttemptReasonKey('web_collect', 'OSError: [Errno 30] Read-only file system'), '')
})
