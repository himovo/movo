import assert from 'node:assert/strict'
import {
  formatScheduledWallTime,
  instantToPickerValue,
  pickerValueToWallDateTime,
} from '../src/components/scheduled-tasks/scheduledTaskTime'

const localNine = new Date(2026, 8, 5, 9, 15, 30).getTime()
assert.equal(pickerValueToWallDateTime(localNine), '2026-09-05T09:15:30')

const persistedWall = instantToPickerValue('2026-09-05T09:15:30', 'America/New_York')
assert.ok(persistedWall)
assert.equal(new Date(persistedWall!).getHours(), 9, 'a wall time is not shifted by the browser timezone')

const newYorkInstant = instantToPickerValue('2026-09-05T13:15:30Z', 'America/New_York')
assert.ok(newYorkInstant)
assert.equal(new Date(newYorkInstant!).getHours(), 9, 'a legacy instant is displayed in the task timezone')

assert.match(formatScheduledWallTime('2026-09-05T09:15:30', 'en-US'), /09:15/)
console.log('scheduled task time tests passed')
