export type DataQualityStatus =
  | 'trusted'
  | 'degraded'
  | 'partial'
  | 'conflict'
  | 'empty'
  | 'unavailable';

export type DataQualitySource = {
  name: string;
  status: DataQualityStatus | 'failed';
  freshness?: string | null;
  error?: string | null;
  sampleCount?: number | null;
};

export type DataQuality = {
  status: DataQualityStatus;
  reasons: string[];
  sources: DataQualitySource[];
  quality_flags: string[];
  empty_reason?: string;
};

export function uniqueQualityReasons(values: unknown[]): string[] {
  return Array.from(
    new Set(
      values
        .flatMap((value) => {
          if (Array.isArray(value)) return value;
          return value == null ? [] : [value];
        })
        .map((value) => String(value ?? '').trim())
        .filter(Boolean),
    ),
  );
}

export function buildDataQuality(input: {
  status: DataQualityStatus;
  reasons?: unknown[];
  sources?: DataQualitySource[];
  qualityFlags?: unknown[];
  emptyReason?: string | null;
}): DataQuality {
  const emptyReason = input.emptyReason?.trim() || undefined;
  return {
    status: input.status,
    reasons: uniqueQualityReasons([
      ...(input.reasons ?? []),
      ...(emptyReason ? [emptyReason] : []),
    ]),
    sources: input.sources ?? [],
    quality_flags: uniqueQualityReasons(input.qualityFlags ?? []),
    ...(emptyReason ? { empty_reason: emptyReason } : {}),
  };
}

export function trustedDataQuality(sourceName: string, sampleCount?: number | null, freshness?: string | null): DataQuality {
  return buildDataQuality({
    status: 'trusted',
    sources: [{ name: sourceName, status: 'trusted', freshness, sampleCount }],
  });
}

export function degradedDataQuality(
  sourceName: string,
  reason: unknown,
  options: { sampleCount?: number | null; freshness?: string | null; qualityFlags?: unknown[] } = {},
): DataQuality {
  return buildDataQuality({
    status: 'degraded',
    reasons: [reason],
    qualityFlags: options.qualityFlags,
    sources: [{
      name: sourceName,
      status: 'degraded',
      freshness: options.freshness,
      sampleCount: options.sampleCount,
      error: String(reason ?? '').trim() || null,
    }],
  });
}

export function unavailableDataQuality(
  sourceName: string,
  reason: unknown,
  options: { emptyReason?: string | null; qualityFlags?: unknown[] } = {},
): DataQuality {
  const text = String(reason ?? '').trim() || 'source_unavailable';
  return buildDataQuality({
    status: 'unavailable',
    reasons: [text],
    qualityFlags: options.qualityFlags,
    emptyReason: options.emptyReason ?? text,
    sources: [{ name: sourceName, status: 'failed', error: text }],
  });
}
