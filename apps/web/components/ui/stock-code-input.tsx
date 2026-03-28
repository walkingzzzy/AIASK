'use client';

export function StockCodeInput({
  value,
  onChange,
  error,
  placeholder = '股票代码',
  id,
  label,
  labelClassName,
}: {
  value: string;
  onChange: (v: string) => void;
  error?: string | null;
  placeholder?: string;
  id?: string;
  label?: string;
  labelClassName?: string;
}) {
  return (
    <div className={`inline-flex ${label ? 'flex-col items-start gap-1.5' : 'items-center gap-2'}`}>
      {label ? <label htmlFor={id} className={labelClassName ?? 'text-xs font-medium uppercase tracking-[0.12em] text-text-muted'}>{label}</label> : null}
      <div className="inline-flex items-center gap-2">
        <input
          id={id}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          maxLength={6}
          placeholder={placeholder}
          aria-invalid={error ? true : undefined}
          className="w-[150px] px-3 py-2 text-sm font-medium"
        />
        {error ? <span className="text-error text-xs">{error}</span> : null}
      </div>
    </div>
  );
}
