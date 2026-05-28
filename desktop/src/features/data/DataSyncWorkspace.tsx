import { Database, GitPullRequest, Play, RefreshCw, ShieldCheck } from "lucide-react";
import { FormEvent, useEffect, useMemo, useState } from "react";
import { formatApiError } from "../../api";
import { JsonPanel, MetricCard, StatusBadge, compact } from "../../components/shared";
import { AiaskApi } from "../../services/aiaskApi";
import type { DesktopDataStatus, DesktopDataSyncPlan, ToolEnvelope } from "../../types";

function splitList(value: string): string[] {
  return value
    .split(/[,\n]/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function intentIdFromEnvelope(envelope: ToolEnvelope | null): string {
  const data = envelope?.data && typeof envelope.data === "object" ? (envelope.data as Record<string, unknown>) : {};
  const intent = data.intent && typeof data.intent === "object" ? (data.intent as Record<string, unknown>) : {};
  return String(intent.intent_id || "");
}

export function DataSyncWorkspace({
  endpoint,
  apiToken,
  controlToken
}: {
  endpoint: string;
  apiToken: string;
  controlToken: string;
}) {
  const api = useMemo(() => new AiaskApi({ endpoint, apiToken, controlToken }), [apiToken, controlToken, endpoint]);
  const [codes, setCodes] = useState("600519, 000001, 000858");
  const [maxStaleDays, setMaxStaleDays] = useState("5");
  const [taskType, setTaskType] = useState("kline");
  const [period, setPeriod] = useState("daily");
  const [dataStatus, setDataStatus] = useState<DesktopDataStatus | null>(null);
  const [plan, setPlan] = useState<DesktopDataSyncPlan | null>(null);
  const [intentEnvelope, setIntentEnvelope] = useState<ToolEnvelope | null>(null);
  const [syncIntents, setSyncIntents] = useState<Array<Record<string, unknown>>>([]);
  const [message, setMessage] = useState("NOT_LOADED");
  const [busy, setBusy] = useState(false);

  async function refresh() {
    setBusy(true);
    try {
      const payload = await api.dataStatus({ codes: splitList(codes), max_stale_days: Number(maxStaleDays || 5) });
      setDataStatus(payload);
      try {
        const intents = await api.intentsList(undefined, 30);
        setSyncIntents((intents.data || []).filter((item) => String(item.action || "").startsWith("data_sync.")));
      } catch {
        setSyncIntents([]);
      }
      setMessage("DATA_STATUS_LOADED");
    } catch (error) {
      setMessage(formatApiError(error));
    } finally {
      setBusy(false);
    }
  }

  async function generatePlan(event?: FormEvent) {
    event?.preventDefault();
    setBusy(true);
    try {
      const payload = await api.dataSyncPlan({
        codes: splitList(codes),
        max_stale_days: Number(maxStaleDays || 5),
        task_type: taskType,
        period
      });
      setPlan(payload);
      setDataStatus(payload.data_status || null);
      setMessage("SYNC_PLAN_READY");
    } catch (error) {
      setMessage(formatApiError(error));
    } finally {
      setBusy(false);
    }
  }

  async function createIntent() {
    if (!plan?.intent_request || !controlToken.trim()) return;
    setBusy(true);
    try {
      const envelope = await api.factoryIntentCreate(
        plan.intent_request.action,
        plan.intent_request.params,
        plan.intent_request.rationale || "Create data sync approval from Desktop."
      );
      setIntentEnvelope(envelope);
      await refresh();
      setMessage(envelope.success ? "SYNC_INTENT_CREATED" : envelope.error || "SYNC_INTENT_FAILED");
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

  const database = dataStatus?.database || {};
  const freshnessRecord =
    dataStatus?.freshness && typeof dataStatus.freshness === "object" ? (dataStatus.freshness as Record<string, unknown>) : {};
  const intentId = intentIdFromEnvelope(intentEnvelope);

  return (
    <section className="quant-workspace">
      <header className="quant-header">
        <div>
          <span>数据与同步</span>
          <h1>数据库质量与同步审批</h1>
        </div>
        <div className="header-actions">
          <StatusBadge status={message.startsWith("AIASK_") ? message : dataStatus?.status || "not_loaded"} label={message} />
          <button className="small-button" disabled={busy} onClick={refresh} type="button">
            <RefreshCw size={14} className={busy ? "spin" : ""} />
            刷新
          </button>
        </div>
      </header>

      <div className="quant-body data-sync-layout">
        <form className="quant-params-panel" onSubmit={generatePlan}>
          <div className="section-header">
            <div>
              <span>同步范围</span>
              <h3>计划生成器</h3>
            </div>
            <Database size={18} />
          </div>
          <label className="field-row">
            <span>证券代码</span>
            <textarea value={codes} onChange={(event) => setCodes(event.target.value)} />
          </label>
          <div className="quant-form-grid">
            <label className="field-row">
              <span>最大过期天数</span>
              <input value={maxStaleDays} onChange={(event) => setMaxStaleDays(event.target.value)} />
            </label>
            <label className="field-row">
              <span>任务类型</span>
              <select value={taskType} onChange={(event) => setTaskType(event.target.value)}>
                <option value="kline">kline</option>
                <option value="quote">quote</option>
                <option value="financial">financial</option>
                <option value="core_market">core_market</option>
                <option value="factor_context">factor_context</option>
              </select>
            </label>
            <label className="field-row">
              <span>周期</span>
              <select value={period} onChange={(event) => setPeriod(event.target.value)}>
                <option value="daily">daily</option>
                <option value="weekly">weekly</option>
                <option value="monthly">monthly</option>
              </select>
            </label>
          </div>
          <button className="primary-button" disabled={busy || !splitList(codes).length} type="submit">
            <Play size={15} />
            生成同步计划
          </button>
          {!controlToken.trim() && (
            <div className="notice warn compact-notice">
              <ShieldCheck size={14} />
              需要控制令牌后，同步计划才能创建为审批意图。
            </div>
          )}
        </form>

        <section className="quant-center-panel">
          <div className="diagnostics-summary wide">
            <MetricCard label="闸门" value={dataStatus?.status || "-"} status={dataStatus?.status} />
            <MetricCard label="代码" value={dataStatus?.codes?.length || splitList(codes).length} status="ready" />
            <MetricCard label="缺失" value={dataStatus?.missing_count ?? "-"} status={(dataStatus?.missing_count || 0) > 0 ? "failed" : "ready"} />
            <MetricCard label="过期" value={dataStatus?.stale_count ?? "-"} status={(dataStatus?.stale_count || 0) > 0 ? "partial" : "ready"} />
          </div>

          <section className="capability-section">
            <div className="section-header">
              <div>
                <span>SQLite / AKShare</span>
                <h3>数据库就绪状态</h3>
              </div>
              <StatusBadge status={database.writable === false ? "failed" : "ready"} />
            </div>
            <div className="kv-grid">
              <span>后端</span>
              <strong>{compact(database.backend)}</strong>
              <span>可写</span>
              <strong>{compact(database.writable)}</strong>
              <span>路径</span>
              <strong>{compact(database.path)}</strong>
              <span>来源</span>
              <strong>{compact(database.sources)}</strong>
            </div>
          </section>

          <section className="capability-section">
            <div className="section-header">
              <div>
                <span>新鲜度</span>
                <h3>质量闸门证据</h3>
              </div>
              <StatusBadge status={dataStatus?.quality_gate?.success ? "ready" : "partial"} />
            </div>
            <JsonPanel value={freshnessRecord || dataStatus?.quality_gate || { status: "not_loaded" }} />
          </section>
        </section>

        <section className="quant-report-panel">
          <div className="section-header">
            <div>
              <span>审批</span>
              <h3>同步意图</h3>
            </div>
            <GitPullRequest size={18} />
          </div>
          {plan ? (
            <>
              <div className="kv-grid">
                <span>动作</span>
                <strong>{plan.intent_request.action}</strong>
                <span>任务</span>
                <strong>{compact(plan.intent_request.params.task_type)}</strong>
                <span>周期</span>
                <strong>{compact(plan.intent_request.params.period)}</strong>
                <span>代码</span>
                <strong>{Array.isArray(plan.intent_request.params.codes) ? plan.intent_request.params.codes.length : "-"}</strong>
              </div>
              <button className="primary-button" disabled={busy || !controlToken.trim()} onClick={createIntent} type="button">
                <GitPullRequest size={15} />
                创建审批意图
              </button>
              {intentId && (
                <div className="notice ok">
                  <strong>{intentId}</strong>
                  <span>请在 Agent 意图检查器中复核并确认这个意图。</span>
                </div>
              )}
              <details className="raw-details" open>
                <summary>同步计划</summary>
                <JsonPanel value={{ plan, intentEnvelope }} />
              </details>
            </>
          ) : (
            <div className="empty-mini">
              <GitPullRequest size={24} />
              <span>请先生成同步计划，再创建审批意图。</span>
            </div>
          )}
          <div className="mini-list compact-list">
            <div className="section-header">
              <div>
                <span>{syncIntents.length} 条</span>
                <h3>同步审批历史</h3>
              </div>
            </div>
            {syncIntents.slice(0, 6).map((intent) => (
              <article className="job-row compact" key={String(intent.intent_id)}>
                <div>
                  <strong>{String(intent.action || "data_sync")}</strong>
                  <span>{compact(intent.updated_at || intent.created_at || "-")}</span>
                </div>
                <StatusBadge status={String(intent.status || "ready")} label={String(intent.status || "-")} />
              </article>
            ))}
            {!syncIntents.length && <p className="muted">暂无同步审批历史。</p>}
          </div>
        </section>
      </div>
    </section>
  );
}
