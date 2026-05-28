import { BarChart3, GitPullRequest, RefreshCw, ShieldCheck, Wrench } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { formatApiError } from "../../api";
import { JsonPanel, MetricCard, StatusBadge, compact } from "../../components/shared";
import { AiaskApi } from "../../services/aiaskApi";
import type { FactorFactoryStatus, ToolEnvelope } from "../../types";

function splitList(value: string): string[] {
  return value
    .split(/[,\n]/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function intentId(envelope: ToolEnvelope | null): string {
  const data = envelope?.data && typeof envelope.data === "object" ? (envelope.data as Record<string, unknown>) : {};
  const intent = data.intent && typeof data.intent === "object" ? (data.intent as Record<string, unknown>) : {};
  return String(intent.intent_id || "");
}

export function FactorFactoryPanel({
  endpoint,
  apiToken,
  controlToken
}: {
  endpoint: string;
  apiToken: string;
  controlToken: string;
}) {
  const api = useMemo(() => new AiaskApi({ endpoint, apiToken, controlToken }), [apiToken, controlToken, endpoint]);
  const [status, setStatus] = useState<FactorFactoryStatus | null>(null);
  const [codes, setCodes] = useState("600519, 000001, 000858");
  const [engines, setEngines] = useState("llm_primary, gp_classic, rule_seed");
  const [candidateCount, setCandidateCount] = useState("10");
  const [generations, setGenerations] = useState("2");
  const [intentEnvelope, setIntentEnvelope] = useState<ToolEnvelope | null>(null);
  const [message, setMessage] = useState("NOT_LOADED");
  const [busy, setBusy] = useState(false);

  async function refresh() {
    setBusy(true);
    try {
      const payload = await api.factorFactoryStatus(80);
      setStatus(payload);
      setMessage("FACTOR_FACTORY_LOADED");
    } catch (error) {
      setMessage(formatApiError(error));
    } finally {
      setBusy(false);
    }
  }

  async function createRunIntent() {
    setBusy(true);
    try {
      const envelope = await api.factorFactoryRunIntent({
        codes: splitList(codes),
        engines: splitList(engines),
        candidate_count: Number(candidateCount || 10),
        evolution_generations: Number(generations || 2)
      });
      setIntentEnvelope(envelope);
      setMessage(envelope.success ? "FACTOR_RUN_INTENT_CREATED" : envelope.error || "FACTOR_RUN_INTENT_FAILED");
    } catch (error) {
      setMessage(formatApiError(error));
    } finally {
      setBusy(false);
    }
  }

  async function createMaintenanceIntent() {
    setBusy(true);
    try {
      const envelope = await api.factorFactoryMaintenanceIntent({});
      setIntentEnvelope(envelope);
      setMessage(envelope.success ? "FACTOR_MAINTENANCE_INTENT_CREATED" : envelope.error || "FACTOR_MAINTENANCE_INTENT_FAILED");
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

  const factory = status?.factory || {};
  const activeFactors = status?.active_factors || [];
  const poolHealth = status?.pool_health || {};
  const engineHealth = status?.engine_health || {};
  const createdIntent = intentId(intentEnvelope);

  return (
    <div className="capability-stack">
      <div className="capability-banner">
        <div>
          <span>因子挖掘工厂</span>
          <h2>因子池、引擎健康和受控挖掘周期</h2>
          <p>运行与维护控制会创建持久化审批意图；确认后的执行仍然留在 Agent facade 内。</p>
        </div>
        <div className="header-actions">
          <StatusBadge status={message.startsWith("AIASK_") ? message : status?.status || "not_loaded"} label={message} />
          <button className="small-button" disabled={busy} onClick={refresh} type="button">
            <RefreshCw size={14} className={busy ? "spin" : ""} />
            刷新
          </button>
        </div>
      </div>

      {!controlToken.trim() && (
        <div className="notice warn">
          <ShieldCheck size={15} />
          创建因子工厂审批意图需要控制令牌。
        </div>
      )}

      <div className="diagnostics-summary wide">
        <MetricCard label="状态" value={status?.status || "-"} status={status?.status} />
        <MetricCard label="池规模" value={compact(factory.pool_size)} status="ready" />
        <MetricCard label="运行次数" value={compact(factory.run_count)} status="ready" />
        <MetricCard label="活跃因子" value={activeFactors.length} status={activeFactors.length ? "ready" : "not_loaded"} />
      </div>

      <section className="capability-grid two">
        <article className="capability-section">
          <div className="section-header">
            <div>
              <span>受控动作</span>
              <h3>挖掘周期意图</h3>
            </div>
            <GitPullRequest size={18} />
          </div>
          <label className="field-row">
            <span>代码</span>
            <textarea value={codes} onChange={(event) => setCodes(event.target.value)} />
          </label>
          <label className="field-row">
            <span>引擎</span>
            <input value={engines} onChange={(event) => setEngines(event.target.value)} />
          </label>
          <div className="quant-form-grid">
            <label className="field-row">
              <span>候选数</span>
              <input value={candidateCount} onChange={(event) => setCandidateCount(event.target.value)} />
            </label>
            <label className="field-row">
              <span>进化代数</span>
              <input value={generations} onChange={(event) => setGenerations(event.target.value)} />
            </label>
          </div>
          <div className="button-row">
            <button className="primary-button" disabled={busy || !controlToken.trim()} onClick={createRunIntent} type="button">
              <BarChart3 size={15} />
              创建运行意图
            </button>
            <button className="small-button" disabled={busy || !controlToken.trim()} onClick={createMaintenanceIntent} type="button">
              <Wrench size={14} />
              创建维护意图
            </button>
          </div>
          {createdIntent && (
            <div className="notice ok">
              <strong>{createdIntent}</strong>
              <span>请在 Agent 意图检查器中确认此意图后执行。</span>
            </div>
          )}
        </article>

        <article className="capability-section">
          <div className="section-header">
            <div>
              <span>健康状态</span>
              <h3>引擎与池状态</h3>
            </div>
            <StatusBadge status={status?.status || "not_loaded"} />
          </div>
          <div className="kv-grid">
            <span>已初始化</span>
            <strong>{compact(factory.initialized)}</strong>
            <span>已加载</span>
            <strong>{compact(factory.pool_loaded_from_db)}</strong>
            <span>已晋升</span>
            <strong>{compact(poolHealth.active_promoted_count)}</strong>
            <span>隔离</span>
            <strong>{compact(poolHealth.quarantine_count)}</strong>
          </div>
          <JsonPanel value={{ engineHealth, poolHealth }} />
        </article>
      </section>

      <section className="capability-section">
        <div className="section-header">
          <div>
            <span>{activeFactors.length} 个因子</span>
            <h3>活跃池</h3>
          </div>
          <StatusBadge status={activeFactors.length ? "ready" : "not_loaded"} />
        </div>
        <div className="mini-list">
          {activeFactors.slice(0, 20).map((factor, index) => (
            <article key={String(factor.factor_id || factor.id || index)}>
              <strong>{String(factor.name || factor.factor_id || factor.id || `factor-${index + 1}`)}</strong>
              <span>{String(factor.family || factor.generation_engine || factor.status || "factor")}</span>
              <p>{compact(factor.validation_summary || factor.fitness || factor.quality_score)}</p>
            </article>
          ))}
          {!activeFactors.length && <p className="muted">当前快照尚未加载活跃因子。</p>}
        </div>
      </section>

      <details className="raw-details">
        <summary>原始因子工厂数据</summary>
        <JsonPanel value={{ status, intentEnvelope }} />
      </details>
    </div>
  );
}
