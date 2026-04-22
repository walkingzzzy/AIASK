'use client';

import Link from 'next/link';
import { Badge } from '@/components/ui';
import { LineChart } from '@/components/charts';
import { resolveStrategyStatusMeta } from '@/app/strategy-market/components/strategy-market-support';
import { resolveIncubationSurface } from '@/app/strategy-market/lib/incubation-surface';
import { fmtPct, fmtNum } from '@/lib/data-utils';
import { getStrategyMetricSnapshot } from '@/lib/strategy-metrics';
import type { Strategy } from '@aiask/shared-types';

const TYPE_LABELS: Record<string, { label: string; variant: 'info' | 'success' | 'warning' | 'danger' | 'neutral' }> = {
  momentum: { label: '动量', variant: 'info' },
  value: { label: '价值', variant: 'success' },
  quality: { label: '质量', variant: 'warning' },
  quality_factor: { label: '质量', variant: 'warning' },
  growth: { label: '成长', variant: 'danger' },
  multi_factor: { label: '多因子', variant: 'neutral' },
  macro: { label: '宏观', variant: 'info' },
  ma_cross: { label: '均线', variant: 'info' },
  dsl_rule: { label: 'DSL', variant: 'neutral' },
};

function Stars({ rating }: { rating: number }) {
  const full = Math.round(rating);
  return (
    <span className="text-amber-400 text-xs" title={`${rating.toFixed(1)} 分`}>
      {'★'.repeat(full)}{'☆'.repeat(5 - full)}
    </span>
  );
}

export function StrategyCard({ s, onAdd }: { s: Strategy; onAdd?: (s: Strategy) => void }) {
  const t = TYPE_LABELS[s.strategy_type || ''] ?? { label: s.strategy_type || '其他', variant: 'neutral' as const };
  const statusMeta = resolveStrategyStatusMeta(s.status);
  const incubation = resolveIncubationSurface({
    strategyStatus: s.status,
    incubationSurface: s.incubation_surface,
  });
  const metrics = getStrategyMetricSnapshot(s);
  const nav = s.nav_series ?? [];
  const cats = nav.map((_, i) => `${i}`);
  const trustedInfo = [
    s.sample_start_date && s.sample_end_date ? `${s.sample_start_date} ~ ${s.sample_end_date}` : null,
    s.turnover_rate != null ? `换手 ${fmtPct(s.turnover_rate)}` : null,
    s.capacity != null ? `容量 ${fmtNum(s.capacity, 0)}` : null,
  ].filter(Boolean);

  return (
    <Link
      href={`/strategy-market/${s.id}`}
      className="panel-solid glass-hover flex flex-col gap-4 rounded-[28px] p-5 no-underline text-inherit"
    >
      <div className="flex items-center justify-between">
        <span className="truncate text-sm font-semibold text-text-primary">{s.name}</span>
        <div className="ml-3 flex shrink-0 flex-wrap items-center justify-end gap-2">
          <Badge variant={t.variant}>{t.label}</Badge>
          <Badge variant={statusMeta.variant}>{statusMeta.label}</Badge>
          <Badge variant={incubation.stage.variant}>{incubation.stage.label}</Badge>
        </div>
      </div>

      {nav.length > 2 && (
        <div className="h-[60px] rounded-[16px] border border-border-light bg-surface-alt/60 p-2">
          <LineChart categories={cats} series={[{ name: 'NAV', data: nav, color: '#1a73e8' }]} height={60} compact />
        </div>
      )}

      <div className="grid grid-cols-3 gap-2 text-xs text-text-secondary">
        <div>
          <div className="metric-label">年化收益</div>
          <div className={`mt-2 text-sm font-semibold ${(metrics.totalReturn ?? 0) >= 0 ? 'text-success' : 'text-danger'}`}>
            {fmtPct(metrics.totalReturn ?? 0)}
          </div>
        </div>
        <div>
          <div className="metric-label">Sharpe</div>
          <div className="mt-2 text-sm font-semibold text-text-primary">{fmtNum(metrics.sharpe ?? 0, 2)}</div>
        </div>
        <div>
          <div className="metric-label">最大回撤</div>
          <div className="mt-2 text-sm font-semibold text-danger">{fmtPct(metrics.maxDrawdown ?? 0)}</div>
        </div>
      </div>

      {trustedInfo.length > 0 ? (
        <div className="flex flex-wrap gap-1 text-[10px] text-text-secondary">
          {trustedInfo.map((item) => (
            <span key={item} className="rounded-full border border-border bg-surface-alt px-2 py-1">{item}</span>
          ))}
        </div>
      ) : null}

      <div className="rounded-[16px] border border-border-light bg-surface-alt/50 px-3 py-2 text-[11px] leading-5 text-text-secondary">
        {incubation.summaryLine}
      </div>

      <div className="rounded-[16px] border border-border-light bg-surface-alt/50 px-3 py-2 text-[11px] leading-5 text-text-secondary">
        收藏、复制个人策略和创建模拟盘测试需进入详情页执行。
      </div>

      <div className="flex items-center justify-between border-t border-border pt-2 text-xs text-text-secondary">
        <div className="flex items-center gap-2">
          {s.avg_rating != null && <Stars rating={s.avg_rating} />}
          <span>{s.subscriber_count ?? 0} 收藏</span>
        </div>
        {onAdd && (
          <button
            onClick={(e) => { e.preventDefault(); e.stopPropagation(); onAdd(s); }}
            className="rounded-full bg-primary px-3 py-1 text-xs text-white shadow-sm"
          >
            + 加入组合
          </button>
        )}
      </div>
    </Link>
  );
}

export type { Strategy };
