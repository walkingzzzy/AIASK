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
    <div
      className="inline-flex flex-wrap items-center gap-1 rounded-[18px] border border-border bg-surface-alt/72 p-1"
      role="tablist"
      aria-label="标签页导航"
    >
      {tabs.map((t) => (
        <button
          key={t.key}
          type="button"
          role="tab"
          aria-selected={active === t.key}
          tabIndex={active === t.key ? 0 : -1}
          className={`rounded-[14px] px-4 py-2 text-sm transition-all ${active === t.key
            ? 'bg-surface text-text-primary shadow-sm border border-border font-semibold'
            : 'border border-transparent text-text-secondary hover:bg-surface hover:border-border-light'
          }`}
          onClick={() => onChange(t.key as T)}
        >
          {t.label}
        </button>
      ))}
    </div>
  );
}
