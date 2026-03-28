import { fmtAmount } from '@/lib/data-utils';

export function KpiCard({
  title,
  value,
  suffix,
  change,
  changeType = 'percent',
  className = '',
}: {
  title: string;
  value: string | number | null | undefined;
  suffix?: string;
  change?: number | null;
  changeType?: 'percent' | 'absolute';
  className?: string;
}) {
  const displayValue = value == null || value === '' ? '-' : String(value);
  return (
    <div className={`rounded-[18px] border border-border bg-surface-alt/72 p-4 shadow-[inset_0_1px_0_rgba(255,255,255,0.55)] ${className}`}>
      <div className="metric-label mb-2">{title}</div>
      <div className="metric-value">
        {displayValue}
        {suffix ? <span className="ml-1 text-sm font-normal text-text-muted">{suffix}</span> : null}
      </div>
      {change != null ? (
        <div className={`mt-2 text-xs font-medium ${change >= 0 ? 'text-success' : 'text-danger'}`}>
          {change >= 0 ? '+' : ''}
          {typeof change === 'number' ? (changeType === 'absolute' ? fmtAmount(change) : change.toFixed(2)) : change}
          {changeType === 'percent' ? '%' : ''}
        </div>
      ) : null}
    </div>
  );
}
