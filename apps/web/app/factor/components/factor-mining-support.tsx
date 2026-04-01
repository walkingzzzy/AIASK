import { Badge } from '@/components/ui';

function variantForBool(value: unknown) {
  return value ? 'success' : 'danger';
}

export function BadgeValue({
  value,
  trueText = '是',
  falseText = '否',
}: {
  value: unknown;
  trueText?: string;
  falseText?: string;
}) {
  return <Badge variant={variantForBool(value)}>{value ? trueText : falseText}</Badge>;
}

export function MiningField({
  id,
  label,
  value,
  onChange,
  placeholder,
  type = 'text',
}: {
  id: string;
  label: string;
  value: string;
  onChange: (value: string) => void;
  placeholder: string;
  type?: 'text' | 'number';
}) {
  return (
    <label htmlFor={id} className="grid gap-1 text-xs text-text-secondary">
      <span>{label}</span>
      <input
        id={id}
        type={type}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        placeholder={placeholder}
        className="w-full text-sm text-text-primary"
      />
    </label>
  );
}

export function MiningSelect({
  id,
  label,
  value,
  onChange,
  options,
}: {
  id: string;
  label: string;
  value: string;
  onChange: (value: string) => void;
  options: Array<{ label: string; value: string }>;
}) {
  return (
    <label htmlFor={id} className="grid gap-1 text-xs text-text-secondary">
      <span>{label}</span>
      <select
        id={id}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className="w-full text-sm text-text-primary"
      >
        {options.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
    </label>
  );
}

export function MiningCheckbox({
  label,
  checked,
  onChange,
}: {
  label: string;
  checked: boolean;
  onChange: (value: boolean) => void;
}) {
  return (
    <label className="metric-tile flex min-h-[46px] cursor-pointer items-center gap-2 rounded-[20px] px-3 py-2 text-sm text-text-secondary">
      <input
        type="checkbox"
        checked={checked}
        onChange={(event) => onChange(event.target.checked)}
        className="accent-primary"
      />
      <span>{label}</span>
    </label>
  );
}

export function renderWarnings(warnings: unknown) {
  if (!Array.isArray(warnings) || warnings.length === 0) return null;
  return (
    <div className="mt-3 flex flex-wrap gap-2">
      {warnings.map((item, index) => (
        <Badge key={`${String(item)}-${index}`} variant="warning">
          {String(item)}
        </Badge>
      ))}
    </div>
  );
}
