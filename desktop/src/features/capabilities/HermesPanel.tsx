import { useMemo, useState } from "react";
import type { CapabilityWorkbenchPayload } from "../../types";
import { JsonPanel, StatusBadge, compact } from "../../components/shared";
import { filterRows, itemLabel } from "./capabilityUtils";

function MappingTable({ title, rows }: { title: string; rows: Array<Record<string, unknown>> }) {
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState("all");
  const visible = useMemo(() => filterRows(rows, query, status), [query, rows, status]);
  return (
    <section className="capability-section">
      <div className="section-header">
        <div>
          <span>{rows.length} items</span>
          <h3>{title}</h3>
        </div>
        <div className="filter-row">
          <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search area, tool, platform..." />
          <select value={status} onChange={(event) => setStatus(event.target.value)}>
            <option value="all">all status</option>
            <option value="implemented">implemented</option>
            <option value="live_unverified">live_unverified</option>
            <option value="skipped_missing_credentials">skipped_missing_credentials</option>
            <option value="blocked">blocked</option>
            <option value="missing">missing</option>
            <option value="failed">failed</option>
          </select>
        </div>
      </div>
      <div className="data-table compact-table">
        <div className="table-head">
          <span>Name</span>
          <span>Area</span>
          <span>Status</span>
          <span>AIASK</span>
        </div>
        {visible.map((item) => (
          <div className="table-row" key={`${title}:${itemLabel(item)}:${String(item.area || "")}`}>
            <strong>{itemLabel(item)}</strong>
            <span>{String(item.area || item.aiask_adapter || "-")}</span>
            <StatusBadge status={String(item.status || item.live_status || "unknown")} />
            <small>{Array.isArray(item.aiask_tools) ? item.aiask_tools.join(", ") : String(item.aiask_adapter || "-")}</small>
          </div>
        ))}
        {!visible.length && <p className="muted table-empty">No rows match this filter.</p>}
      </div>
    </section>
  );
}

function parityStatusMeta(status?: string): { status: string; label: string } {
  if (status === "in_progress") return { status: "live_pending", label: "code parity complete, live pending" };
  if (!status) return { status: "not_loaded", label: "not loaded" };
  return { status, label: status };
}

function surfaceRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, unknown>) : {};
}

function surfaceDetail(payload: Record<string, unknown>): string {
  const candidates = [
    payload.active_provider,
    payload.provider,
    payload.default_provider,
    payload.configured_count,
    payload.enabled_count,
    payload.installed_count,
    payload.count,
    payload.source
  ];
  const value = candidates.find((item) => item !== undefined && item !== null && item !== "");
  return value === undefined ? compact(payload.object || payload.status || "aiask_native") : compact(value);
}

function SurfaceGrid({ hermes }: { hermes: NonNullable<CapabilityWorkbenchPayload["hermes"]> }) {
  const items = [
    { label: "Providers", value: hermes.providers, hint: "model routing and fallback" },
    { label: "Memory", value: hermes.memory, hint: "SQLite and optional providers" },
    { label: "ACP", value: hermes.acp, hint: "client-provided MCP adapter" },
    { label: "Security", value: hermes.security, hint: "redaction and policy checks" },
    { label: "Skill Packs", value: hermes.skill_packs, hint: "AIASK-native skill packs" }
  ];
  return (
    <section className="capability-section">
      <div className="section-header">
        <div>
          <span>Full Mode surfaces</span>
          <h3>Providers, memory, ACP, security, skills</h3>
        </div>
      </div>
      <div className="status-grid">
        {items.map((item) => {
          const payload = surfaceRecord(item.value);
          const status = String(payload.status || payload.live_status || (Object.keys(payload).length ? "ready" : "unknown"));
          return (
            <div className="metric-card" key={item.label}>
              <span>{item.label}</span>
              <strong>{status}</strong>
              <small>{item.hint}: {surfaceDetail(payload)}</small>
            </div>
          );
        })}
      </div>
    </section>
  );
}

function HermesDeltaSummary({ hermes }: { hermes: NonNullable<CapabilityWorkbenchPayload["hermes"]> }) {
  const delta = hermes.parity.v014_delta;
  if (!delta) return null;
  return (
    <section className="capability-section">
      <div className="section-header">
        <div>
          <span>{delta.release_tag || "v0.14"} delta</span>
          <h3>Hermes v0.14 Delta</h3>
        </div>
      </div>
      <div className="status-grid">
        <div className="metric-card">
          <span>Total</span>
          <strong>{delta.total ?? 0}</strong>
          <small>{delta.baseline || hermes.parity.baseline}</small>
        </div>
        <div className="metric-card warn">
          <span>Missing</span>
          <strong>{delta.missing_count ?? 0}</strong>
          <small>New v0.14 capabilities without AIASK-native equivalents</small>
        </div>
        <div className="metric-card neutral">
          <span>Partial</span>
          <strong>{delta.partial_count ?? 0}</strong>
          <small>Mapped surfaces that need deeper behavior or provider work</small>
        </div>
      </div>
    </section>
  );
}

export function HermesPanel({ payload }: { payload: CapabilityWorkbenchPayload | null }) {
  const hermes = payload?.hermes;
  if (!hermes) {
    return <p className="muted">Refresh capabilities to load Hermes parity.</p>;
  }
  const statusBadge = parityStatusMeta(hermes.parity.strict_status || hermes.parity.status);
  return (
    <div className="capability-stack">
      <div className="capability-banner">
        <div>
          <span>Hermes native parity</span>
          <h2>{hermes.status.baseline || "Hermes parity"}</h2>
          <p>Runtime is AIASK-native. Vendor runtime embedded: {String(hermes.status.embedded_vendor_runtime)}</p>
        </div>
        <StatusBadge status={statusBadge.status} label={statusBadge.label} />
      </div>

      <SurfaceGrid hermes={hermes} />
      <HermesDeltaSummary hermes={hermes} />
      <MappingTable title="Feature Mapping" rows={(hermes.feature_mapping || []) as Array<Record<string, unknown>>} />
      <MappingTable title="Hermes Tool Mapping" rows={(hermes.tool_mapping || []) as Array<Record<string, unknown>>} />
      <MappingTable title="Gateway Platform Mapping" rows={(hermes.platform_mapping || []) as Array<Record<string, unknown>>} />
      <MappingTable title="Hermes v0.14 Delta" rows={([...(hermes.parity.v014_delta?.missing || []), ...(hermes.parity.v014_delta?.partial || []), ...(hermes.parity.v014_delta?.implemented || [])]) as Array<Record<string, unknown>>} />

      <details className="raw-details">
        <summary>Raw Hermes payload</summary>
        <JsonPanel value={hermes} />
      </details>
    </div>
  );
}
