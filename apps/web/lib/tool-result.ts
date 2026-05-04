'use client';

type JsonRecord = Record<string, unknown>;

const META_KEYS = new Set([
  'tool',
  'meta',
  'sourceTool',
  'sourceTools',
  'argsMatched',
  'result',
  'traceId',
  'success',
  'data',
  'error',
  'source',
  'cached',
  'timestamp',
  'source_chain',
  'attempted_sources',
  'fallback_used',
  'fallback_reason',
  'degraded',
  'degraded_reason',
  'local_fallback_used',
  'section_errors',
  'data_timestamp',
]);

function asRecord(value: unknown): JsonRecord | null {
  return value && typeof value === 'object' && !Array.isArray(value)
    ? value as JsonRecord
    : null;
}

export function unwrapToolPayload(raw: unknown): JsonRecord {
  const root = asRecord(raw);
  if (!root) return {};

  if (root.degraded === true || root.fallback_used === true || root.local_fallback_used === true) {
    return root;
  }

  const directData = asRecord(root.data);
  const base = directData ?? root;
  const result = asRecord(base.result);
  if (result?.degraded === true || result?.fallback_used === true || result?.local_fallback_used === true) {
    return result;
  }
  let payload = asRecord(result?.data) ?? result ?? base;

  const keys = Object.keys(payload).filter((key) => !META_KEYS.has(key));
  if (keys.length === 1) {
    const nested = asRecord(payload[keys[0]]);
    if (nested) {
      payload = nested;
    }
  }

  return payload;
}

export function extractToolError(raw: unknown): string | null {
  const root = asRecord(raw);
  if (!root) return null;

  const candidates = [
    root.error,
    root.fallback_reason,
    root.fallbackReason,
    root.degraded_reason,
    root.degradedReason,
    root.section_errors,
    asRecord(root.result)?.error,
    asRecord(root.result)?.fallback_reason,
    asRecord(root.result)?.fallbackReason,
    asRecord(root.result)?.degraded_reason,
    asRecord(root.result)?.degradedReason,
    asRecord(root.result)?.section_errors,
    asRecord(asRecord(root.result)?.data)?.error,
    asRecord(root.data)?.error,
  ];

  for (const candidate of candidates) {
    if (typeof candidate === 'string' && candidate.trim()) {
      return candidate;
    }
    const nested = asRecord(candidate);
    if (nested) {
      const message = nested.message ?? nested.code;
      if (typeof message === 'string' && message.trim()) {
        return message;
      }
      const values = Object.values(nested).map((item) => (typeof item === 'string' ? item.trim() : '')).filter(Boolean);
      if (values.length > 0) {
        return values.join('；');
      }
    }
  }

  return null;
}
