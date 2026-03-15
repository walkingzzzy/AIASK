/** Utility helpers for extracting structured data from MCP API responses.
 *  MCP responses typically have shape: { data: { <field>: [...] }, tool?, meta? }
 *  After useApiMutation extracts envelope.data, we get the inner object.
 */

function isRecord(value: unknown): value is Record<string, unknown> {
  return !!value && typeof value === 'object' && !Array.isArray(value);
}

function findArray(value: unknown, keys: string[], seen = new Set<unknown>(), depth = 0): Record<string, unknown>[] {
  if (Array.isArray(value)) return value as Record<string, unknown>[];
  if (!isRecord(value) || seen.has(value) || depth > 6) return [];

  seen.add(value);

  for (const key of keys) {
    const nested = value[key];
    const hit = findArray(nested, [], seen, depth + 1);
    if (hit.length > 0) return hit;
  }

  for (const nested of Object.values(value)) {
    const hit = findArray(nested, keys, seen, depth + 1);
    if (hit.length > 0) return hit;
  }

  return [];
}

/** Try to find an array in the response, checking common nested patterns */
export function extractArray(data: unknown, ...keys: string[]): Record<string, unknown>[] {
  if (!data) return [];
  return findArray(data, keys);
}

function unwrapObject(data: unknown, depth = 0): Record<string, unknown> {
  if (!isRecord(data) || depth > 6) return {};

  for (const key of ['card', 'data', 'result']) {
    const candidate = data[key];
    if (isRecord(candidate)) {
      return unwrapObject(candidate, depth + 1);
    }
  }

  return data;
}

/** Extract a nested object, trying obj.data first */
export function extractObject(data: unknown): Record<string, unknown> {
  return unwrapObject(data);
}

/** Extract a numeric value from nested data */
export function extractNum(data: unknown, key: string): number | null {
  const obj = extractObject(data);
  const v = obj[key];
  if (v == null) return null;
  const n = Number(v);
  return isNaN(n) ? null : n;
}

/** Format number with fixed decimals, return '-' for null */
export function fmtNum(v: unknown, decimals = 2): string {
  if (v == null || v === '') return '-';
  const n = Number(v);
  if (isNaN(n)) return String(v);
  return n.toFixed(decimals);
}

/** Format large numbers (亿/万) */
export function fmtAmount(v: unknown): string {
  if (v == null || v === '') return '-';
  const n = Number(v);
  if (isNaN(n)) return String(v);
  if (Math.abs(n) >= 1e8) return (n / 1e8).toFixed(2) + '亿';
  if (Math.abs(n) >= 1e4) return (n / 1e4).toFixed(2) + '万';
  return n.toFixed(2);
}

/** Format percentage */
export function fmtPct(v: unknown, decimals = 2): string {
  if (v == null || v === '') return '-';
  const n = Number(v);
  if (isNaN(n)) return String(v);
  return n.toFixed(decimals) + '%';
}
