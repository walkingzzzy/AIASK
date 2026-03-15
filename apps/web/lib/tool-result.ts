'use client';

type JsonRecord = Record<string, unknown>;

const META_KEYS = new Set([
  'tool',
  'meta',
  'code',
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

  const directData = asRecord(root.data);
  const base = directData ?? root;
  const result = asRecord(base.result);
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
    asRecord(root.result)?.error,
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
    }
  }

  return null;
}
