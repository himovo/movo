const LIVE_JOB_STATUSES = new Set(['running', 'stopping'])

async function waitForTurnToSettle(agent, timeoutMs = 4_000) {
  if (typeof agent.whenIdle !== 'function') return false
  let timer
  try {
    return await Promise.race([
      agent.whenIdle().then(() => true),
      new Promise(resolve => { timer = setTimeout(() => resolve(false), timeoutMs) }),
    ])
  } finally {
    if (timer !== undefined) clearTimeout(timer)
  }
}

/** Cancel one official DSH agent turn and every background job it owns. */
export async function cancelSessionWork(ctx, agent, cause = 'cancelled', turnTimeoutMs = 4_000) {
  const jobs = ctx.jobs.list(agent).filter(job => LIVE_JOB_STATUSES.has(job.status))
  for (const job of jobs) {
    if (job.status === 'running') ctx.jobs.kill(job.id, agent, cause)
  }
  agent.cancel({ kind: 'user' })
  const [settled, turnSettled] = await Promise.all([
    Promise.all(jobs.map(job => ctx.jobs.wait(job.id, turnTimeoutMs, agent))),
    waitForTurnToSettle(agent, turnTimeoutMs),
  ])
  return {
    accepted: true,
    jobs: settled.map(job => ({ id: String(job.id), status: job.status, detail: job.detail })),
    jobsPending: settled.some(job => LIVE_JOB_STATUSES.has(job.status)),
    turnPending: !turnSettled,
  }
}
