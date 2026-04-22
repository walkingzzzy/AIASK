'use client';

import { SectionCard, Badge, Skeleton } from '@/components/ui';
import { ErrorState, EmptyState } from '@/components/status-state';
import { getBffBaseUrl } from '@/lib/bff-base';
import {
  formatHealthSignalLabel,
  formatHealthStatusLabel,
  healthStatusVariant,
  normalizeSystemHealthSnapshot,
  type RuntimeHealthComponent,
} from '@/lib/system-health';
import { DASHBOARD_MODULES } from '@/hooks/use-dashboard-prefs';
import type { DashboardModuleKey } from '@/hooks/use-dashboard-prefs';

/* ------------------------------------------------------------------ */
/* Props                                                               */
/* ------------------------------------------------------------------ */

export interface SystemStatusProps {
  moduleStatuses: Record<DashboardModuleKey, 'ok' | 'loading' | 'error'>;
  showDashboardSettings: boolean;
  setShowDashboardSettings: (v: boolean) => void;
  dashboardVisibility: Record<DashboardModuleKey, boolean>;
  toggleDashboardModule: (key: DashboardModuleKey) => void;

  /* Health */
  healthQ: { error: string | null; isPending: boolean; data: unknown; refetch: () => void };
  health: Record<string, unknown> | null;
}

/* ------------------------------------------------------------------ */
/* Module status bar + settings                                        */
/* ------------------------------------------------------------------ */

function ModuleStatusBar({ moduleStatuses, showDashboardSettings, setShowDashboardSettings, dashboardVisibility, toggleDashboardModule }: Omit<SystemStatusProps, 'healthQ' | 'health'>) {
  return (
    <SectionCard data-testid="home-system-status-modules">
      <div className="flex items-center justify-between gap-3 mb-2">
        <div>
          <div className="eyebrow">运行状态</div>
          <h2 className="mt-2">模块状态</h2>
        </div>
        <button
          type="button"
          onClick={() => setShowDashboardSettings(!showDashboardSettings)}
          className="rounded-full border border-border px-3 py-1 text-xs"
        >
          {showDashboardSettings ? '收起模块配置' : '配置首页模块'}
        </button>
      </div>
      <div className="flex flex-wrap gap-2">
        {DASHBOARD_MODULES.map((m) => {
          const status = moduleStatuses[m.key];
          const variant = status === 'ok' ? 'success' : status === 'loading' ? 'warning' : 'danger';
          const text = status === 'ok' ? '正常' : status === 'loading' ? '加载中' : '异常';
          return <Badge key={m.key} variant={variant}>{m.label}: {text}</Badge>;
        })}
      </div>
      {showDashboardSettings ? (
        <div className="mt-3 grid grid-cols-2 sm:grid-cols-5 gap-2">
          {DASHBOARD_MODULES.map((m) => (
            <label key={m.key} className="text-xs text-text-secondary flex items-center gap-2">
              <input type="checkbox" checked={dashboardVisibility[m.key]} onChange={() => toggleDashboardModule(m.key)} />
              {m.label}
            </label>
          ))}
        </div>
      ) : null}
    </SectionCard>
  );
}

/* ------------------------------------------------------------------ */
/* Health details                                                      */
/* ------------------------------------------------------------------ */

function formatPercent(value: unknown): string {
  const numeric = Number(value ?? NaN);
  return Number.isFinite(numeric) ? `${(numeric * 100).toFixed(1)}%` : '-';
}

function detailText(value: unknown): string {
  const text = String(value ?? '').trim();
  return text || '-';
}

function ComponentCard({
  title,
  component,
  summary,
  detail,
  lastError,
}: {
  title: string;
  component: RuntimeHealthComponent;
  summary: string;
  detail: string;
  lastError?: string | null;
}) {
  return (
    <div className="rounded-[18px] border border-border bg-surface-alt/35 p-3">
      <div className="flex items-center justify-between gap-2">
        <div className="text-sm font-medium text-text-primary">{title}</div>
        <div className="flex flex-wrap items-center justify-end gap-2">
          <Badge variant={healthStatusVariant(component.status)}>{formatHealthStatusLabel(component.status)}</Badge>
          <Badge variant={component.signal === 'operational' ? 'info' : 'neutral'}>
            {formatHealthSignalLabel(component.signal)}
          </Badge>
        </div>
      </div>
      <div className="mt-2 text-sm text-text-primary">{summary}</div>
      <div className="mt-1 text-xs text-text-secondary">{detail}</div>
      {component.reasons.length > 0 ? (
        <div className="mt-2 flex flex-wrap gap-2">
          {component.reasons.slice(0, 4).map((reason) => (
            <Badge key={reason} variant={component.status === 'untrusted' ? 'danger' : 'warning'}>
              {reason}
            </Badge>
          ))}
        </div>
      ) : null}
      {lastError ? <div className="mt-2 text-xs text-danger break-all">{lastError}</div> : null}
    </div>
  );
}

