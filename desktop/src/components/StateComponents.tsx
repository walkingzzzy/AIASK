import { AlertTriangle, Database, Filter, Info, Loader2, LockKeyhole, RefreshCw, ShieldAlert, XCircle } from "lucide-react";
import type { ReactNode } from "react";

import type { ApiProblem } from "../types";
import { Button } from "./ui";

export function LoadingState({ label = "加载中", preserveData }: { label?: string; preserveData?: boolean }) {
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
      <strong>当前筛选条件下没有结果</strong>
      <p>请调整筛选条件，或清空筛选后查看更多记录。</p>
      <Button icon={<RefreshCw size={16} />} onClick={onClear}>
        清空筛选
      </Button>
    </div>
  );
}

export function ErrorState({ error, onRetry }: { error: ApiProblem; onRetry?: () => void }) {
  return (
    <div className="state state-error" role="alert">
      <XCircle size={32} />
      <strong>{error.title}</strong>
      <p>{error.detail || "请求失败，请检查 Agent HTTP 连接或权限设置。"}</p>
      {error.code ? (
        <div className="error-meta">
          <code>{error.code}</code>
          {error.trace_id ? <small>追踪：{error.trace_id}</small> : null}
        </div>
      ) : null}
      {onRetry ? (
        <Button icon={<RefreshCw size={16} />} onClick={onRetry}>
          重试
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
      <strong>部分能力处于降级状态</strong>
      <div className="degraded-detail">
        <div>
          <small>仍可使用：</small>
          <ul>
            {available.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </div>
        <div>
          <small>当前不可用：</small>
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
      <strong>需要授权</strong>
      <p>{reason}</p>
      <div className="gated-requirements">
        <small>继续前需要满足：</small>
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
      <strong>操作已被阻止</strong>
      <p>{reason}</p>
      {policy ? <small className="policy-ref">策略：{policy}</small> : null}
      <p className="blocked-notice">该限制由后端策略强制执行，桌面端不会绕过。</p>
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
      <strong>数据已过期</strong>
      <p>
        最近更新：{asOf}。已过期 {staleDays} 天。
      </p>
      {onSync ? (
        <Button icon={<RefreshCw size={16} />} onClick={onSync}>
          打开数据同步
        </Button>
      ) : null}
    </div>
  );
}

export function MockDataNotice() {
  return (
    <div className="mock-notice" role="note">
      <Info size={14} />
      <span>当前是演示模式。这些记录用于界面验证，不代表真实后端能力。</span>
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
        数据来源：<strong>{source}</strong>
        {mock ? "（演示）" : ""}
        {asOf ? ` | 更新时间：${asOf}` : ""}
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
  if (empty) return <EmptyState title="暂无数据" detail="当前状态下没有记录。" action={emptyAction} />;
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
