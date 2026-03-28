import { create } from 'zustand';
import { getBffBaseUrl } from '@/lib/bff-base';
import { clearLoggedIn, hasLoggedInHint, refreshAuth } from '@/lib/auth';

export type WatchItem = { code: string; name: string; addedAt: number };
export type WatchGroup = { id: string; name: string; color: string; items: WatchItem[] };

const LS_KEY = 'aiask_watchlist';


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
let _syncPromise: Promise<void> | null = null;

function isAbortLikeError(err: unknown): boolean {
  if (err instanceof DOMException && err.name === 'AbortError') return true;
  if (!(err instanceof Error)) return false;
  return err.name === 'AbortError' || /aborted|aborterror|the user aborted a request/i.test(err.message);
}

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

async function fetchServer(path: string, options?: RequestInit): Promise<unknown> {
  const requestInit: RequestInit = {
    credentials: 'include',
    ...options,
    headers: { 'Content-Type': 'application/json', ...options?.headers },
  };
  try {
    const bffBase = getBffBaseUrl();
    let res = await fetch(`${bffBase}/watchlist${path}`, requestInit);
    if (res.status === 401) {
      const refreshed = await refreshAuth();
      if (refreshed) {
        res = await fetch(`${bffBase}/watchlist${path}`, requestInit);
      } else {
        clearLoggedIn();
        notifySyncError('HTTP 401');
        return null;
      }
    }
    if (!res.ok) {
      notifySyncError(`HTTP ${res.status}`);
      return null;
    }
    const json = await res.json();
    const payload = json && typeof json === 'object' ? json as Record<string, unknown> : {};
    return payload.data ?? null;
  } catch (err) {
    if (isAbortLikeError(err)) {
      return null;
    }
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
  add: (code: string, name?: string, groupId?: string) => Promise<void>;
  /** Remove stock from a specific group, or from all groups when groupId is omitted */
  remove: (code: string, groupId?: string) => Promise<void>;
  /** Toggle stock in default group */
  toggle: (code: string, name?: string) => Promise<void>;
  /** Create a new group */
  createGroup: (name: string, color?: string) => Promise<string | null>;
  /** Delete a group */
  deleteGroup: (groupId: string) => Promise<void>;
  /** Clear all items from default group */
  clear: () => void;
  /** Sync with server (pull) */
  syncFromServer: () => Promise<void>;
  /** Push local changes to server */
  pushToServer: () => Promise<void>;
};

function normalizeAddedAt(value: unknown): number {
  if (typeof value === 'number' && Number.isFinite(value)) return value;
  if (typeof value === 'string') {
    const parsed = Date.parse(value);
    if (Number.isFinite(parsed)) return parsed;
  }
  return Date.now();
}

function mergeItems(localItems: WatchItem[], serverItems: WatchItem[]): WatchItem[] {
  const merged = [...localItems, ...serverItems].filter(
    (item, index, arr) => arr.findIndex((candidate) => candidate.code === item.code) === index,
  );

  return merged.sort((a, b) => b.addedAt - a.addedAt);
}

function mergeGroups(localGroups: WatchGroup[], serverGroups: WatchGroup[]): WatchGroup[] {
  const merged = new Map<string, WatchGroup>();

  for (const group of serverGroups) {
    merged.set(group.id, { ...group, items: [...group.items] });
  }

  for (const group of localGroups) {
    const existing = merged.get(group.id);
    if (!existing) {
      merged.set(group.id, { ...group, items: [...group.items] });
      continue;
    }

    merged.set(group.id, {
      ...existing,
      name: existing.name || group.name,
      color: existing.color || group.color,
      items: mergeItems(group.items, existing.items),
    });
  }

  const groups = Array.from(merged.values());
  const defaultIndex = groups.findIndex((group) => group.id === 'default');
  if (defaultIndex > 0) {
    const [defaultWatchGroup] = groups.splice(defaultIndex, 1);
    groups.unshift(defaultWatchGroup);
  }

  return groups.length > 0 ? groups : [defaultGroup()];
}

function readWatchlistRecord(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    return {};
  }
  return value as Record<string, unknown>;
}

