'use client';

import { useWatchlistStore } from '@/store/watchlist-store';

export function WatchlistButton({ code, name, size = 'sm' }: { code: string; name?: string; size?: 'sm' | 'md' }) {
  const { has, toggle } = useWatchlistStore();
  const active = has(code);
  const cls = size === 'md' ? 'text-lg px-2 py-1' : 'text-sm px-1';

  return (
    <button
      onClick={(e) => { e.stopPropagation(); e.preventDefault(); void toggle(code, name); }}
      className={`cursor-pointer border-none bg-transparent transition-colors ${cls} ${active ? 'text-yellow-500' : 'text-text-secondary hover:text-yellow-400'}`}
      title={active ? '取消关注' : '加入自选'}
    >
      {active ? '★' : '☆'}
    </button>
  );
}
