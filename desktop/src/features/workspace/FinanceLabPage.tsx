import {
  ArrowRight,
  BarChart3,
  CheckCircle2,
  Database,
  Factory,
  FlaskConical,
  GitBranch,
  Landmark,
  LineChart,
  Radio,
  RefreshCw,
  Settings2,
  ShieldCheck
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { formatApiError } from "../../api";
import { MetricCard, RawEvidencePanel, StatusBadge, compact } from "../../components/shared";
import { AiaskApi } from "../../services/aiaskApi";
import type {
  BrokerAnalyticsPayload,
  BrokerAnalyticsRecord,
  BrokerReadinessPayload,
  BrokerSnapshotPayload,
  BrokerSyncPayload,
  CapabilityWorkbenchPayload,
  FactorFactoryStatus,
  MainView,
  ToolEnvelope
} from "../../types";

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
  incubationEvents: (ToolEnvelope & { data: Record<string, unknown> }) | null;
  hitRateEvents: (ToolEnvelope & { data: Record<string, unknown> }) | null;
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

interface IncubationBlockerRow {
  id: string;
  reason: string;
  label: string;
  count?: number;
  strategyId?: string;
  nextAction?: string;
}

interface IncubationLifecycleRow {
  id: string;
  strategyId: string;
  strategyName: string;
  family: string;
  regime: string;
  stage: string;
  evidence: Record<string, unknown>;
  blockers: string[];
  nextAction: string;
}

interface BrokerState {
  readiness: BrokerReadinessPayload | null;
  snapshots: BrokerSnapshotPayload | null;
  analytics: BrokerAnalyticsPayload | null;
  sync: BrokerSyncPayload | null;
}

type BrokerProvider = "qmt" | "tonghuashun";

const brokerProviderOptions: Array<{
  provider: BrokerProvider;
  label: string;
  shortLabel: string;
  description: string;
  env: Array<{ name: string; label: string; required?: boolean; placeholder?: string }>;
}> = [
  {
    provider: "qmt",
    label: "QMT / MiniQMT",
    shortLabel: "QMT",
    description: "MiniQMT + XtQuant SDK，只读取账户、持仓和委托快照。",
    env: [
      { name: "QMT_PATH", label: "MiniQMT 安装路径", required: true, placeholder: "C:\\QMT\\bin.x64" },
      { name: "QMT_ACCOUNT", label: "资金账号", required: true, placeholder: "仅写入 Agent 启动环境" },
      { name: "QMT_ACCOUNT_TYPE", label: "账户类型", placeholder: "STOCK" },
      { name: "QMT_SESSION_ID", label: "会话 ID", placeholder: "可选" }
    ]
  },
  {
    provider: "tonghuashun",
    label: "同花顺",
    shortLabel: "同花顺",
    description: "同花顺桌面交易客户端 + easytrader，只读取资金、持仓、委托和成交。",
    env: [
      { name: "THS_CLIENT_PATH", label: "下单客户端路径", required: true, placeholder: "C:\\Program Files\\THS\\xiadan.exe" },
      { name: "THS_TRADE_ACCOUNT", label: "交易账号", placeholder: "仅写入 Agent 启动环境" },
      { name: "THS_BROKER", label: "券商适配器", placeholder: "ths" }
    ]
  }
];

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

function numberFromUnknown(value: unknown): number | null {
  if (value === null || value === undefined || value === "") return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function formatMoney(value: unknown): string {
  const parsed = numberFromUnknown(value);
  if (parsed === null) return "-";
  return parsed.toLocaleString("zh-CN", { maximumFractionDigits: 0 });
}

function formatPercent(value: unknown): string {
  const parsed = numberFromUnknown(value);
  if (parsed === null) return "-";
  return `${(parsed * 100).toFixed(1)}%`;
}

function analyticsFromBroker(state: BrokerState): BrokerAnalyticsRecord | null {
  return state.analytics?.data?.analytics || state.snapshots?.data?.analytics || state.readiness?.latest_analytics || null;
}

function connectorForProvider(readiness: BrokerReadinessPayload | null, provider: BrokerProvider) {
  const aliases = provider === "tonghuashun" ? ["tonghuashun", "ths"] : [provider];
  return (readiness?.connectors || []).find((connector) => aliases.includes(String(connector.provider || "").toLowerCase()));
}

function brokerProviderLabel(provider: BrokerProvider): string {
  return brokerProviderOptions.find((option) => option.provider === provider)?.label || provider;
}

function brokerEnvSnippet(provider: BrokerProvider): string {
  const option = brokerProviderOptions.find((item) => item.provider === provider) || brokerProviderOptions[0];
  const defaults: Record<string, string> = { QMT_ACCOUNT_TYPE: "STOCK", THS_BROKER: "ths" };
  return option.env.map((item) => `${item.name}=${defaults[item.name] || ""}`).join("\n");
}

function brokerTestEntryPath(connector: ReturnType<typeof connectorForProvider>): string {
  return firstString(recordFromUnknown(connector?.test_entry).path, "/v1/desktop/broker/sync");
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

function compactList(value: unknown): string[] {
  if (Array.isArray(value)) return value.map((item) => firstString(item)).filter(Boolean);
  if (typeof value === "string" && value.trim()) return [value];
  return [];
}

function eventPayloads(envelope: (ToolEnvelope & { data: Record<string, unknown> }) | null): Record<string, unknown>[] {
  const data = recordFromUnknown(envelope?.data);
  return arrayFromUnknown(data.events).map((event) => recordFromUnknown(event));
}

function incubationReportFromRelay(state: RelayState): Record<string, unknown> {
  const incubationData = recordFromUnknown(state.incubation?.data);
  const statusReport = recordFromUnknown(incubationData.report);
  if (statusReport.hit_rate_dashboard || statusReport.summary) return statusReport;
  const event = recordFromUnknown(eventPayloads(state.hitRateEvents)[0]);
  const payload = recordFromUnknown(event.payload);
  return payload.hit_rate_dashboard || payload.summary ? payload : {};
}

function incubationDashboard(report: Record<string, unknown>): Record<string, unknown> {
  return recordFromUnknown(report.hit_rate_dashboard);
}

function incubationBreakdownRows(
  report: Record<string, unknown>,
  dimension: "by_family" | "by_regime"
): Array<{ dimension: string; name: string; metrics: Record<string, unknown>; status: RelayStatus }> {
  const dashboard = incubationDashboard(report);
  const rows = Object.entries(recordFromUnknown(dashboard[dimension])).map(([name, metrics]) => {
    const metricRecord = recordFromUnknown(metrics);
    const blocked = Number(metricRecord.blocked_count || 0);
    const missing = Number(metricRecord.missing_forward_windows || 0);
    const lcb = numberFromUnknown(metricRecord.avg_skill_lcb) ?? 0;
    const status: RelayStatus = blocked > 0 || lcb < 0 ? "failed" : missing > 0 ? "partial" : "ready";
    return { dimension: dimension === "by_family" ? "family" : "regime", name, metrics: metricRecord, status };
  });
  return rows.sort((left, right) => {
    const leftDebt =
      Number(left.metrics.blocked_count || 0) + Number(left.metrics.missing_forward_windows || 0) - (numberFromUnknown(left.metrics.avg_skill_lcb) ?? 0);
    const rightDebt =
      Number(right.metrics.blocked_count || 0) + Number(right.metrics.missing_forward_windows || 0) - (numberFromUnknown(right.metrics.avg_skill_lcb) ?? 0);
    return rightDebt - leftDebt;
  });
}

function incubationBlockersFromRelay(state: RelayState): IncubationBlockerRow[] {
  const report = incubationReportFromRelay(state);
  const summary = recordFromUnknown(report.promotion_blocker_summary);
  const rows: IncubationBlockerRow[] = [];
  arrayFromUnknown(summary.top_blockers).forEach((item, index) => {
    const blocker = recordFromUnknown(item);
    const reason = firstString(blocker.reason_code, blocker.reason, blocker.code);
    if (!reason) return;
    rows.push({
      id: `summary:${reason}:${index}`,
      reason,
      label: firstString(blocker.label, blocker.message, reason),
      count: numberFromUnknown(blocker.count) ?? undefined,
      nextAction: firstString(blocker.next_action, blocker.nextAction)
    });
  });
  eventPayloads(state.incubationEvents).forEach((event) => {
    const payload = recordFromUnknown(event.payload);
    const evidence = recordFromUnknown(payload.evidence || payload.lifecycle_evidence);
    const strategyId = firstString(event.strategy_id, payload.strategy_id, evidence.strategy_id);
    const nextAction = firstString(payload.next_action, evidence.next_action);
    [
      ...compactList(payload.promotion_blockers),
      ...compactList(payload.blockers),
      ...compactList(payload.block_reasons),
      ...compactList(evidence.promotion_blockers),
      ...compactList(evidence.blockers),
      ...compactList(evidence.block_reasons)
    ].forEach((reason, index) => {
      rows.push({
        id: `event:${strategyId || event.id}:${reason}:${index}`,
        reason,
        label: reason,
        strategyId,
        nextAction
      });
    });
  });
  const merged = new Map<string, IncubationBlockerRow>();
  rows.forEach((row) => {
    const key = `${row.reason}:${row.strategyId || ""}`;
    const current = merged.get(key);
    merged.set(key, current ? { ...current, count: current.count ?? row.count, nextAction: current.nextAction || row.nextAction } : row);
  });
  return Array.from(merged.values());
}

function incubationLifecycleRowsFromRelay(state: RelayState): IncubationLifecycleRow[] {
  const report = incubationReportFromRelay(state);
  const rows: IncubationLifecycleRow[] = [];
  const push = (source: Record<string, unknown>, id: string, payload: Record<string, unknown> = {}) => {
    const strategyId = firstString(source.strategy_id, payload.strategy_id, id);
    rows.push({
      id,
      strategyId,
      strategyName: firstString(source.strategy_name, payload.strategy_name, source.name, strategyId),
      family: firstString(source.family, payload.family, "-"),
      regime: firstString(source.regime, payload.regime, "-"),
      stage: firstString(source.current_stage, source.stage, source.to_stage, payload.to_stage, source.lifecycle_state, "unknown"),
      evidence: source,
      blockers: [
        ...compactList(source.promotion_blockers),
        ...compactList(source.blockers),
        ...compactList(source.block_reasons),
        ...compactList(payload.promotion_blockers)
      ].filter((item, index, items) => items.indexOf(item) === index),
      nextAction: firstString(source.next_action, payload.next_action)
    });
  };
  arrayFromUnknown(report.lifecycle_evidence).forEach((item, index) => push(recordFromUnknown(item), `report:${index}`));
  eventPayloads(state.incubationEvents).forEach((event) => {
    const payload = recordFromUnknown(event.payload);
    push(recordFromUnknown(payload.evidence || payload.lifecycle_evidence || payload), firstString(event.id, event.event_id, `event:${rows.length}`), payload);
  });
  const merged = new Map<string, IncubationLifecycleRow>();
  rows.forEach((row) => {
    const current = merged.get(row.strategyId);
    merged.set(row.strategyId, current ? { ...current, ...row, blockers: [...current.blockers, ...row.blockers].filter((item, index, items) => items.indexOf(item) === index) } : row);
  });
  return Array.from(merged.values()).slice(0, 6);
}

function topIncubationBreakdownLabel(report: Record<string, unknown>): string {
  const rows = [...incubationBreakdownRows(report, "by_family"), ...incubationBreakdownRows(report, "by_regime")];
  const row = rows[0];
  if (!row) return "-";
  return `${row.dimension}:${row.name} hit ${formatPercent(row.metrics.hit_rate)} LCB ${firstString(row.metrics.avg_skill_lcb, "-")}`;
}

function relayStatus(items: RelayItem[]): RelayStatus {
  if (items.some((item) => item.status === "failed")) return "failed";
  if (items.some((item) => item.status === "partial" || item.status === "not_loaded")) return "partial";
  return "ready";
}

function relayMessageLabel(message: string): string {
  if (message === "FACTORY_RELAY_LOADED") return "接力状态已加载";
  if (message === "NOT_LOADED") return "等待加载";
  return message;
}

function relayMessageStatus(message: string): string {
  if (message === "FACTORY_RELAY_LOADED") return "ready";
  if (message === "NOT_LOADED") return "not_loaded";
  if (message.startsWith("AIASK_")) return "gated";
  return "failed";
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
  const incubationReport = incubationReportFromRelay(state);
  const reportSummary = recordFromUnknown(incubationReport.summary);
  const errorCount = Number(incubationData.error_count || 0);
  const incubationBlockers = incubationBlockersFromRelay(state);
  const lifecycleRows = incubationLifecycleRowsFromRelay(state);
  const baseIncubationStatus = statusFromSuccess(
    state.incubation?.success,
    errorCount > 0 ? "failed" : incubationData.last_result_status || incubationData.status
  );
  const incubationStatus: RelayStatus = baseIncubationStatus === "failed" ? "failed" : incubationBlockers.length ? "partial" : baseIncubationStatus;
  const topBlocker = incubationBlockers[0];
  const latestLifecycle = lifecycleRows[0];

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
        { label: "孵化中", value: compact(reportSummary.total_incubating) },
        { label: "Weak cell", value: topIncubationBreakdownLabel(incubationReport) },
        { label: "Top blocker", value: firstString(topBlocker?.reason, "-") },
        { label: "Lifecycle", value: latestLifecycle ? `${latestLifecycle.strategyId}:${latestLifecycle.stage}` : "-" }
      ],
      blocker:
        incubationStatus === "ready"
          ? ""
          : topBlocker
            ? `${topBlocker.label}${topBlocker.nextAction ? ` Next: ${topBlocker.nextAction}` : ""}`
          : errorCount > 0
            ? "孵化运行存在错误，需要检查生命周期事件和命中率报告。"
            : "孵化状态尚未加载，无法证明策略已进入观察或晋升反馈环。",
      nextAction: incubationStatus === "ready" ? "查看孵化看板" : firstString(topBlocker?.nextAction, "检查孵化状态"),
      target: "incubation"
    }
  ];
}

