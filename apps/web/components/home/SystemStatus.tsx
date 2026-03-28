'use client';

import { SectionCard, Badge, Skeleton } from '@/components/ui';
import { ErrorState, EmptyState } from '@/components/status-state';
import { getBffBaseUrl } from '@/lib/bff-base';
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
  mcp: Record<string, unknown>;
}

/* ------------------------------------------------------------------ */
/* Module status bar + settings                                        */
/* ------------------------------------------------------------------ */

function ModuleStatusBar({ moduleStatuses, showDashboardSettings, setShowDashboardSettings, dashboardVisibility, toggleDashboardModule }: Omit<SystemStatusProps, 'healthQ' | 'health' | 'mcp'>) {
  return (
    <SectionCard>
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

function HealthDetails({ healthQ, health, mcp }: Pick<SystemStatusProps, 'healthQ' | 'health' | 'mcp'>) {
  const bffBase = getBffBaseUrl();

  return (
    <details className="mt-6">
      <summary className="cursor-pointer text-text-secondary text-sm">BFF / MCP 健康状态</summary>
      <SectionCard className="mt-2">
        {healthQ.error ? <ErrorState text={String(healthQ.error)} onRetry={() => healthQ.refetch()} />
          : healthQ.isPending ? <Skeleton height={60} />
            : health ? (
              <div className="grid grid-cols-2 gap-3 text-sm">
                <div>服务: <Badge variant={String(health.status) === 'ok' ? 'success' : 'warning'}>{String(health.status ?? '-')}</Badge></div>
                <div>MCP: <Badge variant={mcp.reachable ? 'success' : 'danger'}>{mcp.reachable ? '已连接' : '未连接'}</Badge></div>
                <div>工具数: {String(mcp.toolCount ?? '-')} / {String(mcp.expectedTools ?? '-')}</div>
                <div>匹配: <Badge variant={mcp.matched ? 'success' : 'warning'}>{String(mcp.matched ?? '-')}</Badge></div>
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
      <HealthDetails healthQ={props.healthQ} health={props.health} mcp={props.mcp} />
    </>
  );
}
