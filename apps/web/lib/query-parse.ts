export type JsonRecord = Record<string, unknown>;

export function isJsonRecord(value: unknown): value is JsonRecord {
  return !!value && typeof value === 'object' && !Array.isArray(value);
}

export function ensureRecord(raw: unknown, label: string): JsonRecord {
  if (!isJsonRecord(raw)) {
    throw new Error(`${label}返回结构异常（应为对象）`);
  }
  return raw;
}

export function ensureRecordOrArray(raw: unknown, label: string): JsonRecord | JsonRecord[] {
  if (Array.isArray(raw)) {
    return raw as JsonRecord[];
  }
  if (isJsonRecord(raw)) {
    return raw;
  }
  throw new Error(`${label}返回结构异常（应为对象或数组）`);
}

export function ensureArray(raw: unknown, label: string): JsonRecord[] {
  if (Array.isArray(raw)) {
    return raw as JsonRecord[];
  }
  throw new Error(`${label}返回结构异常（应为数组）`);
}

export function ensureHasAnyKey<T extends JsonRecord>(obj: T, keys: string[], label: string): T {
  if (!keys.some((k) => k in obj)) {
    throw new Error(`${label}缺少关键字段: ${keys.join(', ')}`);
  }
  return obj;
}

