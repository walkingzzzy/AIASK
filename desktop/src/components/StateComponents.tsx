import { AlertTriangle, Database, Filter, Info, Loader2, LockKeyhole, RefreshCw, ShieldAlert, XCircle } from "lucide-react";
import type { ReactNode } from "react";

import type { ApiProblem } from "../types";
import { Button } from "./ui";

export function LoadingState({ label = "Loading", preserveData }: { label?: string; preserveData?: boolean }) {
  return (
    <div className={`state state-loading ${preserveData ? "overlay" : ""}`} role="status">
      <Loader2 className="spin" size={24} />
      <span>{label}</span>
    </div>
  );
}

export function EmptyState({ title, detail, action }: { title: string; detail: string; action?: ReactNode }) {
  return (
    <div className="state state-empty">
      <Info size={32} />
      <strong>{title}</strong>
      <p>{detail}</p>
      {action}
    </div>
  );
}

export function FilterEmptyState({ onClear }: { onClear: () => void }) {
  return (
    <div className="state state-filter-empty">
      <Filter size={32} />
      <strong>No results for the current filters</strong>
      <p>Adjust the filters or clear them to see more records.</p>
      <Button icon={<RefreshCw size={16} />} onClick={onClear}>
        Clear filters
      </Button>
    </div>
  );
}

export function ErrorState({ error, onRetry }: { error: ApiProblem; onRetry?: () => void }) {
  return (
    <div className="state state-error" role="alert">
      <XCircle size={32} />
      <strong>{error.title}</strong>
      <p>{error.detail || "The request failed. Check the Agent HTTP connection or token settings."}</p>
      {error.code ? (
        <div className="error-meta">
          <code>{error.code}</code>
          {error.trace_id ? <small>trace: {error.trace_id}</small> : null}
        </div>
      ) : null}
      {onRetry ? (
        <Button icon={<RefreshCw size={16} />} onClick={onRetry}>
          Retry
        </Button>
      ) : null}
    </div>
  );
}

export function DegradedState({
  available,
  unavailable,
  children
}: {
  available: string[];
  unavailable: string[];
  children?: ReactNode;
}) {
  return (
    <div className="state state-degraded">
      <AlertTriangle size={32} />
      <strong>Some capabilities are degraded</strong>
      <div className="degraded-detail">
        <div>
          <small>Still available:</small>
          <ul>
            {available.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </div>
        <div>
          <small>Currently unavailable:</small>
          <ul>
            {unavailable.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </div>
      </div>
      {children}
    </div>
  );
}

export function GatedState({
  reason,
  requirements,
  action
}: {
  reason: string;
  requirements: string[];
  action?: ReactNode;
}) {
  return (
    <div className="state state-gated">
      <LockKeyhole size={32} />
      <strong>Authorization required</strong>
      <p>{reason}</p>
      <div className="gated-requirements">
        <small>Required before continuing:</small>
        <ul>
          {requirements.map((requirement) => (
            <li key={requirement}>{requirement}</li>
          ))}
        </ul>
      </div>
      {action}
    </div>
  );
}

export function BlockedState({ reason, policy }: { reason: string; policy?: string }) {
  return (
    <div className="state state-blocked">
      <ShieldAlert size={32} />
      <strong>Action blocked</strong>
      <p>{reason}</p>
      {policy ? <small className="policy-ref">Policy: {policy}</small> : null}
      <p className="blocked-notice">This restriction is enforced by backend policy and the desktop will not bypass it.</p>
    </div>
  );
}

export function StaleState({
  asOf,
  staleDays,
  onSync
}: {
  asOf: string;
  staleDays: number;
  onSync?: () => void;
}) {
  return (
    <div className="state state-stale">
      <Database size={32} />
      <strong>Data is stale</strong>
      <p>
        Last updated: {asOf}. Stale for {staleDays} day{staleDays === 1 ? "" : "s"}.
      </p>
      {onSync ? (
        <Button icon={<RefreshCw size={16} />} onClick={onSync}>
          Open data sync
        </Button>
      ) : null}
    </div>
  );
}

export function MockDataNotice() {
  return (
    <div className="mock-notice" role="note">
      <Info size={14} />
      <span>You are in mock mode. These records are for UI validation and do not represent live backend capability.</span>
    </div>
  );
}

export function DataSourceBadge({
  source,
  asOf,
  mock
}: {
  source: string;
  asOf?: string;
  mock?: boolean;
}) {
  return (
    <div className="data-source-badge">
      <small>
        Data source: <strong>{source}</strong>
        {mock ? " (Mock)" : ""}
        {asOf ? ` | Updated: ${asOf}` : ""}
      </small>
    </div>
  );
}

export function SmartStateHandler({
  loading,
  error,
  data,
  empty,
  degraded,
  gated,
  blocked,
  stale,
  children,
  onRetry,
  emptyAction
}: {
  loading: boolean;
  error: ApiProblem | null;
  data: unknown;
  empty?: boolean;
  degraded?: { available: string[]; unavailable: string[] };
  gated?: { reason: string; requirements: string[] };
  blocked?: { reason: string; policy?: string };
  stale?: { asOf: string; staleDays: number };
  children: (data: unknown) => ReactNode;
  onRetry?: () => void;
  emptyAction?: ReactNode;
}) {
  if (loading) return <LoadingState />;
  if (error) return <ErrorState error={error} onRetry={onRetry} />;
  if (blocked) return <BlockedState reason={blocked.reason} policy={blocked.policy} />;
  if (gated) return <GatedState reason={gated.reason} requirements={gated.requirements} />;
  if (empty) return <EmptyState title="No data yet" detail="There are no records for the current state." action={emptyAction} />;
  if (degraded) {
    return (
      <DegradedState available={degraded.available} unavailable={degraded.unavailable}>
        {children(data)}
      </DegradedState>
    );
  }
  if (stale) return <StaleState asOf={stale.asOf} staleDays={stale.staleDays} />;

  return <>{children(data)}</>;
}
