'use client';

import Link from 'next/link';
import { Badge } from '@/components/ui';
import { LineChart } from '@/components/charts';
import { fmtPct, fmtNum } from '@/lib/data-utils';
import type { Strategy } from '@aiask/shared-types';

const TYPE_LABELS: Record<string, { label: string; variant: 'info' | 'success' | 'warning' | 'danger' | 'neutral' }> = {
  momentum: { label: '动量', variant: 'info' },
  value: { label: '价值', variant: 'success' },
  quality: { label: '质量', variant: 'warning' },
  growth: { label: '成长', variant: 'danger' },
  multi_factor: { label: '多因子', variant: 'neutral' },
  macro: { label: '宏观', variant: 'info' },
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
  const m = s.metrics;
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
      className="rounded-xl glass glass-hover p-4 flex flex-col gap-2 no-underline text-inherit"
    >
      <div className="flex items-center justify-between">
        <span className="font-semibold text-sm truncate">{s.name}</span>
        <Badge variant={t.variant}>{t.label}</Badge>
      </div>

      {nav.length > 2 && (
        <div className="h-[60px]">
          <LineChart categories={cats} series={[{ name: 'NAV', data: nav, color: '#1a73e8' }]} height={60} compact />
        </div>
      )}

      <div className="grid grid-cols-3 gap-1 text-xs text-text-secondary">
        <div>
          <div className="text-[10px]">年化收益</div>
          <div className={`font-medium ${(m?.annual_return ?? m?.total_return ?? 0) >= 0 ? 'text-success' : 'text-danger'}`}>
            {fmtPct(m?.annual_return ?? m?.total_return ?? 0)}
          </div>
        </div>
        <div>
          <div className="text-[10px]">Sharpe</div>
          <div className="font-medium">{fmtNum(m?.sharpe_ratio ?? 0, 2)}</div>
        </div>
        <div>
          <div className="text-[10px]">最大回撤</div>
          <div className="font-medium text-danger">{fmtPct(m?.max_drawdown ?? 0)}</div>
        </div>
      </div>

      {trustedInfo.length > 0 ? (
        <div className="flex flex-wrap gap-1 text-[10px] text-text-secondary">
          {trustedInfo.map((item) => (
            <span key={item} className="px-1.5 py-0.5 rounded-full border border-glass-border">{item}</span>
          ))}
        </div>
      ) : null}

      <div className="flex items-center justify-between text-xs text-text-secondary pt-1 border-t border-glass-border">
        <div className="flex items-center gap-2">
          {s.avg_rating != null && <Stars rating={s.avg_rating} />}
          <span>{s.subscriber_count ?? 0} 订阅</span>
        </div>
        {onAdd && (
          <button
            onClick={(e) => { e.preventDefault(); e.stopPropagation(); onAdd(s); }}
            className="text-xs px-2 py-0.5 rounded bg-primary/10 text-primary hover:bg-primary/20 cursor-pointer"
          >
            + 加入组合
          </button>
        )}
      </div>
    </Link>
  );
}

export type { Strategy };
