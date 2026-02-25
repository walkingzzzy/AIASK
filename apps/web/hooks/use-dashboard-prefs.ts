'use client';

import { useState, useEffect, useRef } from 'react';
import { useApiQuery } from './use-api-query';
import { useApiMutation } from './use-api-mutation';
import { ensureRecord } from '../lib/query-parse';

const DASHBOARD_MODULES = [
  { key: 'market', label: '行情' },
  { key: 'fund-flow', label: '资金流' },
  { key: 'alerts', label: '告警' },
  { key: 'sentiment', label: '情绪' },
  { key: 'strategy', label: '策略' },
  { key: 'risk', label: '风控' },
] as const;

type DashboardModuleKey = (typeof DASHBOARD_MODULES)[number]['key'];
type ModuleVisibility = Record<DashboardModuleKey, boolean>;

const PREFS_KEY = 'aiask_home_dashboard_prefs';

const DEFAULTS: ModuleVisibility = {
  market: true, 'fund-flow': true, alerts: true,
  sentiment: true, strategy: true, risk: true,
};

function merge(v?: Partial<ModuleVisibility>): ModuleVisibility {
  return {
    market: v?.market ?? true, 'fund-flow': v?.['fund-flow'] ?? true,
    alerts: v?.alerts ?? true, sentiment: v?.sentiment ?? true,
    strategy: v?.strategy ?? true, risk: v?.risk ?? true,
  };
}

function same(a: ModuleVisibility, b: ModuleVisibility) {
  return a.market === b.market && a['fund-flow'] === b['fund-flow']
    && a.alerts === b.alerts && a.sentiment === b.sentiment
    && a.strategy === b.strategy && a.risk === b.risk;
}

function parseVis(value: unknown): Partial<ModuleVisibility> | undefined {
  if (!value || typeof value !== 'object') return undefined;
  const v = value as Record<string, unknown>;
  const r: Partial<ModuleVisibility> = {};
  for (const k of ['market', 'fund-flow', 'alerts', 'sentiment', 'strategy', 'risk'] as DashboardModuleKey[]) {
    if (typeof v[k] === 'boolean') r[k] = v[k] as boolean;
  }
  return Object.keys(r).length ? r : undefined;
}

function loadLocal(): Partial<ModuleVisibility> | undefined {
  if (typeof window === 'undefined') return undefined;
  try {
    const raw = localStorage.getItem(PREFS_KEY);
    if (!raw) return undefined;
    const p = JSON.parse(raw);
    return p?.visibility ? parseVis(p.visibility) : undefined;
  } catch { return undefined; }
}

function hasLocal(): boolean {
  if (typeof window === 'undefined') return false;
  try { return localStorage.getItem(PREFS_KEY) != null; } catch { return false; }
}

function saveLocal(visibility: ModuleVisibility) {
  if (typeof window === 'undefined') return;
  try { localStorage.setItem(PREFS_KEY, JSON.stringify({ visibility, updatedAt: Date.now() })); } catch {}
}

export { DASHBOARD_MODULES };
export type { DashboardModuleKey, ModuleVisibility };

export function useDashboardPrefs(mounted: boolean, profileQ: { data: Record<string, unknown> | null | undefined }) {
  const [visibility, setVisibility] = useState<ModuleVisibility>(DEFAULTS);
  const [initialized, setInitialized] = useState(false);
  const [dirty, setDirty] = useState(false);

  const saveApi = useApiMutation<Record<string, unknown>>({ successToast: false, errorToast: false });
  const saveRef = useRef(saveApi);
  saveRef.current = saveApi;

  // 1) Load from localStorage on mount
  useEffect(() => {
    if (!mounted) return;
    const local = loadLocal();
    if (local) {
      const merged = merge(local);
      setVisibility((prev) => (same(prev, merged) ? prev : merged));
    }
  }, [mounted]);

  // 2) Merge remote profile prefs (if no local prefs)
  useEffect(() => {
    if (!mounted) return;
    const profilePrefs = profileQ.data?.preferences;
    const profileObj = profilePrefs && typeof profilePrefs === 'object' ? profilePrefs as Record<string, unknown> : {};
    const profileDash = parseVis((profileObj.homeDashboard as Record<string, unknown> | undefined)?.visibility);
    if (hasLocal() || !profileDash) { setInitialized(true); return; }
    const merged = merge(profileDash);
    setVisibility((prev) => (same(prev, merged) ? prev : merged));
    saveLocal(merged);
    setInitialized(true);
  }, [mounted, profileQ.data]);

  // 3) Sync dirty prefs to remote
  useEffect(() => {
    if (!mounted || !initialized || !dirty || saveRef.current.isPending) return;
    if (!profileQ.data) return;
    const profilePrefs = profileQ.data.preferences;
    const base = profilePrefs && typeof profilePrefs === 'object' ? profilePrefs as Record<string, unknown> : {};
    saveRef.current.trigger('/auth/profile', { method: 'POST' }, {
      preferences: { ...base, homeDashboard: { visibility, updatedAt: Date.now() } },
    });
    setDirty(false);
  }, [mounted, initialized, dirty, visibility, profileQ.data]);

  const toggle = (key: DashboardModuleKey) => {
    setVisibility((prev) => {
      const next = { ...prev, [key]: !prev[key] };
      saveLocal(next);
      setDirty(true);
      return next;
    });
  };

  return { DASHBOARD_MODULES, visibility, toggle, initialized, dirty };
}

