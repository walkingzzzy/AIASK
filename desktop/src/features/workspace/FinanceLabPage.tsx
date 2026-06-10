import {
  ArrowRight,
  BarChart3,
  Database,
  Factory,
  FlaskConical,
  GitBranch,
  Landmark,
  LineChart,
  Radio,
  RefreshCw,
  ShieldCheck
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { formatApiError } from "../../api";
import { MetricCard, RawEvidencePanel, StatusBadge, compact } from "../../components/shared";
import { AiaskApi } from "../../services/aiaskApi";
import type { CapabilityWorkbenchPayload, FactorFactoryStatus, MainView, ToolEnvelope } from "../../types";

const financeTemplates: Array<{
  id: MainView;
  title: string;
  label: string;
  description: string;
  icon: typeof Landmark;
}> = [
  {
    id: "financial-manager",
    title: "组合与风险",
    label: "财务管理",
    description: "组合、关注列表、风险检查和受控执行入口。",
    icon: Landmark
  },
  {
    id: "quant",
    title: "研究运行",
    label: "量化研究",
    description: "创建结构化研究运行，并复核生成的研究报告。",
    icon: LineChart
  },
  {
    id: "strategy-factory",
    title: "策略生成",
    label: "策略工厂",
    description: "生成、评审并通过安全门控管理策略候选。",
    icon: Factory
  },
  {
    id: "factor-factory",
    title: "因子挖掘",
    label: "因子工厂",
    description: "挖掘因子，查看活跃池和引擎健康状态。",
    icon: BarChart3
  },
  {
    id: "incubation",
    title: "孵化生命周期",
    label: "孵化工厂",
    description: "复核命中率、生命周期阶段和晋升准备度。",
    icon: FlaskConical
  },
  {
    id: "data",
    title: "数据准备度",
    label: "数据",
    description: "检查数据新鲜度、同步计划和运行前置状态。",
    icon: Database
  },
  {
    id: "factory-events",
    title: "工厂事件",
    label: "事件工厂",
    description: "创建、预览、审批并复核工厂事件和雷达任务。",
    icon: Radio
  }
];

type RelayStatus = "ready" | "partial" | "failed" | "not_loaded";

interface RelayState {
  capabilities: CapabilityWorkbenchPayload | null;
  factor: FactorFactoryStatus | null;
  incubation: (ToolEnvelope & { data: Record<string, unknown> }) | null;
  events: (ToolEnvelope & { data: Record<string, unknown> }) | null;
}

interface RelayItem {
  id: "factor" | "strategy" | "incubation";
  title: string;
  subtitle: string;
  status: RelayStatus;
  evidence: Array<{ label: string; value: string | number }>;
  blocker: string;
  nextAction: string;
  target: MainView;
}

function recordFromUnknown(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, unknown>) : {};
}

function arrayFromUnknown(value: unknown): unknown[] {
  return Array.isArray(value) ? value : [];
}

function statusFromSuccess(success?: boolean, rawStatus?: unknown): RelayStatus {
  if (success === false) return "failed";
  const normalized = String(rawStatus || (success ? "ready" : "not_loaded")).toLowerCase();
  if (["ready", "implemented", "passed", "completed", "success"].includes(normalized)) return "ready";
  if (["partial", "degraded", "in_progress", "running", "queued", "reviewing"].includes(normalized)) return "partial";
  if (["failed", "error", "blocked", "missing", "unconfigured"].includes(normalized)) return "failed";
  return rawStatus || success ? "partial" : "not_loaded";
}

function firstString(...values: unknown[]): string {
  for (const value of values) {
    if (typeof value === "string" && value.trim()) return value;
    if (value !== null && value !== undefined && typeof value !== "object") return String(value);
  }
  return "-";
}

function latestStrategyReview(strategyFactory?: CapabilityWorkbenchPayload["strategy_factory"]) {
  const data = recordFromUnknown(strategyFactory?.review_snapshot?.data);
  return recordFromUnknown(arrayFromUnknown(data.reviews)[0]);
}

function latestStrategyRun(strategyFactory?: CapabilityWorkbenchPayload["strategy_factory"]) {
  const data = recordFromUnknown(strategyFactory?.runs?.data);
  return recordFromUnknown(arrayFromUnknown(data.runs)[0]);
}

function latestFactoryEvent(events: RelayState["events"]) {
  const data = recordFromUnknown(events?.data);
  return recordFromUnknown(arrayFromUnknown(data.events)[0]);
}

function relayStatus(items: RelayItem[]): RelayStatus {
  if (items.some((item) => item.status === "failed")) return "failed";
  if (items.some((item) => item.status === "partial" || item.status === "not_loaded")) return "partial";
  return "ready";
}

