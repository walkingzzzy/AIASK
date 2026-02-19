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
          className={`px-4 py-1.5 cursor-pointer border border-border rounded-t-[6px] text-sm ${
            active === t.key
              ? 'border-b-transparent bg-white font-bold'
              : 'bg-surface-alt font-normal'
          }`}
          onClick={() => onChange(t.key as T)}
        >
          {t.label}
        </button>
      ))}
    </div>
  );
}
