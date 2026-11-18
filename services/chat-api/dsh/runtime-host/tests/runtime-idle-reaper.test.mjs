import assert from 'node:assert/strict'
import test from 'node:test'

import { RuntimeIdleReaper } from '../src/runtime-idle-reaper.mjs'

test('reaps idle leases and preserves an active request', async () => {
  const removed = []
  const reaper = new RuntimeIdleReaper({
    idleMs: 1000, intervalMs: 60_000,
    onIdle: async entry => { removed.push(entry.id); reaper.delete(entry) },
  })
  try {
    const idle = { id: 'idle' }
    const active = { id: 'active' }
    reaper.add(idle)
    reaper.add(active)
    let release
    const task = reaper.use(active, () => new Promise(resolve => { release = resolve }))
    await reaper.sweep(Date.now() + 2000)
    assert.deepEqual(removed, ['idle'])
    release()
    await task
    await reaper.sweep(Date.now() + 2000)
    assert.deepEqual(removed, ['idle', 'active'])
  } finally { reaper.stop() }
})

test('capacity pressure reclaims only an old idle runtime, never an active request', async () => {
  const removed=[]
  const reaper=new RuntimeIdleReaper({idleMs:900000,onIdle:async e=>{removed.push(e.id);reaper.delete(e)}})
  const old={id:'old'},busy={id:'busy'}
  reaper.add(old); reaper.add(busy)
  let release
  const work=reaper.use(busy,()=>new Promise(resolve=>{release=resolve}))
  try {
    assert.equal(await reaper.reclaimOne(Date.now()+61000),true)
    assert.deepEqual(removed,['old'])
    assert.equal(await reaper.reclaimOne(Date.now()+61000),false)
  } finally {release();await work;reaper.stop()}
})

test('live policy can disable both idle and capacity-pressure reclaim and enable them again', async () => {
  let configured = 0
  const removed = []
  const reaper = new RuntimeIdleReaper({
    idleMs: 900_000, readIdleMs: async () => configured,
    onIdle: async entry => { removed.push(entry.id); reaper.delete(entry) },
  })
  reaper.add({ id: 'resident' })
  try {
    const later = Date.now() + 1_000_000
    await reaper.sweep(later)
    assert.equal(await reaper.reclaimOne(later), false)
    assert.deepEqual(removed, [])
    configured = 900_000
    await reaper.sweep(later)
    assert.deepEqual(removed, ['resident'])
  } finally { reaper.stop() }
})
