'use client';

type Tab = { key: string; label: string };

export function TabBar<T extends string>({
  tabs,
  active,
  onChange,
}: {
  tabs: readonly Tab[];
  active: T;
  onChange: (key: T) => void;
}) {
  return (
    <div className="flex gap-0 mt-5">
      {tabs.map((t) => (
        <button
          key={t.key}
          type="button"
          className={`px-4 py-1.5 cursor-pointer rounded-t-[8px] text-sm transition-all ${
            active === t.key
              ? 'glass font-bold border-b-transparent'
              : 'bg-surface-alt/50 font-normal border border-glass-border'
          }`}
          onClick={() => onChange(t.key as T)}
        >
          {t.label}
        </button>
      ))}
    </div>
  );
}
