import { create } from 'zustand';
import { ensureBffAvailability } from '@/lib/bff-availability';
import { hasLoggedInHint } from '@/lib/auth';
import { authedFetch, buildApiError, rejectFallbackPayload } from '@/lib/api';

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
  } catch {}
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
    window.dispatchEvent(new CustomEvent('watchlist:sync-error', { detail }));
    if (process.env.NODE_ENV !== 'production') {
      console.warn(`[Watchlist] 同步失败: ${detail}`);
    }
  }
}

async function fetchServer(path: string, options?: RequestInit): Promise<unknown> {
  const reachable = await ensureBffAvailability();
  if (!reachable) {
    const error = new Error('自选股服务暂不可用');
    notifySyncError(error.message);
    throw error;
  }

  const requestInit: RequestInit = {
    ...options,
    headers: { 'Content-Type': 'application/json', ...options?.headers },
  };
  try {
    const res = await authedFetch(`/watchlist${path}`, requestInit);
    const payload = await res.json().catch(() => null);
    if (!res.ok) {
      const error = buildApiError(payload, {
        status: res.status,
        path: `/watchlist${path}`,
        fallbackMessage: `自选股请求失败 (HTTP ${res.status})`,
      });
      notifySyncError(error.message);
      throw error;
    }
    const fallbackReason = rejectFallbackPayload(payload);
    if (fallbackReason) {
      const error = new Error(`自选股请求未完成: ${fallbackReason}`);
      notifySyncError(error.message);
      throw error;
    }
    const body = payload && typeof payload === 'object' ? (payload as Record<string, unknown>) : {};
    return body.data ?? null;
  } catch (err) {
    if (isAbortLikeError(err)) {
      throw err;
    }
    notifySyncError(err instanceof Error ? err.message : 'network error');
    throw err;
  }
}

/* ── Store ── */

type WatchlistState = {
  groups: WatchGroup[];
  synced: boolean;
  syncing: boolean;
  syncError: string | null;
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
  syncFromServer: (force?: boolean) => Promise<void>;
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

function readWatchlistRecord(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    return {};
  }
  return value as Record<string, unknown>;
}

function readCreatedGroupId(payload: unknown, fallbackId: string): string {
  const record = readWatchlistRecord(payload);
  const result = readWatchlistRecord(record.result);
  const data = readWatchlistRecord(result.data);
  const candidate = String(record.group_id ?? data.group_id ?? data.id ?? fallbackId).trim();
  return candidate || fallbackId;
}

export const useWatchlistStore = create<WatchlistState>((set, get) => ({
  groups: loadLocal(),
  synced: false,
  syncing: false,
  syncError: null,

  has: (code) => get().groups.some((g) => g.items.some((i) => i.code === code)),

  add: async (code, name, groupId) => {
    const c = code.trim();
    if (!c) return;
    const groups = get().groups;
    const targetId = groupId || groups[0]?.id || 'default';
    if (groups.some((group) => group.id === targetId && group.items.some((item) => item.code === c))) {
      return;
    }
    const synced = await fetchServer('/stocks/add', {
      method: 'POST',
      body: JSON.stringify({ group: targetId, groupName: groups.find((g) => g.id === targetId)?.name, codes: [c] }),
    });
    if (synced == null) return;
    await get().syncFromServer(true);
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

    const results = await Promise.all(
      targetGroupIds.map((id) =>
        fetchServer(`/stocks/remove?group=${encodeURIComponent(id)}&code=${encodeURIComponent(c)}`, {
          method: 'DELETE',
        }),
      ),
    );

    if (results.some((result) => result == null)) return;
    await get().syncFromServer(true);
  },

  toggle: async (code, name) => {
    if (get().has(code)) await get().remove(code);
    else await get().add(code, name);
  },

  createGroup: async (name, color) => {
    const id = `group_${Date.now()}`;
    const created = await fetchServer('/groups/create', {
      method: 'POST',
      body: JSON.stringify({ id, name: name.trim(), color }),
    });
    if (created == null) return null;
    const createdId = readCreatedGroupId(created, id);
    await get().syncFromServer(true);
    return createdId;
  },

  deleteGroup: async (groupId) => {
    const prev = get().groups;
    const group = prev.find((g) => g.id === groupId);
    if (group) {
      const deleted = await fetchServer(
        `/groups/delete?id=${encodeURIComponent(group.id)}&name=${encodeURIComponent(group.name)}`,
        {
          method: 'DELETE',
        },
      );
      if (deleted == null) return;
      await get().syncFromServer(true);
    }
  },

  clear: () => {
    const next = get().groups.map((g, i) => (i === 0 ? { ...g, items: [] } : g));
    saveLocal(next);
    set({ groups: next });
  },

  syncFromServer: async (force = false) => {
    if (_syncPromise) {
      await _syncPromise;
      return;
    }

    const current = get();
    if (current.syncing || (current.synced && !force)) {
      return;
    }

    set({ syncing: true, syncError: null });
    _syncPromise = (async () => {
      try {
        const reachable = await ensureBffAvailability();
        if (!reachable) {
          throw new Error('自选股服务暂不可用');
        }

        const serverGroups = await fetchServer('/groups');
        if (!hasLoggedInHint()) {
          set({ synced: true, syncing: false, syncError: null });
          return;
        }

        if (Array.isArray(serverGroups) && serverGroups.length > 0) {
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
          saveLocal(normalized);
          set({ groups: normalized, synced: true, syncing: false, syncError: null });
        } else {
          const next = [defaultGroup()];
          saveLocal(next);
          set({ groups: next, synced: true, syncing: false, syncError: null });
        }
      } catch (error) {
        const detail = error instanceof Error ? error.message : '自选股同步失败';
        set({ syncing: false, syncError: detail });
      } finally {
        _syncPromise = null;
      }
    })();

    await _syncPromise;
  },

  pushToServer: async () => {
    await get().syncFromServer(true);
  },
}));
