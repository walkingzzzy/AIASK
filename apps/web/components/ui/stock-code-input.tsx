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
    <div className={`inline-flex ${label ? 'flex-col items-start gap-1' : 'items-center gap-2'}`}>
      {label ? <label htmlFor={id} className={labelClassName ?? 'text-xs text-text-secondary'}>{label}</label> : null}
      <div className="inline-flex items-center gap-2">
        <input
          id={id}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          maxLength={6}
          placeholder={placeholder}
          aria-invalid={error ? true : undefined}
          className="w-[140px] px-2 py-1 border border-border rounded text-sm"
        />
        {error ? <span className="text-error text-xs">{error}</span> : null}
      </div>
    </div>
  );
}
