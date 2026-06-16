import { BarChart3, GitBranch, ShieldCheck } from "lucide-react";
import { MetricCard, StatusBadge, compact } from "../../components/shared";
import type { CapabilityWorkbenchPayload, FactorFactoryStatus, ToolEnvelope } from "../../types";
import { arrayFromUnknown, firstString, formatPercent, numberFromUnknown, recordFromUnknown } from "./FinanceLabUtils";

export type RelayStatus = "ready" | "partial" | "failed" | "not_loaded";

export interface RelayState {
  capabilities: CapabilityWorkbenchPayload | null;
  factor: FactorFactoryStatus | null;
  incubation: (ToolEnvelope & { data: Record<string, unknown> }) | null;
  events: (ToolEnvelope & { data: Record<string, unknown> }) | null;
  incubationEvents: (ToolEnvelope & { data: Record<string, unknown> }) | null;
  hitRateEvents: (ToolEnvelope & { data: Record<string, unknown> }) | null;
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

function compactList(value: unknown): string[] {
  if (Array.isArray(value)) return value.map((item) => firstString(item)).filter(Boolean);
  if (typeof value === "string" && value.trim()) return [value];
  return [];
}

function eventPayloads(envelope: (ToolEnvelope & { data: Record<string, unknown> }) | null): Record<string, unknown>[] {
  const data = recordFromUnknown(envelope?.data);
  return arrayFromUnknown(data.events).map((event) => recordFromUnknown(event));
}

export function incubationReportFromRelay(state: RelayState): Record<string, unknown> {
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

export function incubationBlockersFromRelay(state: RelayState): IncubationBlockerRow[] {
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

export function incubationLifecycleRowsFromRelay(state: RelayState): IncubationLifecycleRow[] {
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

export function topIncubationBreakdownLabel(report: Record<string, unknown>): string {
  const rows = [...incubationBreakdownRows(report, "by_family"), ...incubationBreakdownRows(report, "by_regime")];
  const row = rows[0];
  if (!row) return "-";
  return `${row.dimension}:${row.name} hit ${formatPercent(row.metrics.hit_rate)} LCB ${firstString(row.metrics.avg_skill_lcb, "-")}`;
}

export function IncubationActionWorklist({ relay }: { relay: RelayState }) {
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