export const useWatchlistStore = create<WatchlistState>((set, get) => ({
  groups: loadLocal(),
  synced: false,
  syncing: false,

  has: (code) => get().groups.some((g) => g.items.some((i) => i.code === code)),

  add: async (code, name, groupId) => {
    const c = code.trim();
    if (!c) return;
    const prev = get().groups;
    const targetId = groupId || prev[0]?.id || 'default';
    const next = prev.map((g) => {
      if (g.id !== targetId) return g;
      if (g.items.some((i) => i.code === c)) return g;
      return {
        ...g,
        items: [{ code: c, name: name?.trim() || '', addedAt: Date.now() }, ...g.items],
      };
    });
    if (JSON.stringify(next) === JSON.stringify(prev)) return;
    saveLocal(next);
    set({ groups: next });

    const synced = await fetchServer('/stocks/add', {
      method: 'POST',
      body: JSON.stringify({ group: targetId, groupName: prev.find((g) => g.id === targetId)?.name, codes: [c] }),
    });
    if (synced == null) {
      saveLocal(prev);
      set({ groups: prev });
    }
  },

  remove: async (code, groupId) => {
    const c = code.trim();
    if (!c) return;

    const prev = get().groups;
    const targetGroupIds = prev
      .filter((g) => (groupId ? g.id === groupId : g.items.some((i) => i.code === c)))
      .filter((g) => g.items.some((i) => i.code === c))
      .map((g) => g.id);
    if (targetGroupIds.length === 0) return;

    const next = prev.map((g) => {
      if (!targetGroupIds.includes(g.id)) return g;
      return {
        ...g,
        items: g.items.filter((i) => i.code !== c),
      };
    });
    saveLocal(next);
    set({ groups: next });

    const results = await Promise.all(
      targetGroupIds.map((id) =>
        fetchServer(`/stocks/remove?group=${encodeURIComponent(id)}&code=${encodeURIComponent(c)}`, {
          method: 'DELETE',
        })),
    );

    if (results.some((result) => result == null)) {
      saveLocal(prev);
      set({ groups: prev });
    }
  },

  toggle: async (code, name) => {
    if (get().has(code)) await get().remove(code);
    else await get().add(code, name);
  },

  createGroup: async (name, color) => {
    const prev = get().groups;
    const id = `group_${Date.now()}`;
    const newGroup: WatchGroup = {
      id,
      name: name.trim(),
      color: color || '#6366f1',
      items: [],
    };
    const next = [...prev, newGroup];
    saveLocal(next);
    set({ groups: next });
    const created = await fetchServer('/groups/create', {
      method: 'POST',
      body: JSON.stringify({ id, name: name.trim(), color }),
    });
    if (created == null) {
      saveLocal(prev);
      set({ groups: prev });
      return null;
    }
    return id;
  },

  deleteGroup: async (groupId) => {
    const prev = get().groups;
    const group = prev.find((g) => g.id === groupId);
    const fallbackDefault = defaultGroup();
    const defaultIndex = prev.findIndex((g) => g.id === 'default');
    const next = prev
      .filter((g) => g.id !== groupId)
      .map((g, index) => {
        const isDefaultGroup = g.id === 'default' || (defaultIndex === -1 && index === 0);
        if (!group || group.items.length === 0 || !isDefaultGroup) return g;

        const mergedItems = [...group.items, ...g.items].filter(
          (item, itemIndex, arr) => arr.findIndex((candidate) => candidate.code === item.code) === itemIndex,
        );

        return { ...g, items: mergedItems };
      });

    if (next.length === 0) {
      next.push(group && group.items.length > 0 ? { ...fallbackDefault, items: group.items } : fallbackDefault);
    }

    saveLocal(next);
    set({ groups: next });
    if (group) {
      const deleted = await fetchServer(`/groups/delete?id=${encodeURIComponent(group.id)}&name=${encodeURIComponent(group.name)}`, {
        method: 'DELETE',
      });
      if (deleted == null) {
        saveLocal(prev);
        set({ groups: prev });
      }
    }
  },

  clear: () => {
    const next = get().groups.map((g, i) => (i === 0 ? { ...g, items: [] } : g));
    saveLocal(next);
    set({ groups: next });
  },

  syncFromServer: async () => {
    if (_syncPromise) {
      await _syncPromise;
      return;
    }

    const current = get();
    if (current.syncing || current.synced) {
      return;
    }

    set({ syncing: true });
    _syncPromise = (async () => {
      try {
        const localGroups = get().groups;
        const serverGroups = await fetchServer('/groups');
        if (!hasLoggedInHint()) {
          set({ synced: true, syncing: false });
          return;
        }
        if (serverGroups && Array.isArray(serverGroups) && serverGroups.length > 0) {
          const normalized: WatchGroup[] = serverGroups.map((group) => {
            const record = readWatchlistRecord(group);
            return {
              id: String(record.id ?? record.name ?? 'default'),
              name: String(record.name ?? '我的自选'),
              color: String(record.color ?? '#6366f1'),
              items: Array.isArray(record.items)
                ? record.items.map((item) => {
                  const watchItem = readWatchlistRecord(item);
                  return {
                    code: String(watchItem.code ?? ''),
                    name: String(watchItem.name ?? ''),
                    addedAt: normalizeAddedAt(watchItem.addedAt),
                  };
                })
                : [],
            };
          });
          const mergedGroups = mergeGroups(localGroups, normalized);
          saveLocal(mergedGroups);
          set({ groups: mergedGroups, synced: true, syncing: false });

          const needsBackfill = JSON.stringify(mergedGroups) !== JSON.stringify(normalized);
          if (needsBackfill) {
            await get().pushToServer();
          }
        } else {
          // Server has no data — push local to server
          set({ synced: true, syncing: false });
          await get().pushToServer();
        }
      } catch {
        set({ syncing: false });
      } finally {
        _syncPromise = null;
      }
    })();

    await _syncPromise;
  },

  pushToServer: async () => {
    const groups = get().groups;
    for (const group of groups) {
      if (group.items.length > 0) {
        await fetchServer('/stocks/add', {
          method: 'POST',
          body: JSON.stringify({
            group: group.id,
            groupName: group.name,
            codes: group.items.map((i) => i.code),
          }),
        });
      }
    }
  },
}));
