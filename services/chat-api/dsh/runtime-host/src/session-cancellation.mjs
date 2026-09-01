const LIVE_JOB_STATUSES = new Set(['running', 'stopping'])

/** Cancel one official DSH agent turn and every background job it owns. */
export async function cancelSessionWork(ctx, agent, cause = 'cancelled') {
  const jobs = ctx.jobs.list(agent).filter(job => LIVE_JOB_STATUSES.has(job.status))
  for (const job of jobs) {
    if (job.status === 'running') ctx.jobs.kill(job.id, agent, cause)
  }
  agent.cancel({ kind: 'user' })
  const settled = await Promise.all(jobs.map(job => ctx.jobs.wait(job.id, 5_000, agent)))
  return {
    accepted: true,
    jobs: settled.map(job => ({ id: String(job.id), status: job.status, detail: job.detail })),
    jobsPending: settled.some(job => LIVE_JOB_STATUSES.has(job.status)),
  }
}
