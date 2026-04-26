import type {
  CapabilityResponse,
  DailySnapshotResponse,
  FactoryRunListItem,
  FactoryRunsResponse,
  FactoryStatusResponse,
} from './runs';
import type { FactoryRunDetailResponse } from './governance';

export type FactoryMarketMetricCard = {
  key?: string;
  label?: string;
  value?: string;
  tone?: 'default' | 'success' | 'danger';
};

export type FactoryMarketVisibleOutput = {
  key?: string;
  kind?: string;
  title?: string;
  status?: 'available' | 'degraded' | 'empty' | string;
  summary?: string;
  evidence?: string;
  href?: string | null;
  metadata?: Record<string, unknown>;
};

export type FactoryObservabilityResponse = {
  overview?: Record<string, unknown>;
  factory?: {
    status?: FactoryStatusResponse | null;
    latest_run?: FactoryRunListItem | null;
    runs?: FactoryRunListItem[];
  };
  factor_governance?: {
    scheduler?: Record<string, unknown>;
    registry_summary?: Record<string, unknown>;
    active_pool?: Record<string, unknown>;
    model_registry_summary?: Record<string, unknown>;
    retrain_summary?: Record<string, unknown>;
    retrain_queue?: Record<string, unknown>[];
    recent_run?: Record<string, unknown>;
  };
  degraded?: boolean;
  errors?: string[];
};

export type FactoryMarketViewSectionErrors = {
  status?: string | null;
  snapshot?: string | null;
  runs?: string | null;
  observability?: string | null;
  capabilities?: string | null;
  expanded_run?: string | null;
};

export type FactoryMarketSurface = {
  snapshot_completion_ratio?: number | null;
  snapshot_failure_count?: number;
  snapshot_degraded?: boolean;
  failed_run_count?: number;
  overview_cards?: FactoryMarketMetricCard[];
  hero_cards?: FactoryMarketMetricCard[];
  observability_cards?: FactoryMarketMetricCard[];
  visible_outputs?: FactoryMarketVisibleOutput[];
};

export type FactoryMarketViewResponse = {
  dto_version?: string;
  generated_at?: string;
  selected_run_id?: string | null;
  degraded?: boolean;
  errors?: string[];
  section_errors?: FactoryMarketViewSectionErrors;
  capabilities?: CapabilityResponse;
  status?: FactoryStatusResponse | null;
  snapshot?: DailySnapshotResponse | null;
  runs?: FactoryRunsResponse;
  observability?: FactoryObservabilityResponse | null;
  expanded_run?: FactoryRunDetailResponse | null;
  surface?: FactoryMarketSurface;
};

function asRecord(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    return {};
  }
  return value as Record<string, unknown>;
}

function asRecordArray(value: unknown): Record<string, unknown>[] {
  if (!Array.isArray(value)) return [];
  return value.filter(
    (item): item is Record<string, unknown> => Boolean(item) && typeof item === 'object' && !Array.isArray(item),
  );
}

function asStringArray(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return value.map((item) => String(item ?? '').trim()).filter(Boolean);
}

function normalizeMetricCards(value: unknown): FactoryMarketMetricCard[] {
  return asRecordArray(value).map((item) => ({
    key: typeof item.key === 'string' ? item.key : undefined,
    label: typeof item.label === 'string' ? item.label : undefined,
    value: typeof item.value === 'string' ? item.value : undefined,
    tone: item.tone === 'success' || item.tone === 'danger' || item.tone === 'default' ? item.tone : undefined,
  }));
}

function normalizeVisibleOutputs(value: unknown): FactoryMarketVisibleOutput[] {
  return asRecordArray(value).map((item) => ({
    key: typeof item.key === 'string' ? item.key : undefined,
    kind: typeof item.kind === 'string' ? item.kind : undefined,
    title: typeof item.title === 'string' ? item.title : undefined,
    status: typeof item.status === 'string' ? item.status : undefined,
    summary: typeof item.summary === 'string' ? item.summary : undefined,
    evidence: typeof item.evidence === 'string' ? item.evidence : undefined,
    href: typeof item.href === 'string' ? item.href : item.href === null ? null : undefined,
    metadata: asRecord(item.metadata),
  }));
}

