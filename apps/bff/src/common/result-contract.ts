import type {
  ResultContract,
  ResultAction,
  ResultEvidenceItem,
  ResultFreshness,
  ResultLink,
  ResultPlatformMeta,
  ResultStatus,
  ResultSkillSuggestion,
  ResultStrategySuggestion,
  ResultView,
  ResultWorkbenchTask,
} from '@aiask/shared-types';

type ResultContractInput = {
  summary: string;
  status?: ResultStatus;
  availableViews?: ResultView[];
  recommendedActions?: ResultAction[];
  recommendedLinks?: ResultLink[];
  evidence?: ResultEvidenceItem[];
  riskNotes?: string[];
  freshness?: ResultFreshness | null;
  platformMeta?: ResultPlatformMeta | null;
  skillSuggestions?: ResultSkillSuggestion[];
  strategySuggestions?: ResultStrategySuggestion[];
  workbenchTask?: ResultWorkbenchTask | null;
};

export function asRecord(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    return {};
  }
  return value as Record<string, unknown>;
}

export function readPath(value: unknown, path: string): unknown {
  return path.split('.').reduce<unknown>((acc, key) => {
    if (!acc || typeof acc !== 'object' || Array.isArray(acc)) {
      return undefined;
    }
    return (acc as Record<string, unknown>)[key];
  }, value);
}

export function toText(value: unknown): string {
  if (typeof value === 'string') return value.trim();
  if (typeof value === 'number' || typeof value === 'boolean') return String(value);
  if (Array.isArray(value)) {
    return value.map((item) => toText(item)).filter(Boolean).join('；');
  }
  if (value && typeof value === 'object') {
    const record = value as Record<string, unknown>;
    const preferred = [
      'summary',
      'analysis',
      'conclusion',
      'description',
      'reason',
      'message',
      'label',
      'value',
    ];
    for (const key of preferred) {
      const text = toText(record[key]);
      if (text) return text;
    }
  }
  return '';
}

export function toTextArray(value: unknown): string[] {
  if (Array.isArray(value)) return value.map((item) => toText(item)).filter(Boolean);
  if (typeof value === 'string') {
    return value.split(/[;；\n]/).map((item) => item.trim()).filter(Boolean);
  }
  return [];
}

export function uniqueStrings(values: Array<string | null | undefined>) {
  return Array.from(new Set(values.map((item) => String(item ?? '').trim()).filter(Boolean)));
}

export function extractFreshness(
  payload: unknown,
  fallbackUpdatedAt?: string | null,
  label?: string | null,
): ResultFreshness | null {
  const root = asRecord(payload);
  const data = asRecord(root.data);
  const meta = asRecord(root.meta);
  const updatedAt = toText(
    meta.fetchedAt
      ?? meta.fetched_at
      ?? data.updated_at
      ?? data.updatedAt
      ?? root.updated_at
      ?? root.updatedAt,
  ) || toText(fallbackUpdatedAt);
  const asOf = toText(data.as_of ?? data.asOf ?? root.as_of ?? root.asOf) || null;
  const freshnessLabel = toText(label) || null;
  if (!updatedAt && !asOf && !freshnessLabel) {
    return null;
  }
  return {
    updatedAt: updatedAt || null,
    asOf,
    label: freshnessLabel,
  };
}

export function extractPlatformMeta(
  payload: unknown,
  options: {
    sourceTool?: string | null;
    referencePath?: string | null;
    freshnessLabel?: string | null;
  } = {},
): ResultPlatformMeta {
  const root = asRecord(payload);
  const meta = asRecord(root.meta);
  const transport = asRecord(meta.transport);
  const rawFallback = [
    ...toTextArray(meta.fallback_reason),
    ...toTextArray(meta.fallbackReason),
    ...toTextArray(transport.fallback_reason),
    ...toTextArray(transport.fallbackReason),
    ...toTextArray(root.fallback_reason),
    ...toTextArray(root.fallbackReason),
  ];
  const sourceChain = uniqueStrings([
    ...toTextArray(meta.source_chain),
    ...toTextArray(meta.sourceChain),
    ...toTextArray(transport.source_chain),
    ...toTextArray(transport.sourceChain),
  ]);
  const degraded = Boolean(
    root.degraded
      ?? meta.degraded
      ?? transport.degraded
      ?? rawFallback.length > 0,
  );
  return {
    sourceTool: toText(options.sourceTool ?? root.sourceTool ?? root.source_tool) || null,
    sourceChain,
    degraded,
    fallbackReason: uniqueStrings(rawFallback),
    freshnessLabel: toText(options.freshnessLabel) || null,
    referencePath: toText(options.referencePath) || null,
  };
}

export function buildResultContract(input: ResultContractInput): ResultContract {
  const availableViews: ResultView[] = input.availableViews?.length
    ? Array.from(new Set<ResultView>(input.availableViews))
    : ['summary', 'next_step'];
  const summary = input.summary.trim();
  return {
    summary,
    status: input.status ?? (input.platformMeta?.degraded ? 'degraded' : 'ready'),
    availableViews,
    recommendedActions: input.recommendedActions ?? [],
    recommendedLinks: input.recommendedLinks ?? [],
    evidence: input.evidence?.filter((item) => item.label && item.value) ?? [],
    riskNotes: uniqueStrings(input.riskNotes ?? []),
    freshness: input.freshness ?? null,
    platformMeta: input.platformMeta ?? null,
    skillSuggestions: input.skillSuggestions ?? [],
    strategySuggestions: input.strategySuggestions ?? [],
    workbenchTask: input.workbenchTask ?? null,
  };
}
