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
      className="inline-flex flex-wrap items-center gap-1.5 rounded-[22px] border border-glass-border bg-[linear-gradient(180deg,rgba(255,255,255,0.54),rgba(246,250,255,0.3))] p-1.5 shadow-[0_18px_34px_-28px_rgba(15,23,42,0.28)] backdrop-blur-xl"
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
          className={`rounded-[16px] px-4 py-2 text-sm transition-all duration-200 ${active === t.key
            ? 'border border-primary/20 bg-[linear-gradient(180deg,rgba(255,255,255,0.94),rgba(231,242,255,0.76))] text-primary shadow-[0_16px_30px_-22px_rgba(11,107,203,0.44),inset_0_1px_0_rgba(255,255,255,0.88)] font-semibold scale-[1.01]'
            : 'border border-transparent text-text-secondary hover:bg-white/55 hover:border-white/70 hover:text-text-primary hover:scale-[1.01]'
          }`}
          onClick={() => onChange(t.key as T)}
        >
          {t.label}
        </button>
      ))}
    </div>
  );
}
