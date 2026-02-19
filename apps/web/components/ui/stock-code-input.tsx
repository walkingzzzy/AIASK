'use client';

export function StockCodeInput({
  value,
  onChange,
  error,
  placeholder = '股票代码',
}: {
  value: string;
  onChange: (v: string) => void;
  error?: string | null;
  placeholder?: string;
}) {
  return (
    <div className="inline-flex items-center gap-2">
      <input
        value={value}
        onChange={(e) => onChange(e.target.value)}
        maxLength={6}
        placeholder={placeholder}
        className="w-[140px] px-2 py-1 border border-border rounded text-sm"
      />
      {error ? <span className="text-error text-xs">{error}</span> : null}
    </div>
  );
}
