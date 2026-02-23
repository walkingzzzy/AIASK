export function KpiCard({
  title,
  value,
  suffix,
  change,
  className = '',
}: {
  title: string;
  value: string | number | null | undefined;
  suffix?: string;
  change?: number | null;
  className?: string;
}) {
  const displayValue = value == null || value === '' ? '-' : String(value);
  return (
    <div className={`glass glass-hover rounded-xl p-3 transition-transform hover:scale-[1.02] ${className}`}>
      <div className="text-text-secondary text-xs mb-1">{title}</div>
      <div className="text-xl font-bold">
        {displayValue}
        {suffix ? <span className="text-sm font-normal text-text-muted ml-1">{suffix}</span> : null}
      </div>
      {change != null ? (
        <div className={`text-xs mt-1 ${change >= 0 ? 'text-danger' : 'text-success'}`}>
          {change >= 0 ? '+' : ''}{typeof change === 'number' ? change.toFixed(2) : change}%
        </div>
      ) : null}
    </div>
  );
}
