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
    <div className={`metric-tile card-interactive glass-hover rounded-card p-4 sm:p-5 ${className}`}>
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
