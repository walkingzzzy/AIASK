import { CalendarClock, Play, Plus, RefreshCw, Trash2 } from "lucide-react";
import { FormEvent, useEffect, useMemo, useState } from "react";
import { formatApiError } from "../../api";
import { JsonPanel, StatusBadge, compact, confirmAction } from "../../components/shared";
import { AiaskApi } from "../../services/aiaskApi";
import type { JobRunRecord } from "../../types";

function jobId(job: Record<string, unknown>): string {
  return String(job.job_id || job.id || "");
}

function testIdPart(value: unknown): string {
  return String(value || "unknown")
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9_-]+/g, "-")
    .replace(/^-+|-+$/g, "") || "unknown";
}

export function AutomationWorkspace({
  endpoint,
  apiToken,
  controlToken,
  userId,
  management = false
}: {
  endpoint: string;
  apiToken: string;
  controlToken: string;
  userId?: string;
  management?: boolean;
}) {
  const api = useMemo(() => new AiaskApi({ endpoint, apiToken, controlToken }), [apiToken, controlToken, endpoint]);
  const [jobs, setJobs] = useState<Array<Record<string, unknown>>>([]);
  const [selected, setSelected] = useState<Record<string, unknown> | null>(null);
  const [name, setName] = useState("每日研究监控");
  const [prompt, setPrompt] = useState("复盘最新市场数据，并总结需要关注的风险提醒。");
  const [schedule, setSchedule] = useState("*/30 * * * *");
  const [intervalSeconds, setIntervalSeconds] = useState("");
  const [enabled, setEnabled] = useState(true);
  const [toolset, setToolset] = useState("finance_safe");
  const [result, setResult] = useState<unknown>(null);
  const [jobRuns, setJobRuns] = useState<JobRunRecord[]>([]);
  const [message, setMessage] = useState("NOT_LOADED");
  const [runsMessage, setRunsMessage] = useState("RUNS_NOT_LOADED");
  const [busy, setBusy] = useState(false);
  const [runningJobIds, setRunningJobIds] = useState<string[]>([]);

  async function refresh() {
    setBusy(true);
    try {
      const payload = await api.jobsList();
      setJobs(payload.data || []);
      setMessage("JOBS_LOADED");
    } catch (error) {
      setMessage(formatApiError(error));
    } finally {
      setBusy(false);
    }
  }

  async function loadJobRuns(job: Record<string, unknown>) {
    const id = jobId(job);
    if (!id) return;
    setSelected(job);
    try {
      const payload = await api.jobRuns(id, 20);
      setJobRuns(payload.data || []);
      setRunsMessage("JOB_RUNS_LOADED");
    } catch (error) {
      setJobRuns([]);
      setRunsMessage(formatApiError(error));
    }
  }

  async function createJob(event: FormEvent) {
    event.preventDefault();
    if (!confirmAction("创建自动化任务", `任务：${name || "未命名"}\n工具集：${toolset}`)) return;
    setBusy(true);
    try {
      const payload = await api.jobCreate({
        name,
        prompt,
        schedule: intervalSeconds.trim() ? undefined : schedule,
        interval_seconds: intervalSeconds.trim() ? Number(intervalSeconds) : undefined,
        toolset,
        enabled,
        user_id: userId || undefined
      });
      setResult(payload);
      setMessage("JOB_CREATED");
      await refresh();
    } catch (error) {
      setMessage(formatApiError(error));
    } finally {
      setBusy(false);
    }
  }

  async function toggleJob(job: Record<string, unknown>) {
    const id = jobId(job);
    if (!id) return;
    const nextEnabled = !job.enabled;
    if (!confirmAction(nextEnabled ? "恢复自动化任务" : "暂停自动化任务", `任务：${String(job.name || id)}`)) return;
    setBusy(true);
    setMessage(nextEnabled ? "JOB_RESUME_RUNNING" : "JOB_PAUSE_RUNNING");
    try {
      const payload = await api.jobUpdate(id, { enabled: nextEnabled });
      setResult(payload);
      setMessage(nextEnabled ? "JOB_RESUMED" : "JOB_PAUSED");
      await refresh();
    } catch (error) {
      setMessage(formatApiError(error));
    } finally {
      setBusy(false);
    }
  }

  async function runJob(job: Record<string, unknown>) {
    const id = jobId(job);
    if (!id) return;
    if (!confirmAction("运行自动化任务", `任务：${String(job.name || id)}`)) return;
    setRunningJobIds((items) => Array.from(new Set([...items, id])));
    setMessage("JOB_RUN_RUNNING");
    const runPromise = api.jobRun(id);
    const timeoutPromise = new Promise<null>((resolve) => window.setTimeout(() => resolve(null), 45000));
    const finish = async (payload: Awaited<ReturnType<typeof api.jobRun>>) => {
      setResult(payload);
      setMessage(payload.success ? "JOB_RUN_COMPLETED" : payload.error || "JOB_RUN_FAILED");
      await refresh();
      await loadJobRuns(job);
    };
    try {
      const payload = await Promise.race([runPromise, timeoutPromise]);
      if (payload === null) {
        setMessage("JOB_RUN_STILL_RUNNING");
        runPromise
          .then((completed) => finish(completed))
          .catch((error) => setMessage(formatApiError(error)))
          .finally(() => setRunningJobIds((items) => items.filter((item) => item !== id)));
        return;
      }
      await finish(payload);
    } catch (error) {
      setMessage(formatApiError(error));
    } finally {
      setRunningJobIds((items) => items.filter((item) => item !== id));
    }
  }

  async function deleteJob(job: Record<string, unknown>) {
    const id = jobId(job);
    if (!id) return;
    if (!confirmAction("删除自动化任务", `任务：${String(job.name || id)}\n删除后将从任务列表移除。`)) return;
    setBusy(true);
    setMessage("JOB_DELETE_RUNNING");
    try {
      const payload = await api.jobDelete(id);
      setResult(payload);
      setSelected(null);
      setMessage("JOB_DELETED");
      await refresh();
    } catch (error) {
      setMessage(formatApiError(error));
    } finally {
      setBusy(false);
    }
  }

  useEffect(() => {
    refresh().catch(() => undefined);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [endpoint, apiToken]);

  return (
    <section className="capabilities-workspace">
      <header className="capabilities-header">
        <div>
          <span>自动化</span>
          <h1>{management ? "自动化管理" : "AI 自动化任务"}</h1>
        </div>
        <div className="header-actions">
          <StatusBadge status={message.startsWith("AIASK_") ? message : "ready"} label={message} />
          <button className="small-button" disabled={busy} onClick={refresh} type="button">
            <RefreshCw size={14} className={busy ? "spin" : ""} />
            刷新
          </button>
        </div>
      </header>

      <div className="capabilities-body">
        <div className="capability-stack">
          <div className="capability-banner">
            <div>
              <span>{jobs.length} 个任务</span>
              <h2>{management ? "计划中的 Agent 工作" : "让 AI 定期替你完成重复任务"}</h2>
              <p>
                {management
                  ? "这里用于管理高级调度、工具集和删除操作。"
                  : "前台保留日常创建、运行、暂停和恢复；Cron、toolset 和删除操作放在设置的自动化管理中。"}
              </p>
            </div>
            <StatusBadge status={jobs.length ? "ready" : "not_loaded"} label={jobs.length ? "已配置" : "空"} />
          </div>

          <section className="capability-grid two">
            <form className="capability-section" onSubmit={createJob}>
              <div className="section-header">
                <div>
                  <span>创建</span>
                  <h3>自动化任务</h3>
                </div>
                <Plus size={18} />
              </div>
              <label className="field-row">
                <span>名称</span>
                <input value={name} onChange={(event) => setName(event.target.value)} />
              </label>
              <label className="field-row">
                <span>Prompt</span>
                <textarea value={prompt} onChange={(event) => setPrompt(event.target.value)} />
              </label>
              {management ? (
                <div className="quant-form-grid">
                  <label className="field-row">
                    <span>Cron</span>
                    <input value={schedule} onChange={(event) => setSchedule(event.target.value)} placeholder="*/30 * * * *" />
                  </label>
                  <label className="field-row">
                    <span>间隔秒数</span>
                    <input value={intervalSeconds} onChange={(event) => setIntervalSeconds(event.target.value)} placeholder="可选" />
                  </label>
                  <label className="field-row">
                    <span>工具集</span>
                    <select value={toolset} onChange={(event) => setToolset(event.target.value)}>
                      <option value="finance_safe">finance_safe</option>
                      <option value="general_full">general_full</option>
                    </select>
                  </label>
                  <label className="field-row checkbox-row">
                    <span>启用</span>
                    <input checked={enabled} onChange={(event) => setEnabled(event.target.checked)} type="checkbox" />
                  </label>
                </div>
              ) : (
                <div className="notice">
                  默认使用 finance_safe 工具集和 30 分钟检查节奏。需要 Cron、interval 或 toolset 时，请到设置中的自动化管理调整。
                </div>
              )}
              <button
                aria-label="创建任务"
                className="primary-button"
                disabled={busy || !name.trim() || !prompt.trim()}
                type="submit"
              >
                <CalendarClock size={15} />
                {management ? "创建任务" : "创建自动化"}
              </button>
            </form>

            <section className="capability-section">
              <div className="section-header">
                <div>
                  <span>最近结果</span>
                  <h3>运行输出</h3>
                </div>
                <StatusBadge status={result ? "ready" : "not_loaded"} />
              </div>
              {management ? (
                <JsonPanel value={result || { status: "no_action" }} />
              ) : (
                <p className="muted">
                  {result ? `最近操作已完成：${compact((result as Record<string, unknown>).status || (result as Record<string, unknown>).object || result)}` : "运行或创建自动化后，这里会显示摘要。"}
                </p>
              )}
            </section>
          </section>

          <section className="capability-section">
            <div className="section-header">
              <div>
                <span>已配置任务</span>
                <h3>列表与控制</h3>
              </div>
              <StatusBadge status={jobs.length ? "ready" : "not_loaded"} />
            </div>
            <div className="mini-list">
              {jobs.map((job) => (
                <article className="job-row" key={jobId(job)}>
                  {(() => {
                    const id = jobId(job);
                    const rowBusy = busy || runningJobIds.includes(id);
                    const jobLabel = String(job.name || id || "unnamed job");
                    const jobTestId = testIdPart(id || jobLabel);
                    return (
                      <>
                  <div>
                    <strong>{jobLabel}</strong>
                    <span>{String(job.schedule || job.interval_seconds || "手动")} | {compact(job.last_run_at || "从未运行")}</span>
                  </div>
                  <StatusBadge status={job.enabled ? "ready" : "disabled"} label={job.enabled ? "已启用" : "已暂停"} />
                  <div className="row-actions">
                    <button aria-label={`查看任务 ${jobLabel}`} className="small-button" data-testid={`job-inspect-${jobTestId}`} disabled={rowBusy} onClick={() => loadJobRuns(job)} type="button">查看</button>
                    <button aria-label={`${job.enabled ? "暂停任务" : "恢复任务"} ${jobLabel}`} className="small-button" data-testid={`job-toggle-${jobTestId}`} disabled={rowBusy} onClick={() => toggleJob(job)} type="button">
                      {job.enabled ? "暂停" : "恢复"}
                    </button>
                    <button aria-label={`运行任务 ${jobLabel}`} className="small-button" data-testid={`job-run-${jobTestId}`} disabled={rowBusy} onClick={() => runJob(job)} type="button">
                      <Play size={13} />
                      {runningJobIds.includes(id) ? "运行中" : "运行"}
                    </button>
                    {management && (
                      <button aria-label={`删除任务 ${jobLabel}`} className="small-button danger" data-testid={`job-delete-${jobTestId}`} disabled={rowBusy} onClick={() => deleteJob(job)} type="button">
                        <Trash2 size={13} />
                        删除
                      </button>
                    )}
                  </div>
                      </>
                    );
                  })()}
                </article>
              ))}
              {!jobs.length && <p className="muted">尚未配置任务。</p>}
            </div>
          </section>

          {management ? (
            <details className="raw-details">
              <summary>已选任务</summary>
              <JsonPanel value={selected || { status: "not_selected" }} />
            </details>
          ) : (
            <section className="capability-section">
              <div className="section-header">
                <div>
                  <span>选中任务</span>
                  <h3>{selected ? String(selected.name || jobId(selected)) : "尚未选择"}</h3>
                </div>
                <StatusBadge status={selected ? "ready" : "not_loaded"} />
              </div>
              <p className="muted">
                {selected
                  ? `当前状态：${selected.enabled ? "已启用" : "已暂停"}；最近运行：${compact(selected.last_run_at || "从未运行")}。`
                  : "点击任务行的“查看”后，这里会显示日常复核摘要。"}
              </p>
              {selected && (
                <div className="mini-list compact-list">
                  <StatusBadge status={runsMessage.startsWith("AIASK_") ? "gated" : "ready"} label={runsMessage} />
                  {jobRuns.slice(0, 6).map((run, index) => (
                    <article className="job-row compact" key={run.job_run_id || run.run_id || run.response_id || `${run.job_id || "job"}-${index}`}>
                      <div>
                        <strong>{run.status}</strong>
                        <span>{compact(run.started_at || "-")} | {run.duration_ms ? `${run.duration_ms}ms` : "耗时待更新"}</span>
                        {run.error && <span className="text-red">{run.error}</span>}
                      </div>
                      <StatusBadge status={run.status === "completed" ? "ready" : run.status} label={run.run_id || run.response_id || run.job_run_id} />
                    </article>
                  ))}
                  {!jobRuns.length && <p className="muted">暂无任务执行记录。</p>}
                </div>
              )}
            </section>
          )}
        </div>
      </div>
    </section>
  );
}
