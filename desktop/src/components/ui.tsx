import {
  AlertTriangle,
  CheckCircle2,
  ChevronRight,
  Info,
  Loader2,
  LockKeyhole,
  RefreshCw,
  XCircle
} from "lucide-react";
import type { ReactNode } from "react";
import { Link } from "react-router-dom";

import { redactSecrets, toList } from "../services/api/core";
import type { ApiProblem, Metric, TableColumn, Tone, UnknownRecord } from "../types";

type MobileRecordDetail = {
  label: string;
  value: ReactNode;
};

type MobileRecordCard = {
  title: ReactNode;
  subtitle?: ReactNode;
  details?: MobileRecordDetail[];
  actions?: ReactNode;
};

const toneClass: Record<Tone, string> = {
  neutral: "tone-neutral",
  success: "tone-success",
  warning: "tone-warning",
  danger: "tone-danger",
  info: "tone-info",
  gated: "tone-gated"
};

const toneIcon: Record<Tone, ReactNode> = {
  neutral: <Info size={14} />,
  success: <CheckCircle2 size={14} />,
  warning: <AlertTriangle size={14} />,
  danger: <XCircle size={14} />,
  info: <Info size={14} />,
  gated: <LockKeyhole size={14} />
};

export function StatusBadge({ tone = "neutral", children }: { tone?: Tone; children: ReactNode }) {
  return (
    <span className={`status-badge ${toneClass[tone]}`}>
      {toneIcon[tone]}
      {children}
    </span>
  );
}

export function Button({
  children,
  tone = "neutral",
  icon,
  busy,
  ...props
}: React.ButtonHTMLAttributes<HTMLButtonElement> & { tone?: Tone; icon?: ReactNode; busy?: boolean }) {
  return (
    <button className={`button ${toneClass[tone]}`} disabled={busy || props.disabled} {...props}>
      {busy ? <Loader2 size={16} className="spin" /> : icon}
      <span>{children}</span>
    </button>
  );
}

export function MetricStrip({ metrics }: { metrics: Metric[] }) {
  return (
    <div className="metric-strip">
      {metrics.map((metric) => (
        <div className={`metric ${toneClass[metric.tone || "neutral"]}`} key={metric.label}>
          <span>{metric.label}</span>
          <strong>{metric.value}</strong>
          {metric.detail ? <small>{metric.detail}</small> : null}
        </div>
      ))}
    </div>
  );
}

export function PageShell({
  title,
  description,
  badge,
  actions,
  metrics,
  children,
  aside
}: {
  title: string;
  description: string;
  badge?: ReactNode;
  actions?: ReactNode;
  metrics?: Metric[];
  children: ReactNode;
  aside?: ReactNode;
}) {
  return (
    <section className="page-shell" data-testid="page-shell">
      <header className="page-header">
        <div>
          <div className="page-title-row">
            <h1 data-testid="page-title">{title}</h1>
            {badge}
          </div>
          <p>{description}</p>
        </div>
        {actions ? <div className="page-actions">{actions}</div> : null}
      </header>
      {metrics?.length ? <MetricStrip metrics={metrics} /> : null}
      <div className={aside ? "page-content with-aside" : "page-content"}>
        <main>{children}</main>
        {aside ? <aside className="page-aside">{aside}</aside> : null}
      </div>
    </section>
  );
}

export function Panel({
  title,
  children,
  action,
  className = ""
}: {
  title?: string;
  children: ReactNode;
  action?: ReactNode;
  className?: string;
}) {
  return (
    <section className={`panel ${className}`}>
      {title || action ? (
        <div className="panel-header">
          {title ? <h2>{title}</h2> : <span />}
          {action}
        </div>
      ) : null}
      {children}
    </section>
  );
}

export function LoadingState({ label = "加载中" }: { label?: string }) {
  return (
    <div className="state state-loading">
      <Loader2 className="spin" size={18} />
      <span>{label}</span>
    </div>
  );
}

export function EmptyState({ title, detail, action }: { title: string; detail: string; action?: ReactNode }) {
  return (
    <div className="state">
      <Info size={18} />
      <strong>{title}</strong>
      <p>{detail}</p>
      {action}
    </div>
  );
}

