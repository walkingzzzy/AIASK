import { create } from 'zustand';

export type WatchItem = { code: string; name: string; addedAt: number };

const LS_KEY = 'aiask_watchlist';

function load(): WatchItem[] {
  if (typeof window === 'undefined') return [];
  try { return JSON.parse(localStorage.getItem(LS_KEY) || '[]'); } catch { return []; }
}

function save(list: WatchItem[]) {
  if (typeof window === 'undefined') return;
  try { localStorage.setItem(LS_KEY, JSON.stringify(list)); } catch {}
}

type WatchlistState = {
  items: WatchItem[];
  has: (code: string) => boolean;
  add: (code: string, name?: string) => void;
  remove: (code: string) => void;
  toggle: (code: string, name?: string) => void;
  clear: () => void;
};

export const useWatchlistStore = create<WatchlistState>((set, get) => ({
  items: load(),
  has: (code) => get().items.some((i) => i.code === code),
  add: (code, name) => {
    const c = code.trim();
    if (!c || get().items.some((i) => i.code === c)) return;
    const next = [{ code: c, name: name?.trim() || '', addedAt: Date.now() }, ...get().items];
    save(next);
    set({ items: next });
  },
  remove: (code) => {
    const next = get().items.filter((i) => i.code !== code.trim());
    save(next);
    set({ items: next });
  },
  toggle: (code, name) => {
    get().has(code) ? get().remove(code) : get().add(code, name);
  },
  clear: () => { save([]); set({ items: [] }); },
}));