function normalizeObservabilityResponse(value: unknown): FactoryObservabilityResponse | null {
  const payload = asRecord(value);
  if (Object.keys(payload).length === 0) return null;
  const factory = asRecord(payload.factory);
  const factorGovernance = asRecord(payload.factor_governance);
  return {
    ...payload,
    overview: asRecord(payload.overview),
    factory: {
      ...factory,
      status: Object.keys(asRecord(factory.status)).length > 0 ? (factory.status as FactoryStatusResponse) : null,
      latest_run:
        Object.keys(asRecord(factory.latest_run)).length > 0 ? (factory.latest_run as FactoryRunListItem) : null,
      runs: asRecordArray(factory.runs) as FactoryRunListItem[],
    },
    factor_governance: {
      ...factorGovernance,
      scheduler: asRecord(factorGovernance.scheduler),
      registry_summary: asRecord(factorGovernance.registry_summary),
      active_pool: asRecord(factorGovernance.active_pool),
      model_registry_summary: asRecord(factorGovernance.model_registry_summary),
      retrain_summary: asRecord(factorGovernance.retrain_summary),
      retrain_queue: asRecordArray(factorGovernance.retrain_queue),
      recent_run: asRecord(factorGovernance.recent_run),
    },
    degraded: Boolean(payload.degraded),
    errors: asStringArray(payload.errors),
  };
}

export function normalizeFactoryMarketViewResponse(payload: unknown): FactoryMarketViewResponse {
  const raw = asRecord(payload);
  if (Object.keys(raw).length === 0) {
    throw new Error('factory market view response missing payload');
  }

  const runs = asRecord(raw.runs);
  const surface = asRecord(raw.surface);

  return {
    ...raw,
    dto_version: typeof raw.dto_version === 'string' ? raw.dto_version : 'strategy_market.factory_market_view.v1',
    generated_at: typeof raw.generated_at === 'string' ? raw.generated_at : undefined,
    selected_run_id:
      typeof raw.selected_run_id === 'string' ? raw.selected_run_id : raw.selected_run_id === null ? null : undefined,
    degraded: Boolean(raw.degraded),
    errors: asStringArray(raw.errors),
    section_errors: {
      status:
        raw.section_errors == null
          ? null
          : ((asRecord(raw.section_errors).status as string | null | undefined) ?? null),
      snapshot:
        raw.section_errors == null
          ? null
          : ((asRecord(raw.section_errors).snapshot as string | null | undefined) ?? null),
      runs:
        raw.section_errors == null ? null : ((asRecord(raw.section_errors).runs as string | null | undefined) ?? null),
      observability:
        raw.section_errors == null
          ? null
          : ((asRecord(raw.section_errors).observability as string | null | undefined) ?? null),
      capabilities:
        raw.section_errors == null
          ? null
          : ((asRecord(raw.section_errors).capabilities as string | null | undefined) ?? null),
      expanded_run:
        raw.section_errors == null
          ? null
          : ((asRecord(raw.section_errors).expanded_run as string | null | undefined) ?? null),
    },
    capabilities: asRecord(raw.capabilities) as CapabilityResponse,
    status: Object.keys(asRecord(raw.status)).length > 0 ? (raw.status as FactoryStatusResponse) : null,
    snapshot: Object.keys(asRecord(raw.snapshot)).length > 0 ? (raw.snapshot as DailySnapshotResponse) : null,
    runs: {
      ...runs,
      dto_version: typeof runs.dto_version === 'string' ? runs.dto_version : 'strategy_market.factory_runs.v2',
      latest: Object.keys(asRecord(runs.latest)).length > 0 ? (runs.latest as FactoryRunListItem) : null,
      items: asRecordArray(runs.items) as FactoryRunListItem[],
      count: Number.isFinite(Number(runs.count)) ? Number(runs.count) : asRecordArray(runs.items).length,
    },
    observability: normalizeObservabilityResponse(raw.observability),
    expanded_run:
      Object.keys(asRecord(raw.expanded_run)).length > 0 ? (raw.expanded_run as FactoryRunDetailResponse) : null,
    surface: {
      ...surface,
      snapshot_completion_ratio:
        surface.snapshot_completion_ratio == null || Number.isNaN(Number(surface.snapshot_completion_ratio))
          ? null
          : Number(surface.snapshot_completion_ratio),
      snapshot_failure_count: Number.isFinite(Number(surface.snapshot_failure_count))
        ? Number(surface.snapshot_failure_count)
        : 0,
      snapshot_degraded: Boolean(surface.snapshot_degraded),
      failed_run_count: Number.isFinite(Number(surface.failed_run_count)) ? Number(surface.failed_run_count) : 0,
      overview_cards: normalizeMetricCards(surface.overview_cards),
      hero_cards: normalizeMetricCards(surface.hero_cards),
      observability_cards: normalizeMetricCards(surface.observability_cards),
      visible_outputs: normalizeVisibleOutputs(surface.visible_outputs),
    },
  };
}