export function ErrorState({ error, onRetry }: { error: ApiProblem; onRetry?: () => void }) {
  return (
    <div className="state state-error" role="alert">
      <XCircle size={18} />
      <strong>{error.title}</strong>
      <p>{error.detail || "请求失败，请检查 Agent HTTP 连接或权限设置。"}</p>
      {error.code ? <code>{error.code}</code> : null}
      {onRetry ? (
        <Button icon={<RefreshCw size={16} />} onClick={onRetry}>
          重试
        </Button>
      ) : null}
    </div>
  );
}

export function DataTable<T extends UnknownRecord>({
  items,
  columns,
  empty = "暂无数据",
  mobileCard
}: {
  items: T[];
  columns: TableColumn<T>[];
  empty?: string;
  mobileCard?: (item: T, index: number) => MobileRecordCard;
}) {
  const rowKey = (item: T, index: number) => {
    for (const field of ["id", "key", "name", "symbol", "code", "title"]) {
      const value = item[field as keyof T];
      if (typeof value === "string" || typeof value === "number" || typeof value === "boolean") {
        return `${field}-${String(value)}-${index}`;
      }
    }
    return `row-${index}`;
  };

  if (!items.length) return <EmptyState title={empty} detail="当前状态下没有记录。" />;
  return (
    <>
      <div className={`table-wrap${mobileCard ? " has-mobile-cards" : ""}`}>
        <table>
          <thead>
            <tr>
              {columns.map((column) => (
                <th key={String(column.key)} style={column.width ? { width: column.width } : undefined}>
                  {column.header}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {items.map((item, index) => (
              <tr key={rowKey(item, index)}>
                {columns.map((column) => (
                  <td key={String(column.key)}>
                    {column.render ? column.render(item) : String(item[column.key as keyof T] ?? "")}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {mobileCard ? (
        <div className="mobile-record-list">
          {items.map((item, index) => {
            const card = mobileCard(item, index);
            return (
              <article className="mobile-record-card" key={`mobile-${rowKey(item, index)}`}>
                <div className="mobile-record-card-title">
                  <strong>{card.title}</strong>
                </div>
                {card.subtitle ? <p className="mobile-record-card-subtitle">{card.subtitle}</p> : null}
                {card.details?.length ? (
                  <dl className="mobile-record-details">
                    {card.details.map((detail) => (
                      <div className="mobile-record-detail" key={detail.label}>
                        <dt>{detail.label}</dt>
                        <dd>{detail.value}</dd>
                      </div>
                    ))}
                  </dl>
                ) : null}
                {card.actions ? <div className="mobile-record-actions">{card.actions}</div> : null}
              </article>
            );
          })}
        </div>
      ) : null}
    </>
  );
}

export function JsonPanel({ data, title = "证据 JSON" }: { data: unknown; title?: string }) {
  return (
    <details className="json-panel" data-testid="json-panel">
      <summary>{title}</summary>
      <pre>{JSON.stringify(redactSecrets(data), null, 2)}</pre>
    </details>
  );
}

export function ResourcePanel<T>({
  title,
  resource,
  children
}: {
  title: string;
  resource: { data: T | null; loading: boolean; error: ApiProblem | null; reload: () => Promise<void> };
  children: (data: T) => ReactNode;
}) {
  return (
    <Panel
      title={title}
      action={
        <Button icon={<RefreshCw size={16} />} onClick={() => void resource.reload()}>
          刷新
        </Button>
      }
    >
      {resource.loading ? <LoadingState /> : null}
      {resource.error ? <ErrorState error={resource.error} onRetry={() => void resource.reload()} /> : null}
      {!resource.loading && !resource.error && resource.data ? children(resource.data) : null}
    </Panel>
  );
}

export function LinkCard({
  to,
  title,
  detail,
  tone = "neutral",
  meta
}: {
  to: string;
  title: string;
  detail: string;
  tone?: Tone;
  meta?: string;
}) {
  return (
    <Link className={`link-card ${toneClass[tone]}`} to={to}>
      <div>
        <strong>{title}</strong>
        <p>{detail}</p>
        {meta ? <small>{meta}</small> : null}
      </div>
      <ChevronRight size={18} />
    </Link>
  );
}

export function GatedNotice({ controlAvailable, action }: { controlAvailable: boolean; action: string }) {
  if (controlAvailable) {
    return <StatusBadge tone="success">控制权限已就绪</StatusBadge>;
  }
  return <StatusBadge tone="gated">{action}需要控制权限</StatusBadge>;
}

export function listFromPayload<T extends UnknownRecord = UnknownRecord>(payload: unknown): T[] {
  return toList<T>(payload);
}
