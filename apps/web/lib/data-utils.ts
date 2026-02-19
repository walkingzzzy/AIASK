/** Utility helpers for extracting structured data from MCP API responses.
 *  MCP responses typically have shape: { data: { <field>: [...] }, tool?, meta? }
 *  After useApiMutation extracts envelope.data, we get the inner object.
 */

/** Try to find an array in the response, checking common nested patterns */
export function extractArray(data: unknown, ...keys: string[]): Record<string, unknown>[] {
  if (!data) return [];
  if (Array.isArray(data)) return data as Record<string, unknown>[];
  const obj = data as Record<string, unknown>;

  // Try specified keys first
  for (const k of keys) {
    const v = obj[k];
    if (Array.isArray(v)) return v as Record<string, unknown>[];
  }

  // Try obj.data.<key>
  if (obj.data && typeof obj.data === 'object' && !Array.isArray(obj.data)) {
    const inner = obj.data as Record<string, unknown>;
    for (const k of keys) {
      const v = inner[k];
      if (Array.isArray(v)) return v as Record<string, unknown>[];
    }
    // Fallback: first array found in inner
    for (const v of Object.values(inner)) {
      if (Array.isArray(v)) return v as Record<string, unknown>[];
    }
  }

  // Fallback: first array found at top level
  for (const v of Object.values(obj)) {
    if (Array.isArray(v)) return v as Record<string, unknown>[];
  }

  return [];
}

/** Extract a nested object, trying obj.data first */
export function extractObject(data: unknown): Record<string, unknown> {
  if (!data || typeof data !== 'object') return {};
  const obj = data as Record<string, unknown>;
  if (obj.data && typeof obj.data === 'object' && !Array.isArray(obj.data)) {
    return obj.data as Record<string, unknown>;
  }
  return obj;
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
