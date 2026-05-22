import { CalendarClock, Play, Plus, RefreshCw, Trash2 } from "lucide-react";
import { FormEvent, useEffect, useMemo, useState } from "react";
import { formatApiError } from "../../api";
import { JsonPanel, StatusBadge, compact } from "../../components/shared";
import { AiaskApi } from "../../services/aiaskApi";

function jobId(job: Record<string, unknown>): string {
  return String(job.job_id || job.id || "");
}

export function AutomationWorkspace({
  endpoint,
  apiToken,
  controlToken,
  userId
}: {
  endpoint: string;
  apiToken: string;
  controlToken: string;
  userId?: string;
}) {
  const api = useMemo(() => new AiaskApi({ endpoint, apiToken, controlToken }), [apiToken, controlToken, endpoint]);
  const [jobs, setJobs] = useState<Array<Record<string, unknown>>>([]);
  const [selected, setSelected] = useState<Record<string, unknown> | null>(null);
  const [name, setName] = useState("Daily research monitor");
  const [prompt, setPrompt] = useState("Review the latest market data and summarize any risk alerts.");
  const [schedule, setSchedule] = useState("*/30 * * * *");
  const [intervalSeconds, setIntervalSeconds] = useState("");
  const [enabled, setEnabled] = useState(true);
  const [toolset, setToolset] = useState("finance_safe");
  const [result, setResult] = useState<unknown>(null);
  const [message, setMessage] = useState("NOT_LOADED");
  const [busy, setBusy] = useState(false);

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

  async function createJob(event: FormEvent) {
    event.preventDefault();
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
    setBusy(true);
    try {
      const payload = await api.jobUpdate(id, { enabled: !job.enabled });
      setResult(payload);
      setMessage("JOB_UPDATED");
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
    setBusy(true);
    try {
      const payload = await api.jobRun(id);
      setResult(payload);
      setMessage(payload.success ? "JOB_RUN_COMPLETED" : payload.error || "JOB_RUN_FAILED");
      await refresh();
    } catch (error) {
      setMessage(formatApiError(error));
    } finally {
      setBusy(false);
    }
  }

  async function deleteJob(job: Record<string, unknown>) {
    const id = jobId(job);
    if (!id) return;
    setBusy(true);
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
          <span>Automation</span>
          <h1>Jobs, schedules, and manual runs</h1>
        </div>
        <div className="header-actions">
          <StatusBadge status={message.startsWith("AIASK_") ? message : "ready"} label={message} />
          <button className="small-button" disabled={busy} onClick={refresh} type="button">
            <RefreshCw size={14} className={busy ? "spin" : ""} />
            Refresh
          </button>
        </div>
      </header>

      <div className="capabilities-body">
        <div className="capability-stack">
          <div className="capability-banner">
            <div>
              <span>{jobs.length} jobs</span>
              <h2>Scheduled Agent work</h2>
              <p>Jobs run through the Agent runtime and keep their run IDs and responses in local state.</p>
            </div>
            <StatusBadge status={jobs.length ? "ready" : "not_loaded"} label={jobs.length ? "configured" : "empty"} />
          </div>

          <section className="capability-grid two">
            <form className="capability-section" onSubmit={createJob}>
              <div className="section-header">
                <div>
                  <span>Create</span>
                  <h3>Automation job</h3>
                </div>
                <Plus size={18} />
              </div>
              <label className="field-row">
                <span>Name</span>
                <input value={name} onChange={(event) => setName(event.target.value)} />
              </label>
              <label className="field-row">
                <span>Prompt</span>
                <textarea value={prompt} onChange={(event) => setPrompt(event.target.value)} />
              </label>
              <div className="quant-form-grid">
                <label className="field-row">
                  <span>Cron</span>
                  <input value={schedule} onChange={(event) => setSchedule(event.target.value)} placeholder="*/30 * * * *" />
                </label>
                <label className="field-row">
                  <span>Interval seconds</span>
                  <input value={intervalSeconds} onChange={(event) => setIntervalSeconds(event.target.value)} placeholder="optional" />
                </label>
                <label className="field-row">
                  <span>Toolset</span>
                  <select value={toolset} onChange={(event) => setToolset(event.target.value)}>
                    <option value="finance_safe">finance_safe</option>
                    <option value="general_full">general_full</option>
                  </select>
                </label>
                <label className="field-row checkbox-row">
                  <span>Enabled</span>
                  <input checked={enabled} onChange={(event) => setEnabled(event.target.checked)} type="checkbox" />
                </label>
              </div>
              <button className="primary-button" disabled={busy || !name.trim() || !prompt.trim()} type="submit">
                <CalendarClock size={15} />
                Create job
              </button>
            </form>

            <section className="capability-section">
              <div className="section-header">
                <div>
                  <span>Recent result</span>
                  <h3>Run output</h3>
                </div>
                <StatusBadge status={result ? "ready" : "not_loaded"} />
              </div>
              <JsonPanel value={result || { status: "no_action" }} />
            </section>
          </section>

          <section className="capability-section">
            <div className="section-header">
              <div>
                <span>Configured jobs</span>
                <h3>List and controls</h3>
              </div>
              <StatusBadge status={jobs.length ? "ready" : "not_loaded"} />
            </div>
            <div className="mini-list">
              {jobs.map((job) => (
                <article className="job-row" key={jobId(job)}>
                  <div>
                    <strong>{String(job.name || jobId(job))}</strong>
                    <span>{String(job.schedule || job.interval_seconds || "manual")} | {compact(job.last_run_at || "never run")}</span>
                  </div>
                  <StatusBadge status={job.enabled ? "ready" : "disabled"} label={job.enabled ? "enabled" : "paused"} />
                  <div className="row-actions">
                    <button className="small-button" disabled={busy} onClick={() => setSelected(job)} type="button">Inspect</button>
                    <button className="small-button" disabled={busy} onClick={() => toggleJob(job)} type="button">
                      {job.enabled ? "Pause" : "Resume"}
                    </button>
                    <button className="small-button" disabled={busy} onClick={() => runJob(job)} type="button">
                      <Play size={13} />
                      Run
                    </button>
                    <button className="small-button danger" disabled={busy} onClick={() => deleteJob(job)} type="button">
                      <Trash2 size={13} />
                      Delete
                    </button>
                  </div>
                </article>
              ))}
              {!jobs.length && <p className="muted">No jobs are configured yet.</p>}
            </div>
          </section>

          <details className="raw-details">
            <summary>Selected job</summary>
            <JsonPanel value={selected || { status: "not_selected" }} />
          </details>
        </div>
      </div>
    </section>
  );
}
