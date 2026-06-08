import { BrainCircuit, FileText, Play, RefreshCw, Save, Square } from "lucide-react";
import { useMemo, useState } from "react";
import { formatApiError } from "../../api";
import { JsonPanel, StatusBadge, compact, confirmAction } from "../../components/shared";
import { AiaskApi } from "../../services/aiaskApi";
import type { LearningProposal, RlRun } from "../../types";

export function LearningRlPanel({ apiToken, controlToken, endpoint }: { apiToken: string; controlToken: string; endpoint: string }) {
  const api = useMemo(() => new AiaskApi({ endpoint, apiToken, controlToken }), [apiToken, controlToken, endpoint]);
  const [learningStatus, setLearningStatus] = useState<unknown>(null);
  const [proposals, setProposals] = useState<LearningProposal[]>([]);
  const [rlEnvironments, setRlEnvironments] = useState<unknown>(null);
  const [rlConfig, setRlConfig] = useState<unknown>(null);
  const [configDraft, setConfigDraft] = useState("{}");
  const [rlRuns, setRlRuns] = useState<RlRun[]>([]);
  const [selectedEnvironment, setSelectedEnvironment] = useState("");
  const [result, setResult] = useState<unknown>(null);
  const [runArtifact, setRunArtifact] = useState<unknown>(null);
  const [message, setMessage] = useState("NOT_LOADED");
  const [busy, setBusy] = useState(false);

  async function refresh() {
    setBusy(true);
    try {
      const [learning, review, envs, config, runs] = await Promise.all([
        api.learningStatus(),
        api.learningReview(undefined, 50),
        api.rlEnvironments(),
        api.rlConfig(),
        api.rlRuns(50)
      ]);
      setLearningStatus(learning);
      setProposals(review.data || []);
      setRlEnvironments(envs.data || envs);
      setRlConfig(config);
      setConfigDraft(JSON.stringify((config as { data?: unknown })?.data || config || {}, null, 2));
      setRlRuns(runs.data || []);
      setMessage("LEARNING_RL_LOADED");
    } catch (error) {
      setMessage(formatApiError(error));
    } finally {
      setBusy(false);
    }
  }

  async function applyProposal(proposalId: string) {
    if (!confirmAction("应用学习建议", `Proposal: ${proposalId}`)) return;
    setBusy(true);
    setMessage("LEARNING_PROPOSAL_APPLY_RUNNING");
    try {
      setResult(await api.learningApply(proposalId));
      setMessage("LEARNING_PROPOSAL_APPLIED");
      await refresh();
    } catch (error) {
      setMessage(formatApiError(error));
    } finally {
      setBusy(false);
    }
  }

  async function startRun() {
    if (!confirmAction("启动 RL 训练", `Environment: ${selectedEnvironment || "默认环境"}`)) return;
    setBusy(true);
    setMessage("RL_RUN_STARTING");
    try {
      setResult(await api.rlRunStart(selectedEnvironment || undefined, {}));
      setMessage("RL_RUN_STARTED");
      await refresh();
    } catch (error) {
      setMessage(formatApiError(error));
    } finally {
      setBusy(false);
    }
  }

  async function saveConfig() {
    if (!confirmAction("保存 RL 配置", "将更新 Agent 侧 RL 配置。")) return;
    setBusy(true);
    setMessage("RL_CONFIG_SAVING");
    try {
      const parsed = JSON.parse(configDraft || "{}") as Record<string, unknown>;
      setResult(await api.rlConfigUpdate(parsed));
      setMessage("RL_CONFIG_SAVED");
      await refresh();
    } catch (error) {
      setMessage(error instanceof SyntaxError ? "RL_CONFIG_JSON_INVALID" : formatApiError(error));
    } finally {
      setBusy(false);
    }
  }

  async function loadRunArtifact(runId: string, kind: "detail" | "results" | "logs") {
    setBusy(true);
    try {
      const payload =
        kind === "detail"
          ? await api.rlRunGet(runId)
          : kind === "results"
            ? await api.rlRunResults(runId)
            : await api.rlRunLogs(runId);
      setRunArtifact({ kind, run_id: runId, payload });
      setResult(payload);
      setMessage(`RL_RUN_${kind.toUpperCase()}_LOADED`);
    } catch (error) {
      setMessage(formatApiError(error));
      setRunArtifact({ kind, run_id: runId, success: false, error: formatApiError(error) });
    } finally {
      setBusy(false);
    }
  }

  async function stopRun(runId: string) {
    if (!confirmAction("停止 RL 运行", `Run: ${runId}`)) return;
    setBusy(true);
    setMessage("RL_RUN_STOPPING");
    try {
      setResult(await api.rlRunStop(runId));
      setMessage("RL_RUN_STOPPED");
      await refresh();
    } catch (error) {
      setMessage(formatApiError(error));
    } finally {
      setBusy(false);
    }
  }

  const envList = Array.isArray(rlEnvironments) ? rlEnvironments : Array.isArray((rlEnvironments as { environments?: unknown[] } | null)?.environments) ? (rlEnvironments as { environments: unknown[] }).environments : [];

  return (
    <div className="capability-stack">
      <div className="capability-banner">
        <div>
          <BrainCircuit size={20} />
          <span>学习 / RL</span>
          <h2>学习建议与 RL 训练控制台</h2>
          <p>展示学习建议、应用状态、RL 环境、配置、运行记录和结果入口。</p>
        </div>
        <div className="status-cluster">
          <StatusBadge status={message.startsWith("AIASK_") ? "gated" : "ready"} label={message} />
          <button className="small-button" disabled={busy} onClick={refresh} type="button">
            <RefreshCw size={14} className={busy ? "spin" : ""} />
            刷新
          </button>
        </div>
      </div>

      <section className="capability-grid two">
        <div className="capability-section">
          <div className="section-header">
            <h3>RL 配置</h3>
            <StatusBadge status={rlConfig ? "ready" : "not_loaded"} />
          </div>
          <label className="field-row">
            <span>JSON 配置</span>
            <textarea value={configDraft} onChange={(event) => setConfigDraft(event.target.value)} />
          </label>
          <button className="small-button" disabled={busy || !controlToken.trim()} onClick={saveConfig} type="button">
            <Save size={14} />
            保存配置
          </button>
        </div>

        <div className="capability-section">
          <div className="section-header"><h3>学习建议</h3><StatusBadge status={proposals.length ? "ready" : "not_loaded"} label={`${proposals.length} 条`} /></div>
          <div className="mini-list">
            {proposals.map((proposal, index) => {
              const id = String(proposal.proposal_id || proposal.id || index);
              return (
                <article className="job-row" key={id}>
                  <div>
                    <strong>{proposal.title || id}</strong>
                    <span>{compact(proposal.status || proposal.summary || "-")}</span>
                  </div>
                  <button className="small-button" disabled={busy || !id} onClick={() => applyProposal(id)} type="button">应用</button>
                </article>
              );
            })}
            {!proposals.length && <p className="muted">暂无学习建议。</p>}
          </div>
        </div>

        <div className="capability-section">
          <div className="section-header"><h3>RL 运行</h3><StatusBadge status={rlRuns.length ? "ready" : "not_loaded"} label={`${rlRuns.length} 次`} /></div>
          <label className="field-row">
            <span>环境</span>
            <select value={selectedEnvironment} onChange={(event) => setSelectedEnvironment(event.target.value)}>
              <option value="">默认环境</option>
              {envList.map((env, index) => {
                const name = typeof env === "string" ? env : String((env as Record<string, unknown>)?.name || (env as Record<string, unknown>)?.id || index);
                return <option key={name} value={name}>{name}</option>;
              })}
            </select>
          </label>
          <button className="primary-button" disabled={busy} onClick={startRun} type="button">
            <Play size={14} />
            启动训练
          </button>
          <div className="mini-list">
            {rlRuns.map((run, index) => {
              const id = String(run.run_id || index);
              return (
                <article className="job-row" key={id}>
                  <div>
                    <strong>{run.environment || id}</strong>
                    <span>{compact(run.status || "-")}</span>
                  </div>
                  <div className="row-actions">
                    <button className="small-button" disabled={busy || !run.run_id} onClick={() => loadRunArtifact(String(run.run_id), "detail")} type="button">
                      <FileText size={13} />
                      详情
                    </button>
                    <button className="small-button" disabled={busy || !run.run_id} onClick={() => loadRunArtifact(String(run.run_id), "results")} type="button">结果</button>
                    <button className="small-button" disabled={busy || !run.run_id} onClick={() => loadRunArtifact(String(run.run_id), "logs")} type="button">日志</button>
                    <button className="small-button" disabled={busy || !run.run_id} onClick={() => stopRun(String(run.run_id))} type="button">
                      <Square size={13} />
                      停止
                    </button>
                  </div>
                </article>
              );
            })}
          </div>
        </div>
      </section>

      <details className="raw-details">
        <summary>状态、配置与结果</summary>
        <JsonPanel value={{ learningStatus, rlEnvironments, rlConfig, rlRuns, runArtifact, result }} />
      </details>
    </div>
  );
}