function IncubationActionWorklist({ relay }: { relay: RelayState }) {
  const report = incubationReportFromRelay(relay);
  const dashboard = incubationDashboard(report);
  const overall = recordFromUnknown(dashboard.overall);
  const breakdownRows = [...incubationBreakdownRows(report, "by_family"), ...incubationBreakdownRows(report, "by_regime")].slice(0, 6);
  const blockers = incubationBlockersFromRelay(relay).slice(0, 6);
  const lifecycleRows = incubationLifecycleRowsFromRelay(relay).slice(0, 6);

  return (
    <>
      <section className="capability-section">
        <div className="section-header">
          <div>
            <span>Incubation action worklist</span>
            <h3>Hit-rate evidence that needs review</h3>
          </div>
          <StatusBadge status={blockers.length ? "partial" : relay.incubation?.success ? "ready" : "not_loaded"} />
        </div>
        <div className="diagnostics-summary wide">
          <MetricCard label="Hit rate" value={formatPercent(overall.hit_rate)} status={numberFromUnknown(overall.hit_rate) ? "ready" : "not_loaded"} />
          <MetricCard label="Skill LCB" value={firstString(overall.avg_skill_lcb, "-")} status={(numberFromUnknown(overall.avg_skill_lcb) ?? 0) > 0 ? "ready" : "partial"} />
          <MetricCard label="Blocked strategies" value={blockers.length} status={blockers.length ? "partial" : "ready"} />
          <MetricCard label="Lifecycle rows" value={lifecycleRows.length} status={lifecycleRows.length ? "ready" : "not_loaded"} />
        </div>
      </section>

      <div className="capability-grid two">
        <section className="capability-section">
          <div className="section-header">
            <div>
              <span>Weak family/regime cells</span>
              <h3>Where hit-rate review is actionable</h3>
            </div>
            <BarChart3 size={18} />
          </div>
          <div className="mini-list">
            {breakdownRows.map((row) => (
              <article className={`capability-row ${row.status === "ready" ? "ok" : row.status === "failed" ? "bad" : "warn"}`} key={`${row.dimension}:${row.name}`}>
                <div>
                  <span>
                    {row.dimension} | n={compact(row.metrics.total_n || row.metrics.n || row.metrics.total_signals)}
                  </span>
                  <strong>{row.name}</strong>
                </div>
                <StatusBadge status={row.status} label={`hit ${formatPercent(row.metrics.hit_rate)}`} />
                <small>
                  LCB {firstString(row.metrics.avg_skill_lcb, "-")} | blocked {compact(row.metrics.blocked_count || 0)} | missing windows{" "}
                  {compact(row.metrics.missing_forward_windows || 0)} | ready {compact(row.metrics.promotion_ready_count || 0)}
                </small>
              </article>
            ))}
            {!breakdownRows.length && <p className="muted">No family or regime hit-rate breakdown is available.</p>}
          </div>
        </section>

        <section className="capability-section">
          <div className="section-header">
            <div>
              <span>Promotion blocker evidence</span>
              <h3>What blocks graduation now</h3>
            </div>
            <ShieldCheck size={18} />
          </div>
          <div className="mini-list">
            {blockers.map((blocker) => (
              <article className="capability-row warn" key={blocker.id}>
                <div>
                  <span>{blocker.strategyId || "all strategies"}</span>
                  <strong>{blocker.label}</strong>
                </div>
                <StatusBadge status="partial" label={blocker.reason} />
                <small>{blocker.nextAction || "Open the incubation panel and review lifecycle evidence."}</small>
              </article>
            ))}
            {!blockers.length && <p className="muted">No promotion blockers reported.</p>}
          </div>
        </section>
      </div>

      <section className="capability-section">
        <div className="section-header">
          <div>
            <span>Lifecycle evidence trail</span>
            <h3>Current strategy states with proof</h3>
          </div>
          <GitBranch size={18} />
        </div>
        <div className="mini-list">
          {lifecycleRows.map((row) => (
            <article className={`capability-row ${row.blockers.length ? "warn" : "ok"}`} key={row.id}>
              <div>
                <span>
                  {row.family} | {row.regime} | hit {formatPercent(row.evidence.hit_rate)} | LCB{" "}
                  {firstString(row.evidence.skill_lcb, "-")}
                </span>
                <strong>
                  {`${row.strategyName || row.strategyId} -> ${row.stage}`}
                </strong>
              </div>
              <StatusBadge status={row.blockers.length ? "partial" : "ready"} label={row.blockers[0] || "evidence_ready"} />
              <small>
                windows {compactList(row.evidence.forward_windows_completed).join("/") || "-"} | audit{" "}
                {firstString(recordFromUnknown(row.evidence.execution_audit).status, "-")} | next {row.nextAction || "review"}
              </small>
            </article>
          ))}
          {!lifecycleRows.length && <p className="muted">No lifecycle evidence events available.</p>}
        </div>
      </section>
    </>
  );
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
  const [relay, setRelay] = useState<RelayState>({
    capabilities: null,
    factor: null,
    incubation: null,
    events: null,
    incubationEvents: null,
    hitRateEvents: null
  });
  const [broker, setBroker] = useState<BrokerState>({ readiness: null, snapshots: null, analytics: null, sync: null });
  const [message, setMessage] = useState("NOT_LOADED");
  const [brokerMessage, setBrokerMessage] = useState("BROKER_NOT_LOADED");
  const [brokerProvider, setBrokerProvider] = useState<BrokerProvider>("qmt");
  const [brokerConsent, setBrokerConsent] = useState(false);
  const [busy, setBusy] = useState(false);
  const [brokerBusy, setBrokerBusy] = useState(false);

  async function refreshRelay() {
    setBusy(true);
    try {
      const [capabilities, factor, incubation, events, incubationEvents, hitRateEvents] = await Promise.all([
        api.capabilities(),
        api.factorFactoryStatus(20),
        api.incubationFactoryStatus(),
        api.strategyDomainEvents({ event_type: "factory.run_completed", limit: 5 }),
        api.strategyDomainEvents({ event_type: "incubation.stage_transitioned", limit: 12 }),
        api.strategyDomainEvents({ event_type: "incubation_factory.hit_rate_report_generated", limit: 3 })
      ]);
      setRelay({ capabilities, factor, incubation, events, incubationEvents, hitRateEvents });
      setMessage("FACTORY_RELAY_LOADED");
    } catch (error) {
      setMessage(formatApiError(error));
    } finally {
      setBusy(false);
    }
  }

  async function refreshBroker() {
    setBrokerBusy(true);
    try {
      const [readiness, snapshots, analytics] = await Promise.all([
        api.brokerReadiness(),
        api.brokerAccounts("local", brokerProvider),
        api.brokerAnalyticsLatest("local", brokerProvider)
      ]);
      setBroker((current) => ({ ...current, readiness, snapshots, analytics }));
      setBrokerMessage("BROKER_READONLY_LOADED");
    } catch (error) {
      setBrokerMessage(formatApiError(error));
    } finally {
      setBrokerBusy(false);
    }
  }

  async function syncBroker() {
    setBrokerBusy(true);
    try {
      const sync = await api.brokerSync({ provider: brokerProvider, consent: brokerConsent, user_id: "local" });
      const [snapshots, analytics] = await Promise.all([
        api.brokerAccounts("local", brokerProvider),
        api.brokerAnalyticsLatest("local", brokerProvider)
      ]);
      setBroker((current) => ({ ...current, sync, snapshots, analytics }));
      setBrokerMessage(sync.success ? "BROKER_SYNCED" : sync.error_code || "BROKER_SYNC_FAILED");
    } catch (error) {
      setBrokerMessage(formatApiError(error));
    } finally {
      setBrokerBusy(false);
    }
  }

  useEffect(() => {
    refreshRelay().catch(() => undefined);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [endpoint, apiToken, controlToken]);

  useEffect(() => {
    refreshBroker().catch(() => undefined);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [endpoint, apiToken, controlToken, brokerProvider]);

  const relayItems = buildRelayItems(relay);
  const overallStatus = relayStatus(relayItems);
  const blockers = relayItems.filter((item) => item.blocker);
  const source = relay.capabilities?.summary.source || (endpoint.startsWith("mock://") ? "mock_fixture" : "live_backend");
  const brokerConnectors = broker.readiness?.connectors || [];
  const activeBrokerConnector = connectorForProvider(broker.readiness, brokerProvider);
  const brokerData = broker.snapshots?.data || {};
  const brokerAnalytics = analyticsFromBroker(broker);
  const brokerMetrics = recordFromUnknown(brokerAnalytics?.metrics);
  const topPositions = arrayFromUnknown(brokerMetrics.top_positions);
  const riskFlags = Array.isArray(brokerAnalytics?.risk_flags) ? brokerAnalytics.risk_flags : [];
  const latestAccount = brokerData.accounts?.[0];
  const selectedBrokerOption = brokerProviderOptions.find((option) => option.provider === brokerProvider) || brokerProviderOptions[0];

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
          <StatusBadge status={relayMessageStatus(message)} label={relayMessageLabel(message)} technicalLabel={message} />
          <StatusBadge status={brokerMessage.toLowerCase()} label={brokerMessage} />
          <button className="small-button" disabled={busy} onClick={refreshRelay} type="button">
            <RefreshCw size={14} className={busy ? "spin" : ""} />
            刷新接力状态
          </button>
        </div>
      </header>

      <div className="capabilities-body">
        <div className="capability-stack">
          <section className="capability-section broker-readonly-panel" aria-label="Broker read-only behavior analytics">
            <div className="section-header">
              <div>
                <span>Broker Read-only</span>
                <h2>券商只读与行为分析</h2>
              </div>
              <div className="header-actions compact-actions">
                <StatusBadge status={broker.readiness?.status || "not_loaded"} />
                <StatusBadge status={broker.readiness?.read_only ? "read_only" : "not_loaded"} label="read_only" />
                <StatusBadge status="blocked" label="live_trading_disabled" />
                <button className="small-button" disabled={brokerBusy} onClick={refreshBroker} type="button">
                  <RefreshCw size={14} className={brokerBusy ? "spin" : ""} />
                  检查环境
                </button>
                <button className="small-button" disabled={brokerBusy || !brokerConsent} onClick={syncBroker} type="button">
                  <RefreshCw size={14} className={brokerBusy ? "spin" : ""} />
                  Sync {selectedBrokerOption.shortLabel} read-only
                </button>
              </div>
            </div>

            <div className="broker-wizard">
              <div className="broker-provider-tabs" role="tablist" aria-label="券商只读接入类型">
                {brokerProviderOptions.map((option) => {
                  const connector = connectorForProvider(broker.readiness, option.provider);
                  const active = brokerProvider === option.provider;
                  return (
                    <button
                      aria-selected={active}
                      className={`broker-provider-tab ${active ? "active" : ""}`}
                      key={option.provider}
                      onClick={() => setBrokerProvider(option.provider)}
                      role="tab"
                      type="button"
                    >
                      <span>{option.label}</span>
                      <strong>{option.description}</strong>
                      <StatusBadge status={connector?.ready ? "ready" : connector?.status || "not_loaded"} />
                    </button>
                  );
                })}
              </div>

              <div className="broker-wizard-grid">
                <div className="broker-subpanel">
                  <div className="section-header compact">
                    <div>
                      <span>step 1</span>
                      <h3>环境变量与依赖</h3>
                    </div>
                    <Settings2 size={16} />
                  </div>
                  <div className="broker-env-list">
                    {selectedBrokerOption.env.map((item) => {
                      const missing = activeBrokerConnector?.missing_env?.includes(item.name);
                      return (
                        <div className="relay-evidence-row" key={item.name}>
                          <span>{item.name}</span>
                          <strong>{missing ? "missing" : item.required ? "required" : "optional"}</strong>
                        </div>
                      );
                    })}
                  </div>
                  <pre className="env-block broker-env-block">{brokerEnvSnippet(brokerProvider)}</pre>
                  <div className="mini-list">
                    {(activeBrokerConnector?.environment_checks || [
                      "Install the broker desktop client on the same Windows host as the Agent.",
                      "Install the optional broker SDK in the Agent Python environment.",
                      "Register the financial MCP server that exposes read-only broker tools."
                    ]).map((check, index) => (
                      <article className="capability-row broker-check-row" key={`${check}-${index}`}>
                        <div>
                          <span>env_check</span>
                          <strong>{check}</strong>
                        </div>
                        <StatusBadge status={activeBrokerConnector?.ready ? "ready" : activeBrokerConnector?.status || "not_loaded"} />
                      </article>
                    ))}
                  </div>
                  <p className="muted">把变量加入 Agent 启动环境并重启；桌面端不会保存账号、路径或密钥值。</p>
                </div>

                <div className="broker-subpanel">
                  <div className="section-header compact">
                    <div>
                      <span>step 2</span>
                      <h3>授权说明</h3>
                    </div>
                    <ShieldCheck size={16} />
                  </div>
                  <div className="mini-list">
                    {(activeBrokerConnector?.authorization_notes || [
                      "只读同步需要显式授权。",
                      "账户标识会在 Agent 侧哈希化。",
                      "实盘下单与撤单保持禁用。"
                    ]).map((note, index) => (
                      <article className="capability-row broker-check-row" key={`${note}-${index}`}>
                        <div>
                          <span>read_only</span>
                          <strong>{note}</strong>
                        </div>
                        <CheckCircle2 size={15} />
                      </article>
                    ))}
                  </div>
                  <label className="checkbox-row broker-consent-row">
                    <input checked={brokerConsent} onChange={(event) => setBrokerConsent(event.target.checked)} type="checkbox" />
                    <span>我确认本次只读测试可读取 {brokerProviderLabel(brokerProvider)} 账户、持仓、委托和成交快照用于分析。</span>
                  </label>
                </div>

                <div className="broker-subpanel">
                  <div className="section-header compact">
                    <div>
                      <span>step 3</span>
                      <h3>只读测试入口</h3>
                    </div>
                    <StatusBadge status={activeBrokerConnector?.ready ? "ready" : activeBrokerConnector?.status || "not_loaded"} />
                  </div>
                  <div className="broker-test-entry">
                    <div className="relay-evidence-row">
                      <span>provider</span>
                      <strong>{brokerProvider}</strong>
                    </div>
                    <div className="relay-evidence-row">
                      <span>route</span>
                      <strong>{brokerTestEntryPath(activeBrokerConnector)}</strong>
                    </div>
                    <div className="relay-evidence-row">
                      <span>consent</span>
                      <strong>{brokerConsent ? "granted" : "required"}</strong>
                    </div>
                  </div>
                  <button className="primary-button" disabled={brokerBusy || !brokerConsent} onClick={syncBroker} type="button">
                    <RefreshCw size={14} className={brokerBusy ? "spin" : ""} />
                    运行只读测试并生成分析
                  </button>
                </div>
              </div>
            </div>

            <div className="diagnostics-summary wide broker-summary">
              <MetricCard label="Total asset" value={formatMoney(brokerMetrics.total_asset || latestAccount?.total_asset)} status={latestAccount ? "ready" : "not_loaded"} />
              <MetricCard label="Cash ratio" value={formatPercent(brokerMetrics.cash_ratio)} status={numberFromUnknown(brokerMetrics.cash_ratio) !== null ? "ready" : "not_loaded"} />
              <MetricCard label="Positions" value={Number(brokerMetrics.position_count || brokerData.positions?.length || 0)} status={brokerData.positions?.length ? "ready" : "not_loaded"} />
              <MetricCard label="Risk flags" value={riskFlags.length} status={riskFlags.length ? "warning" : "ready"} />
            </div>

            <div className="broker-grid">
              <div className="broker-subpanel">
                <div className="section-header compact">
                  <div>
                    <span>connectors</span>
                    <h3>只读连接器</h3>
                  </div>
                </div>
                <div className="mini-list">
                  {brokerConnectors.map((connector) => (
                    <article className="capability-row broker-connector-row" key={connector.provider}>
                      <div>
                        <span>{connector.label || connector.provider}</span>
                        <strong>{connector.provider} · {connector.status}</strong>
                        <p>{connector.missing_env?.length ? `missing env: ${connector.missing_env.join(", ")}` : "env ready"} · {connector.missing_tools?.length ? `missing tools: ${connector.missing_tools.length}` : "tools ready"}</p>
                      </div>
                      <StatusBadge status={connector.ready ? "ready" : connector.status} />
                    </article>
                  ))}
                  {!brokerConnectors.length && (
                    <article className="capability-row">
                      <div>
                        <span>qmt</span>
                        <strong>not_loaded</strong>
                      </div>
                      <StatusBadge status="not_loaded" />
                    </article>
                  )}
                </div>
              </div>

              <div className="broker-subpanel">
                <div className="section-header compact">
                  <div>
                    <span>positions</span>
                    <h3>持仓集中度</h3>
                  </div>
                  <StatusBadge status={brokerAnalytics ? "ready" : "not_loaded"} />
                </div>
                <div className="mini-list">
                  {topPositions.slice(0, 4).map((item, index) => {
                    const row = recordFromUnknown(item);
                    return (
                      <article className="capability-row broker-position-row" key={`${row.symbol || index}`}>
                        <div>
                          <span>{firstString(row.symbol, row.name)}</span>
                          <strong>{firstString(row.name, row.symbol)} · {formatMoney(row.market_value)}</strong>
                          <p>{formatPercent(row.position_pct)}</p>
                        </div>
                      </article>
                    );
                  })}
                  {!topPositions.length && (
                    <article className="capability-row">
                      <div>
                        <span>-</span>
                        <strong>no position snapshot</strong>
                      </div>
                    </article>
                  )}
                </div>
              </div>

              <div className="broker-subpanel">
                <div className="section-header compact">
                  <div>
                    <span>behavior</span>
                    <h3>交易行为</h3>
                  </div>
                  <StatusBadge status={brokerAnalytics?.model_version || "not_loaded"} />
                </div>
                <div className="kv-grid relay-kv-grid">
                  <div className="relay-evidence-row">
                    <span>trade_count</span>
                    <strong>{compact(brokerMetrics.trade_count)}</strong>
                  </div>
                  <div className="relay-evidence-row">
                    <span>buy_count</span>
                    <strong>{compact(brokerMetrics.buy_count)}</strong>
                  </div>
                  <div className="relay-evidence-row">
                    <span>sell_count</span>
                    <strong>{compact(brokerMetrics.sell_count)}</strong>
                  </div>
                  <div className="relay-evidence-row">
                    <span>concentration</span>
                    <strong>{formatPercent(brokerMetrics.top_position_concentration)}</strong>
                  </div>
                </div>
              </div>
            </div>

            {riskFlags.length ? (
              <div className="notice warn broker-risk-list">
                <ShieldCheck size={15} />
                {riskFlags.map((flag) => firstString(flag.code, flag.severity)).join(" · ")}
              </div>
            ) : (
              <div className="notice ok">
                <ShieldCheck size={15} />
                read-only analytics ready
              </div>
            )}
          </section>

          <section className="capability-banner finance-relay-banner">
            <div>
              <span>Factor -&gt; Strategy -&gt; Incubation</span>
              <h2>工厂接力总览</h2>
              <p>只读汇总 Agent HTTP 证据：因子池是否可用、策略评审是否给出分流、孵化器是否已经产生生命周期和命中率反馈。</p>
            </div>
            <GitBranch size={20} />
          </section>

          <div className="diagnostics-summary wide">
            <MetricCard label="接力状态" value={overallStatus === "failed" ? "需要处理" : overallStatus === "partial" ? "部分就绪" : overallStatus === "ready" ? "就绪" : "未加载"} status={overallStatus} />
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

          <IncubationActionWorklist relay={relay} />

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
