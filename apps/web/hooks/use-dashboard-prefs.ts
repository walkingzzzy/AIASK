'use client';

import { useState } from 'react';
import { useApiMutation } from './use-api-mutation';

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

function saveLocal(visibility: ModuleVisibility) {
  if (typeof window === 'undefined') return;
  try { localStorage.setItem(PREFS_KEY, JSON.stringify({ visibility, updatedAt: Date.now() })); } catch {}
}

export { DASHBOARD_MODULES };
export type { DashboardModuleKey, ModuleVisibility };

export function useDashboardPrefs(mounted: boolean, profileQ: { data: Record<string, unknown> | null | undefined }) {
  const [draftVisibility, setDraftVisibility] = useState<ModuleVisibility | null>(null);
  const saveApi = useApiMutation<Record<string, unknown>>({ successToast: false, errorToast: false });
  const profilePrefs = profileQ.data?.preferences;
  const profileObj = profilePrefs && typeof profilePrefs === 'object' ? profilePrefs as Record<string, unknown> : {};
  const profileDash = parseVis((profileObj.homeDashboard as Record<string, unknown> | undefined)?.visibility);
  const storedVisibility = mounted ? loadLocal() : undefined;
  const visibility = draftVisibility ?? (mounted ? merge(storedVisibility ?? profileDash) : DEFAULTS);
  const initialized = mounted;
  const dirty = saveApi.isPending;

  const toggle = (key: DashboardModuleKey) => {
    const next = { ...visibility, [key]: !visibility[key] };
    saveLocal(next);
    setDraftVisibility((prev) => (prev && same(prev, next) ? prev : next));
    void saveApi.trigger('/auth/profile', { method: 'POST' }, {
      preferences: { ...profileObj, homeDashboard: { visibility: next, updatedAt: Date.now() } },
    });
  };

  return { DASHBOARD_MODULES, visibility, toggle, initialized, dirty };
}