function HealthDetails({ healthQ, health }: Pick<SystemStatusProps, 'healthQ' | 'health'>) {
  const bffBase = getBffBaseUrl();
  const snapshot = normalizeSystemHealthSnapshot(health);
  const mcp = snapshot.dependencies.mcp.raw;
  const db = snapshot.dependencies.db.raw;
  const cache = snapshot.dependencies.cache.raw;
  const vector = snapshot.dependencies.vector.raw;
  const audit = snapshot.dependencies.audit.raw;
  const notifications = snapshot.dependencies.notifications.raw;

  return (
    <details className="mt-6" data-testid="home-system-health-details">
      <summary
        className="cursor-pointer text-text-secondary text-sm"
        data-testid="home-system-health-summary"
      >
        BFF / MCP 健康状态
      </summary>
      <SectionCard className="mt-2">
        {healthQ.error ? <ErrorState text={String(healthQ.error)} onRetry={() => healthQ.refetch()} />
          : healthQ.isPending ? <Skeleton height={60} />
            : health ? (
              <div className="space-y-3">
                <div className="rounded-[18px] border border-border bg-surface-alt/35 p-3">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div className="text-sm font-medium text-text-primary">系统总览</div>
                    <div className="flex flex-wrap items-center gap-2">
                      <Badge variant={healthStatusVariant(snapshot.status)}>
                        {formatHealthStatusLabel(snapshot.status)}
                      </Badge>
                      <Badge variant={snapshot.readiness === 'ready' ? 'success' : snapshot.readiness === 'degraded' ? 'warning' : 'danger'}>
                        {detailText(snapshot.readiness)}
                      </Badge>
                    </div>
                  </div>
                  <div className="mt-2 text-sm text-text-primary">{snapshot.service}</div>
                  <div className="mt-1 text-xs text-text-secondary">
                    最近更新 {detailText(snapshot.timestamp ? new Date(snapshot.timestamp).toLocaleString('zh-CN') : '-')}
                  </div>
                  {snapshot.reasons.length > 0 ? (
                    <div className="mt-2 flex flex-wrap gap-2">
                      {snapshot.reasons.slice(0, 6).map((reason) => (
                        <Badge key={reason} variant={snapshot.status === 'untrusted' ? 'danger' : 'warning'}>
                          {reason}
                        </Badge>
                      ))}
                    </div>
                  ) : null}
                </div>

                <div className="grid gap-3 md:grid-cols-2">
                  <ComponentCard
                    title="MCP"
                    component={snapshot.dependencies.mcp}
                    summary={`工具 ${detailText(mcp.toolCount)} / ${detailText(mcp.expectedTools)} · 传输 ${detailText(mcp.transportKind ?? mcp.source)}`}
                    detail={`连接 ${detailText(mcp.activeConnections)} / ${detailText(mcp.poolSize)} · 匹配 ${detailText(mcp.matched)}`}
                    lastError={typeof mcp.lastError === 'string' ? mcp.lastError : null}
                  />
                  <ComponentCard
                    title="DB"
                    component={snapshot.dependencies.db}
                    summary={`模式 ${detailText(db.mode)} · 阶段 ${detailText(db.lastFailureStage ?? snapshot.dependencies.db.reasons[0])}`}
                    detail={`healthy ${detailText(db.healthy)} · 最近延迟 ${detailText(db.lastLatencyMs)}ms · 最近检查 ${detailText(db.lastCheckedAt)}`}
                    lastError={typeof db.lastError === 'string' ? db.lastError : null}
                  />
                  <ComponentCard
                    title="Cache"
                    component={snapshot.dependencies.cache}
                    summary={`后端 ${detailText(cache.activeBackend)} · 阶段 ${detailText(cache.lastFailureStage ?? snapshot.dependencies.cache.reasons[0])}`}
                    detail={`命中率 ${formatPercent(cache.hitRate)} · Redis ${detailText(cache.redisReady)} · 内存条目 ${detailText(cache.memorySize)} · 错误 ${detailText(cache.errors)}`}
                    lastError={typeof cache.lastError === 'string' ? cache.lastError : null}
                  />
                  <ComponentCard
                    title="Vector"
                    component={snapshot.dependencies.vector}
                    summary={`backend ${detailText(vector.backend)} · health ${detailText(vector.health_mode ?? vector.healthMode)}`}
                    detail={`集合 ${detailText(vector.collection_count)} · 最新版本 ${detailText((vector.latest_snapshot as Record<string, unknown> | undefined)?.index_version)}`}
                    lastError={typeof vector.lastError === 'string' ? vector.lastError : null}
                  />
                </div>

                <div className="grid gap-3 md:grid-cols-2">
                  <ComponentCard
                    title="Audit"
                    component={snapshot.dependencies.audit}
                    summary={`后端 ${detailText(audit.activeBackend)} / 配置 ${detailText(audit.configuredBackend)}`}
                    detail={`内存条目 ${detailText(audit.memoryEntries)} · 最近读错 ${detailText(audit.lastReadError)}`}
                    lastError={typeof audit.lastPersistError === 'string' ? audit.lastPersistError : null}
                  />
                  <ComponentCard
                    title="Notifications"
                    component={snapshot.dependencies.notifications}
                    summary={`配置 ${detailText(notifications.configured)} · 来源 ${detailText(notifications.source)}`}
                    detail={`attempted ${detailText(notifications.attempted)} / delivered ${detailText(notifications.delivered)} / failed ${detailText(notifications.failed)}`}
                    lastError={typeof notifications.lastError === 'string' ? notifications.lastError : null}
                  />
                </div>
              </div>
            ) : <EmptyState text={`暂无健康数据：${bffBase}`} />}
      </SectionCard>
    </details>
  );
}

/* ------------------------------------------------------------------ */
/* Composed export                                                     */
/* ------------------------------------------------------------------ */

export function SystemStatus(props: SystemStatusProps) {
  return (
    <>
      <ModuleStatusBar
        moduleStatuses={props.moduleStatuses}
        showDashboardSettings={props.showDashboardSettings}
        setShowDashboardSettings={props.setShowDashboardSettings}
        dashboardVisibility={props.dashboardVisibility}
        toggleDashboardModule={props.toggleDashboardModule}
      />
      <HealthDetails healthQ={props.healthQ} health={props.health} />
    </>
  );
}
