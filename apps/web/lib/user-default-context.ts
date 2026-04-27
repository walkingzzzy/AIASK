'use client';

import { authedFetch, unwrapApiEnvelope } from '@/lib/api';

export type UserDefaultContext = {
  stockCode: string | null;
  stockSource: 'workspace' | 'watchlist' | 'paper_position' | 'profile' | 'none';
  accountId: string | null;
  strategyId: string | null;
  strategyName: string | null;
  workspaceId: string | null;
  workspaceName: string | null;
  workspaceContext?: Record<string, unknown>;
  watchlistLeadCode?: string | null;
  paperPositionLeadCode?: string | null;
  profileStockCode?: string | null;
  sources?: Record<string, unknown>;
  updatedAt?: string;
};

export type UserDefaultContextPatch = {
  stockCode?: string;
  accountId?: string;
  strategyId?: string;
  strategyName?: string;
  workspaceId?: string;
};

let cachedContext: UserDefaultContext | null = null;
let inFlight: Promise<UserDefaultContext | null> | null = null;

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === 'object' && !Array.isArray(value)
    ? value as Record<string, unknown>
    : {};
}

function normalizeStockCode(value: unknown): string | null {
  const code = String(value ?? '').trim();
  return /^\d{6}$/.test(code) ? code : null;
}

function normalizeDefaultContext(raw: unknown): UserDefaultContext | null {
  const record = asRecord(raw);
  if (!Object.keys(record).length) return null;
  return {
    stockCode: normalizeStockCode(record.stockCode),
    stockSource: ['workspace', 'watchlist', 'paper_position', 'profile', 'none'].includes(String(record.stockSource))
      ? record.stockSource as UserDefaultContext['stockSource']
      : 'none',
    accountId: String(record.accountId ?? '').trim() || null,
    strategyId: String(record.strategyId ?? '').trim() || null,
    strategyName: String(record.strategyName ?? '').trim() || null,
    workspaceId: String(record.workspaceId ?? '').trim() || null,
    workspaceName: String(record.workspaceName ?? '').trim() || null,
    workspaceContext: asRecord(record.workspaceContext),
    watchlistLeadCode: normalizeStockCode(record.watchlistLeadCode),
    paperPositionLeadCode: normalizeStockCode(record.paperPositionLeadCode),
    profileStockCode: normalizeStockCode(record.profileStockCode),
    sources: asRecord(record.sources),
    updatedAt: typeof record.updatedAt === 'string' ? record.updatedAt : undefined,
  };
}

export async function fetchUserDefaultContext(): Promise<UserDefaultContext | null> {
  if (cachedContext) return cachedContext;
  if (inFlight) return inFlight;

  inFlight = (async () => {
    try {
      const response = await authedFetch('/user/default-context', { cache: 'no-store' }, { redirectOnUnauthorized: false });
      if (!response.ok) return null;
      const payload = await response.json().catch(() => null);
      const context = normalizeDefaultContext(unwrapApiEnvelope(payload).data);
      cachedContext = context;
      return context;
    } catch {
      return null;
    } finally {
      inFlight = null;
    }
  })();

  return inFlight;
}

export async function saveUserDefaultContext(patch: UserDefaultContextPatch): Promise<void> {
  try {
    const response = await authedFetch('/user/default-context', {
      method: 'POST',
      cache: 'no-store',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify(patch),
    }, { redirectOnUnauthorized: false });
    if (!response.ok) return;
    const payload = await response.json().catch(() => null);
    cachedContext = normalizeDefaultContext(unwrapApiEnvelope(payload).data);
  } catch {
    // Best-effort preference sync; local workspace/global stock state still updates immediately.
  }
}
