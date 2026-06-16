let jobs: Array<Record<string, unknown>> = [
  {
    job_id: "job_mock_research",
    name: "每日研究监控",
    prompt: "复盘 mock 市场数据。",
    schedule: "*/30 * * * *",
    enabled: true,
    user_id: "local",
    last_run_at: null
  }
];

export function mockJobsData(): Array<Record<string, unknown>> {
  return jobs;
}

export function mockJobsList() {
  return { object: "list", data: jobs };
}

export function mockJobCreate(body: Record<string, unknown>, defaultUserId: unknown) {
  const job = {
    job_id: `job_mock_${jobs.length + 1}`,
    enabled: body.enabled ?? true,
    user_id: body.user_id || defaultUserId,
    ...body
  };
  jobs = [job, ...jobs];
  return { object: "aiask.job", job };
}

export function mockJobRuns(jobId: string) {
  return {
    object: "list",
    job_id: jobId,
    data: [
      {
        job_run_id: `jobrun_${jobId}`,
        job_id: jobId,
        status: "completed",
        response_id: "resp_mock",
        run_id: "run_mock",
        duration_ms: 15,
        started_at: "2026-05-22T09:00:00Z",
        finished_at: "2026-05-22T09:00:01Z"
      }
    ]
  };
}

export function mockJobRun(jobId: string) {
  return { run_id: `run_${jobId}`, job_id: jobId, output_text: "mock job run" };
}

export function mockJobUpdate(jobId: string, body: Record<string, unknown>) {
  jobs = jobs.map((job) => String(job.job_id) === jobId ? { ...job, ...body } : job);
  return { object: "aiask.job", job: jobs.find((job) => String(job.job_id) === jobId) };
}

export function mockJobDelete(jobId: string) {
  jobs = jobs.filter((job) => String(job.job_id) !== jobId);
  return { object: "aiask.job_deleted", deleted: true, job_id: jobId };
}
