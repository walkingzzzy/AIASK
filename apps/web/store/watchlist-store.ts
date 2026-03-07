import { create } from 'zustand';

export type WatchItem = { code: string; name: string; addedAt: number };
export type WatchGroup = { id: string; name: string; color: string; items: WatchItem[] };

const LS_KEY = 'aiask_watchlist';
const BFF_BASE = process.env.NEXT_PUBLIC_BFF_BASE_URL || 'http://localhost:3001/api';


/* ── LocalStorage helpers ── */

function loadLocal(): WatchGroup[] {
  if (typeof window === 'undefined') return [defaultGroup()];
  try {
    const raw = localStorage.getItem(LS_KEY);
    if (!raw) return [defaultGroup()];
    const parsed = JSON.parse(raw);
    // migrate: old format was WatchItem[]
    if (Array.isArray(parsed) && parsed.length > 0 && 'code' in parsed[0]) {
      return [{ id: 'default', name: '我的自选', color: '#6366f1', items: parsed }];
    }
    return parsed;
  } catch {
    return [defaultGroup()];
  }
}

function saveLocal(groups: WatchGroup[]) {
  if (typeof window === 'undefined') return;
  try {
    localStorage.setItem(LS_KEY, JSON.stringify(groups));
  } catch { }
}

function defaultGroup(): WatchGroup {
  return { id: 'default', name: '我的自选', color: '#6366f1', items: [] };
}

/* ── Server sync helpers ── */

let _lastErrorTs = 0;

function notifySyncError(detail: string) {
  // Debounce: show at most one error toast per 30s
  const now = Date.now();
  if (now - _lastErrorTs < 30_000) return;
  _lastErrorTs = now;
  if (typeof window !== 'undefined') {
    window.dispatchEvent(
      new CustomEvent('watchlist:sync-error', { detail }),
    );
    console.warn(`[Watchlist] 同步失败: ${detail}`);
  }
}

async function fetchServer(path: string, options?: RequestInit): Promise<any> {
  try {
    const res = await fetch(`${BFF_BASE}/watchlist${path}`, {
      credentials: 'include',
      ...options,
      headers: { 'Content-Type': 'application/json', ...options?.headers },
    });
    if (!res.ok) {
      notifySyncError(`HTTP ${res.status}`);
      return null;
    }
    const json = await res.json();
    return json?.data ?? null;
  } catch (err) {
    notifySyncError(err instanceof Error ? err.message : 'network error');
    return null;
  }
}

/* ── Store ── */

type WatchlistState = {
  groups: WatchGroup[];
  synced: boolean;
  syncing: boolean;
  /** Check if any group contains code */
  has: (code: string) => boolean;
  /** Add stock to a group (default: first group) */
  add: (code: string, name?: string, groupId?: string) => void;
  /** Remove stock from all groups */
  remove: (code: string) => void;
  /** Toggle stock in default group */
  toggle: (code: string, name?: string) => void;
  /** Create a new group */
  createGroup: (name: string, color?: string) => void;
  /** Delete a group */
  deleteGroup: (groupId: string) => void;
  /** Clear all items from default group */
  clear: () => void;
  /** Sync with server (pull) */
  syncFromServer: () => Promise<void>;
  /** Push local changes to server */
  pushToServer: () => Promise<void>;
};

export const useWatchlistStore = create<WatchlistState>((set, get) => ({
  groups: loadLocal(),
  synced: false,
  syncing: false,

  has: (code) => get().groups.some((g) => g.items.some((i) => i.code === code)),

  add: (code, name, groupId) => {
    const c = code.trim();
    if (!c) return;
    const targetId = groupId || get().groups[0]?.id || 'default';
    const next = get().groups.map((g) => {
      if (g.id !== targetId) return g;
      if (g.items.some((i) => i.code === c)) return g;
      return {
        ...g,
        items: [{ code: c, name: name?.trim() || '', addedAt: Date.now() }, ...g.items],
      };
    });
    saveLocal(next);
    set({ groups: next });
    // Optimistic server sync (fire-and-forget)
    fetchServer('/stocks/add', {
      method: 'POST',
      body: JSON.stringify({ group: targetId, codes: [c] }),
    });
  },

  remove: (code) => {
    const c = code.trim();
    // 先取好 groupId，再 set，避免 set 后 get 语义混乱
    const groupId = get().groups[0]?.id || 'default';
    const next = get().groups.map((g) => ({
      ...g,
      items: g.items.filter((i) => i.code !== c),
    }));
    saveLocal(next);
    set({ groups: next });
    // Sync remove to server
    fetchServer(`/stocks/remove?group=${encodeURIComponent(groupId)}&code=${c}`, {
      method: 'DELETE',
    });
  },

  toggle: (code, name) => {
    get().has(code) ? get().remove(code) : get().add(code, name);
  },

  createGroup: (name, color) => {
    const id = `group_${Date.now()}`;
    const newGroup: WatchGroup = {
      id,
      name: name.trim(),
      color: color || '#6366f1',
      items: [],
    };
    const next = [...get().groups, newGroup];
    saveLocal(next);
    set({ groups: next });
    fetchServer('/groups/create', {
      method: 'POST',
      body: JSON.stringify({ name: name.trim(), color }),
    });
  },

  deleteGroup: (groupId) => {
    const group = get().groups.find((g) => g.id === groupId);
    const next = get().groups.filter((g) => g.id !== groupId);
    if (next.length === 0) next.push(defaultGroup());
    saveLocal(next);
    set({ groups: next });
    if (group) {
      fetchServer(`/groups/delete?name=${encodeURIComponent(group.name)}`, {
        method: 'DELETE',
      });
    }
  },

  clear: () => {
    const next = get().groups.map((g, i) => (i === 0 ? { ...g, items: [] } : g));
    saveLocal(next);
    set({ groups: next });
  },

  syncFromServer: async () => {
    set({ syncing: true });
    try {
      const serverGroups = await fetchServer('/groups');
      if (serverGroups && Array.isArray(serverGroups) && serverGroups.length > 0) {
        const normalized: WatchGroup[] = serverGroups.map((g: any) => ({
          id: String(g.id ?? g.name ?? 'default'),
          name: String(g.name ?? '我的自选'),
          color: String(g.color ?? '#6366f1'),
          items: Array.isArray(g.items)
            ? g.items.map((i: any) => ({
              code: String(i.code ?? ''),
              name: String(i.name ?? ''),
              addedAt: Number(i.addedAt ?? Date.now()),
            }))
            : [],
        }));
        saveLocal(normalized);
        set({ groups: normalized, synced: true, syncing: false });
      } else {
        // Server has no data — push local to server
        set({ synced: true, syncing: false });
        get().pushToServer();
      }
    } catch {
      set({ syncing: false });
    }
  },

  pushToServer: async () => {
    const groups = get().groups;
    for (const group of groups) {
      if (group.items.length > 0) {
        await fetchServer('/stocks/add', {
          method: 'POST',
          body: JSON.stringify({
            group: group.id,
            codes: group.items.map((i) => i.code),
          }),
        });
      }
    }
  },
}));