function buildRelayItems(state: RelayState): RelayItem[] {
  const factorFactory = state.factor?.factory || {};
  const activeFactors = state.factor?.active_factors || [];
  const promotedCount = Number(recordFromUnknown(state.factor?.pool_health).active_promoted_count || 0);
  const factorReady = statusFromSuccess(undefined, state.factor?.status);
  const factorStatus: RelayStatus = factorReady === "ready" && !activeFactors.length ? "partial" : factorReady;

  const strategyFactory = state.capabilities?.strategy_factory;
  const strategyStatusData = recordFromUnknown(strategyFactory?.status?.data);
  const strategyReview = latestStrategyReview(strategyFactory);
  const strategyRun = latestStrategyRun(strategyFactory);
  const event = latestFactoryEvent(state.events);
  const reviewDecision = firstString(strategyReview.decision, strategyReview.status);
  const strategyStatus = statusFromSuccess(strategyFactory?.status?.success, strategyStatusData.status || strategyReview.status || strategyRun.status);

  const incubationData = recordFromUnknown(state.incubation?.data);
  const incubationReport = recordFromUnknown(incubationData.report);
  const reportSummary = recordFromUnknown(incubationReport.summary);
  const errorCount = Number(incubationData.error_count || 0);
  const incubationStatus = statusFromSuccess(
    state.incubation?.success,
    errorCount > 0 ? "failed" : incubationData.last_result_status || incubationData.status
  );

  return [
    {
      id: "factor",
      title: "因子工厂",
      subtitle: "挖掘与治理活跃池",
      status: factorStatus,
      evidence: [
        { label: "活跃池", value: compact(factorFactory.pool_size) },
        { label: "活跃因子", value: activeFactors.length },
        { label: "已晋升", value: Number.isFinite(promotedCount) ? promotedCount : "-" },
        { label: "代表因子", value: firstString(activeFactors[0]?.name, activeFactors[0]?.factor_id) }
      ],
      blocker:
        factorStatus === "ready"
          ? ""
          : activeFactors.length
            ? "因子状态不是 ready，需要复核引擎健康或隔离池。"
            : "尚未看到活跃因子，策略工厂缺少可复用的因子证据。",
      nextAction: factorStatus === "ready" ? "查看因子池" : "维护或运行因子工厂",
      target: "factor-factory"
    },
    {
      id: "strategy",
      title: "策略工厂",
      subtitle: "候选生成、评审与孵化分流",
      status: strategyStatus,
      evidence: [
        { label: "最近运行", value: firstString(strategyRun.run_id, strategyStatusData.last_run_id) },
        { label: "候选数", value: compact(strategyRun.candidates || strategyStatusData.candidate_count || strategyStatusData.run_count) },
        { label: "评审策略", value: firstString(strategyReview.strategy_id, event.strategy_id) },
        { label: "评审决策", value: reviewDecision }
      ],
      blocker:
        strategyStatus === "ready"
          ? ""
          : "策略状态或评审快照不可用，需要刷新能力中心并检查策略工厂接口。",
      nextAction: reviewDecision.includes("incubate") || reviewDecision.includes("promote") ? "打开策略评审" : "刷新策略工厂",
      target: "strategy-factory"
    },
    {
      id: "incubation",
      title: "孵化工厂",
      subtitle: "生命周期、命中率与反馈",
      status: incubationStatus,
      evidence: [
        { label: "运行次数", value: compact(incubationData.run_count) },
        { label: "错误数", value: errorCount },
        { label: "最近结果", value: firstString(incubationData.last_result_status, incubationData.status) },
        { label: "孵化中", value: compact(reportSummary.total_incubating) }
      ],
      blocker:
        incubationStatus === "ready"
          ? ""
          : errorCount > 0
            ? "孵化运行存在错误，需要检查生命周期事件和命中率报告。"
            : "孵化状态尚未加载，无法证明策略已进入观察或晋升反馈环。",
      nextAction: incubationStatus === "ready" ? "查看孵化看板" : "检查孵化状态",
      target: "incubation"
    }
  ];
}

