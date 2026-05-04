export const STOCK_CODE_RE = /^\d{6}$/;
export const SYSTEM_STOCK_FALLBACKS = new Set(['000001', '600519']);

export function normalizeStockCode(value: unknown): string {
  const code = String(value ?? '').trim();
  return STOCK_CODE_RE.test(code) ? code : '';
}

export function isSystemStockFallback(value: unknown): boolean {
  const code = normalizeStockCode(value);
  return Boolean(code && SYSTEM_STOCK_FALLBACKS.has(code));
}

export function hasStockConfirmation(value: unknown): boolean {
  return typeof value === 'string' && value.trim().length > 0;
}

export function trustedUserStockCode(code: unknown, confirmedAt?: unknown): string {
  const normalized = normalizeStockCode(code);
  if (!normalized) return '';
  return hasStockConfirmation(confirmedAt) || !isSystemStockFallback(normalized) ? normalized : '';
}

export function sanitizeUserStockContext<T extends { stockCode?: unknown; eventCode?: unknown; stockConfirmedAt?: unknown }>(
  context: T,
): T {
  const confirmed = hasStockConfirmation(context.stockConfirmedAt);
  const shouldDropStockCode = isSystemStockFallback(context.stockCode) && !confirmed;
  const shouldDropEventCode = isSystemStockFallback(context.eventCode) && !confirmed;
  if (!shouldDropStockCode && !shouldDropEventCode) return context;

  const next = { ...context } as T & {
    stockCode?: unknown;
    eventCode?: unknown;
    stockConfirmedAt?: unknown;
  };
  if (shouldDropStockCode) delete next.stockCode;
  if (shouldDropEventCode) delete next.eventCode;
  if (!next.stockCode && !next.eventCode) delete next.stockConfirmedAt;
  return next as T;
}
