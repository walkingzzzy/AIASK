import { create } from 'zustand';

export type RecentStock = { code: string; name: string; ts: number };

const MAX_RECENT = 20;
const LS_KEY = 'aiask_recent_stocks';
const LS_CODE_KEY = 'aiask_current_stock';

function loadRecent(): RecentStock[] {
  if (typeof window === 'undefined') return [];
  try {
    return JSON.parse(localStorage.getItem(LS_KEY) || '[]');
  } catch { return []; }
}

function saveRecent(list: RecentStock[]) {
  if (typeof window === 'undefined') return;
  try { localStorage.setItem(LS_KEY, JSON.stringify(list)); } catch {}
}

function loadCode(): string {
  if (typeof window === 'undefined') return '';
  try { return localStorage.getItem(LS_CODE_KEY) || ''; } catch { return ''; }
}

function saveCode(code: string) {
  if (typeof window === 'undefined') return;
  try {
    if (code) localStorage.setItem(LS_CODE_KEY, code);
    else localStorage.removeItem(LS_CODE_KEY);
  } catch {}
}

type StockContextState = {
  /** 当前全局选中的股票代码 */
  code: string;
  /** 当前股票名称（可能为空） */
  name: string;
  /** 最近查看列表 */
  recent: RecentStock[];
  /** 设置当前股票（同时写入最近查看） */
  setStock: (code: string, name?: string) => void;
  /** 仅设置代码（不写入最近查看，用于输入框同步） */
  setCode: (code: string) => void;
  /** 清除最近查看 */
  clearRecent: () => void;
};

export const useStockContext = create<StockContextState>((set, get) => ({
  code: loadCode(),
  name: '',
  recent: loadRecent(),

  setStock: (code, name) => {
    const trimmed = code.trim();
    if (!trimmed) return;
    const n = name?.trim() || '';
    const prev = get().recent.filter((r) => r.code !== trimmed);
    const next = [{ code: trimmed, name: n, ts: Date.now() }, ...prev].slice(0, MAX_RECENT);
    saveRecent(next);
    saveCode(trimmed);
    set({ code: trimmed, name: n, recent: next });
  },

  setCode: (code) => {
    const trimmed = code.trim();
    saveCode(trimmed);
    set({ code: trimmed });
  },

  clearRecent: () => {
    saveRecent([]);
    set({ recent: [] });
  },
}));