export function FinanceLabPage({
  apiToken,
  controlToken,
  endpoint,
  onOpenView
}: {
  apiToken: string;
  controlToken?: string;
  endpoint: string;
  onOpenView: (view: MainView) => void;
}) {
  const api = useMemo(() => new AiaskApi({ endpoint, apiToken, controlToken }), [apiToken, controlToken, endpoint]);
  const [relay, setRelay] = useState<RelayState>({ capabilities: null, factor: null, incubation: null, events: null });
  const [message, setMessage] = useState("NOT_LOADED");
  const [busy, setBusy] = useState(false);

  async function refreshRelay() {
    setBusy(true);
    try {
      const [capabilities, factor, incubation, events] = await Promise.all([
        api.capabilities(),
        api.factorFactoryStatus(20),
        api.incubationFactoryStatus(),
        api.strategyDomainEvents({ event_type: "factory.run_completed", limit: 5 })
      ]);
      setRelay({ capabilities, factor, incubation, events });
      setMessage("FACTORY_RELAY_LOADED");
    } catch (error) {
      setMessage(formatApiError(error));
    } finally {
      setBusy(false);
    }
  }

  useEffect(() => {
    refreshRelay().catch(() => undefined);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [endpoint, apiToken, controlToken]);

  const relayItems = buildRelayItems(relay);
  const overallStatus = relayStatus(relayItems);
  const blockers = relayItems.filter((item) => item.blocker);
  const source = relay.capabilities?.summary.source || (endpoint.startsWith("mock://") ? "mock_fixture" : "live_backend");

  return (
    <section className="capabilities-workspace optimization-page">
      <header className="capabilities-header">
        <div>
          <span>金融任务</span>
          <h1>金融实验室</h1>
          <p>把金融工作作为任务模板启动；结果回到当前线程，沉淀为产物、审批项和运行摘要。</p>
        </div>
        <div className="header-actions">
          <StatusBadge status={source} label={source === "mock_fixture" ? "Mock 数据" : "Agent HTTP"} />
          <StatusBadge status={message.startsWith("AIASK_") ? message : overallStatus} label={message} />
          <button className="small-button" disabled={busy} onClick={refreshRelay} type="button">
            <RefreshCw size={14} className={busy ? "spin" : ""} />
            刷新接力状态
          </button>
        </div>
      </header>

      <div className="capabilities-body">
        <div className="capability-stack">
          <section className="capability-banner finance-relay-banner">
            <div>
              <span>Factor -&gt; Strategy -&gt; Incubation</span>
              <h2>工厂接力总览</h2>
              <p>只读汇总 Agent HTTP 证据：因子池是否可用、策略评审是否给出分流、孵化器是否已经产生生命周期和命中率反馈。</p>
            </div>
            <GitBranch size={20} />
          </section>

          <div className="diagnostics-summary wide">
            <MetricCard label="接力状态" value={overallStatus} status={overallStatus} />
            <MetricCard label="活跃因子" value={relay.factor?.active_factors?.length || 0} status={relay.factor?.active_factors?.length ? "ready" : "not_loaded"} />
            <MetricCard label="策略评审" value={latestStrategyReview(relay.capabilities?.strategy_factory).decision ? "可见" : "未加载"} status={latestStrategyReview(relay.capabilities?.strategy_factory).decision ? "ready" : "not_loaded"} />
            <MetricCard label="孵化运行" value={compact(recordFromUnknown(relay.incubation?.data).run_count)} status={relay.incubation?.success ? "ready" : "not_loaded"} />
          </div>

          <section className="finance-relay-grid" aria-label="工厂接力总览">
            {relayItems.map((item, index) => (
              <article className={`capability-section finance-relay-card ${item.status}`} key={item.id}>
                <div className="section-header">
                  <div>
                    <span>{item.subtitle}</span>
                    <h3>{item.title}</h3>
                  </div>
                  <StatusBadge status={item.status} />
                </div>
                <div className="kv-grid relay-kv-grid">
                  {item.evidence.map((row) => (
                    <div className="relay-evidence-row" key={row.label}>
                      <span>{row.label}</span>
                      <strong>{row.value}</strong>
                    </div>
                  ))}
                </div>
                {item.blocker ? (
                  <div className="notice warn">
                    <ShieldCheck size={15} />
                    {item.blocker}
                  </div>
                ) : (
                  <div className="notice ok">
                    <ShieldCheck size={15} />
                    当前证据足以进入下一段复核。
                  </div>
                )}
                <button className="small-button" onClick={() => onOpenView(item.target)} type="button">
                  {item.nextAction}
                  <ArrowRight size={14} />
                </button>
                {index < relayItems.length - 1 && <ArrowRight className="relay-arrow" size={18} aria-hidden="true" />}
              </article>
            ))}
          </section>

          <section className="capability-section">
            <div className="section-header">
              <div>
                <span>{blockers.length ? `${blockers.length} 个待处理点` : "接力闭环"}</span>
                <h3>下一步</h3>
              </div>
              <StatusBadge status={blockers.length ? "partial" : "ready"} />
            </div>
            <div className="mini-list">
              {(blockers.length ? blockers : relayItems).map((item) => (
                <article className="capability-row" key={item.id}>
                  <div>
                    <span>{item.title}</span>
                    <strong>{item.blocker || item.nextAction}</strong>
                  </div>
                  <button className="small-button" onClick={() => onOpenView(item.target)} type="button">
                    打开{item.title}
                  </button>
                </article>
              ))}
            </div>
          </section>

          <RawEvidencePanel title="工厂接力原始证据" value={relay} />

          <div className="optimization-grid">
            {financeTemplates.map((template) => {
              const Icon = template.icon;
              return (
                <button
                  aria-label={template.label}
                  className="optimization-card action-card"
                  key={template.id}
                  onClick={() => onOpenView(template.id)}
                  type="button"
                >
                  <Icon size={18} />
                  <span>{template.label}</span>
                  <h2>{template.title}</h2>
                  <p>{template.description}</p>
                </button>
              );
            })}
          </div>
        </div>
      </div>
    </section>
  );
}
