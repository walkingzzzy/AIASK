import { refreshAuth, clearLoggedIn, hasLoggedInHint, redirectToLogin } from './auth';
import { markBffAvailable, markBffUnavailable } from './bff-availability';
import { getBffBaseUrl } from './bff-base';
import type { CacheMeta, Envelope } from '@aiask/shared-types';

export type { CacheMeta, Envelope } from '@aiask/shared-types';
export type ApiAcceptanceStatus = 'unavailable' | 'prerequisite_missing' | 'degraded';
export type DataTrustStatus = 'trusted' | 'degraded' | 'partial' | 'conflict' | 'empty' | 'unavailable' | 'unknown';
export type DataTrust = {
  status: DataTrustStatus;
  degraded: boolean;
  reasons: string[];
  qualityFlags: string[];
  sources: Array<Record<string, unknown>>;
  emptyReason?: string;
};
export type DataDisplayDisposition = 'trusted' | 'partial-valid' | 'degraded-valid' | 'valid-empty' | 'blocking';
export type DataDisplayDecision = {
  disposition: DataDisplayDisposition;
  status: DataTrustStatus;
  canRenderData: boolean;
  shouldShowQualityBanner: boolean;
  isBlocking: boolean;
  isValidEmpty: boolean;
  sampleCount: number;
  reasons: string[];
  blockingReason?: string;
};

export class ApiError extends Error {
  status?: number;
  code?: string;
  traceId?: string;
  acceptanceStatus?: ApiAcceptanceStatus;
  detail?: unknown;
  path?: string;
}

/** Guard: only one redirect to login at a time */
let redirecting = false;

type AuthFetchOptions = {
  noStore?: boolean;
  redirectOnUnauthorized?: boolean;
};

export function isAbortLikeError(error: unknown): boolean {
  if (error instanceof DOMException && error.name === 'AbortError') {
    return true;
  }
  if (!(error instanceof Error)) {
    return false;
  }
  return (
    error.name === 'AbortError'
    || /abort(?:ed|error)|the user aborted a request|signal is aborted/i.test(error.message)
  );
}

function buildAbortError(message = '请求已取消'): Error {
  if (typeof DOMException !== 'undefined') {
    return new DOMException(message, 'AbortError');
  }
  const error = new Error(message);
  error.name = 'AbortError';
  return error;
}

export function isPermissionDeniedErrorMessage(message: string | null | undefined): boolean {
  return /(?:^|\b)403(?:\b|$)|forbidden|permission denied|权限|无权/i.test(String(message ?? ''));
}

function extractApiErrorCode(payload: unknown): string | undefined {
  if (!payload || typeof payload !== 'object') return undefined;
  const body = payload as Record<string, unknown>;
  if (typeof body.code === 'string' && body.code.trim()) return body.code;
  if (body.error && typeof body.error === 'object') {
    const errorBody = body.error as Record<string, unknown>;
    if (typeof errorBody.code === 'string' && errorBody.code.trim()) return errorBody.code;
  }
  return undefined;
}

export function extractAcceptanceStatus(payload: unknown): ApiAcceptanceStatus | undefined {
  if (!payload || typeof payload !== 'object') return undefined;
  const body = payload as Record<string, unknown>;
  const value = body.acceptanceStatus;
  if (value === 'unavailable' || value === 'prerequisite_missing' || value === 'degraded') {
    return value;
  }
  return undefined;
}

export function extractTraceId(payload: unknown): string | undefined {
  return payload && typeof payload === 'object' && typeof (payload as { traceId?: unknown }).traceId === 'string'
    ? (payload as { traceId: string }).traceId
    : undefined;
}

export function buildApiError(
  payload: unknown,
  options: {
    status?: number;
    path?: string;
    fallbackMessage?: string;
  } = {},
): ApiError {
  const baseMessage = extractApiErrorMessage(payload, options.fallbackMessage ?? '请求失败');
  const traceId = extractTraceId(payload);
  const acceptanceStatus = extractAcceptanceStatus(payload);
  const pathSuffix = options.path ? ` @ ${options.path}` : '';
  const traceSuffix = traceId ? ` (traceId: ${traceId})` : '';
  const error = new ApiError(`${baseMessage}${pathSuffix}${traceSuffix}`);
  error.name = 'ApiError';
  error.status = options.status;
  error.code = extractApiErrorCode(payload);
  error.traceId = traceId;
  error.acceptanceStatus = acceptanceStatus;
  error.detail = payload && typeof payload === 'object' ? (payload as Record<string, unknown>).detail : undefined;
  error.path = options.path;
  return error;
}

async function redirectAfterAuthExpired(): Promise<never> {
  if (!redirecting) {
    redirecting = true;
    clearLoggedIn();
    redirectToLogin();
    setTimeout(() => {
      redirecting = false;
    }, 3000);
  }
  throw new Error('登录已过期');
}

async function authedFetchCore(path: string, init?: RequestInit, opts?: AuthFetchOptions): Promise<Response> {
  const headers: Record<string, string> = {};
  if (init?.headers) Object.assign(headers, init.headers);

  const requestInit: RequestInit = {
    ...init,
    headers,
    credentials: 'include',
    ...(opts?.noStore ? { cache: init?.cache ?? ('no-store' as RequestCache) } : {}),
  };
  const bffBase = getBffBaseUrl();

  let resp: Response;
  try {
    resp = await fetch(`${bffBase}${path}`, requestInit);
    markBffAvailable();
  } catch (error) {
    if (isAbortLikeError(error)) {
      throw buildAbortError();
    }
    markBffUnavailable();
    throw new Error(error instanceof Error ? '数据服务暂不可用' : '请求失败');
  }

  if (resp.status === 401) {
    if (opts?.redirectOnUnauthorized !== false || hasLoggedInHint()) {
      const refreshed = await refreshAuth();
      if (refreshed) {
        try {
          const retryResp = await fetch(`${bffBase}${path}`, requestInit);
          markBffAvailable();
          return retryResp;
        } catch (error) {
          if (isAbortLikeError(error)) {
            throw buildAbortError();
          }
          markBffUnavailable();
          throw new Error('数据服务暂不可用');
        }
      }
    }
    if (opts?.redirectOnUnauthorized === false) {
      clearLoggedIn();
      return resp;
    }
    return redirectAfterAuthExpired();
  }
  return resp;
}

/** Authenticated fetch wrapper — relies on HttpOnly cookies, handles 401 auto-refresh */
export async function authedFetch(
  path: string,
  init?: RequestInit,
  opts?: Omit<AuthFetchOptions, 'noStore'>,
): Promise<Response> {
  return authedFetchCore(path, init, opts);
}

/** Authenticated streaming fetch wrapper — aligns chat/SSE requests with authedFetch auth semantics. */
export async function authedStreamFetch(
  path: string,
  init?: RequestInit,
  opts?: Omit<AuthFetchOptions, 'noStore'>,
): Promise<Response> {
  return authedFetchCore(path, init, { ...opts, noStore: true });
}

export function extractApiErrorMessage(payload: unknown, fallback = '请求失败'): string {
  if (!payload || typeof payload !== 'object') return fallback;
  const body = payload as Record<string, unknown>;
  const error = body.error;

  if (typeof error === 'string' && error.trim()) {
    return error;
  }
  if (error && typeof error === 'object') {
    const errorBody = error as Record<string, unknown>;
    if (typeof errorBody.message === 'string' && errorBody.message.trim()) {
      return errorBody.message;
    }
    if (typeof errorBody.code === 'string' && errorBody.code.trim()) {
      return errorBody.code;
    }
  }
  if (typeof body.message === 'string' && body.message.trim()) {
    return body.message;
  }
  return fallback;
}

const TRUST_META_KEYS = new Set([
  'argsMatched',
  'argsTried',
  'attempted_sources',
  'backend_requested',
  'backend_used',
  'cached',
  'contract_meta',
  'data',
  'data_quality',
  'data_timestamp',
  'empty_reason',
  'error',
  'fallback_reason',
  'fallback_used',
  'local_fallback_used',
  'message',
  'meta',
  'ok',
  'quality_flags',
  'result',
  'result_contract',
  'source',
  'source_chain',
  'sourceTool',
  'sourceTools',
  'success',
  'timestamp',
  'tool',
  'traceId',
  'transport',
]);

function isRecord(value: unknown): value is Record<string, unknown> {
  return !!value && typeof value === 'object' && !Array.isArray(value);
}

function compactReason(value: unknown): string {
  if (typeof value === 'string') return value.trim();
  if (Array.isArray(value)) {
    return value.map((item) => compactReason(item)).filter(Boolean).join('；');
  }
  if (isRecord(value)) {
    const preferred = value.message ?? value.reason ?? value.code ?? value.detail;
    return compactReason(preferred);
  }
  return '';
}

function compactReasons(...values: unknown[]): string[] {
  return Array.from(
    new Set(
      values
        .flatMap((value) => {
          if (Array.isArray(value)) return value;
          return value == null ? [] : [value];
        })
        .map((value) => compactReason(value))
        .filter(Boolean),
    ),
  );
}

function readDataQuality(record: Record<string, unknown>): DataTrust | null {
  const quality = record.data_quality;
  if (!isRecord(quality)) return null;
  const rawStatus = String(quality.status ?? '').trim().toLowerCase();
  const status: DataTrustStatus = (
    rawStatus === 'trusted'
    || rawStatus === 'degraded'
    || rawStatus === 'partial'
    || rawStatus === 'conflict'
    || rawStatus === 'empty'
    || rawStatus === 'unavailable'
  ) ? rawStatus : 'unknown';
  const emptyReason = compactReason(quality.empty_reason);
  const reasons = compactReasons(quality.reasons, emptyReason);
  const qualityFlags = compactReasons(quality.quality_flags);
  const sources = Array.isArray(quality.sources)
    ? quality.sources.filter(isRecord)
    : [];
  return {
    status,
    degraded: ['degraded', 'partial', 'conflict', 'empty', 'unavailable'].includes(status),
    reasons,
    qualityFlags,
    sources,
    ...(emptyReason ? { emptyReason } : {}),
  };
}

function hasBusinessValue(value: unknown, seen = new Set<unknown>(), depth = 0): boolean {
  if (value == null || value === '') return false;
  if (Array.isArray(value)) return value.length > 0;
  if (!isRecord(value) || seen.has(value) || depth > 5) return true;
  seen.add(value);

  const businessKeys = Object.keys(value).filter((key) => !TRUST_META_KEYS.has(key));
  if (businessKeys.some((key) => hasBusinessValue(value[key], seen, depth + 1))) {
    return true;
  }
  if (businessKeys.length > 0) {
    return false;
  }
  return ['data', 'result'].some((key) => hasBusinessValue(value[key], seen, depth + 1));
}

function trustSampleCount(trust: DataTrust | null | undefined): number {
  if (!trust) return 0;
  return trust.sources.reduce((max, source) => {
    const raw = source.sampleCount ?? source.sample_count;
    const count = Number(raw);
    return Number.isFinite(count) && count > max ? count : max;
  }, 0);
}

function deriveBusinessSampleCount(value: unknown, seen = new Set<unknown>(), depth = 0): number {
  if (value == null || value === '') return 0;
  if (Array.isArray(value)) return value.length;
  if (!isRecord(value) || seen.has(value) || depth > 6) return value == null ? 0 : 1;
  seen.add(value);

  const directCount = Number(value.sampleCount ?? value.sample_count ?? value.count ?? value.totalCount ?? value.total_count);
  if (Number.isFinite(directCount) && directCount > 0) return directCount;

  const arrayKeys = [
    'kline',
    'points',
    'reports',
    'notices',
    'items',
    'blocks',
    'stocks',
    'flows',
    'trades',
    'quotes',
    'news',
    'data',
    'result',
  ];
  for (const key of arrayKeys) {
    const nested = value[key];
    if (Array.isArray(nested)) return nested.length;
  }

  if (isRecord(value.quote)) {
    const quote = value.quote;
    return [quote.price, quote.last, quote.changePercent, quote.change_pct, quote.volume]
      .some((item) => item != null && item !== '')
      ? 1
      : 0;
  }
  if (isRecord(value.orderBook)) {
    const orderBook = value.orderBook;
    return (Array.isArray(orderBook.bids) ? orderBook.bids.length : 0)
      + (Array.isArray(orderBook.asks) ? orderBook.asks.length : 0);
  }

  let nestedMax = 0;
  for (const [key, nested] of Object.entries(value)) {
    if (TRUST_META_KEYS.has(key)) continue;
    if (nested == null || nested === '') continue;
    const count = deriveBusinessSampleCount(nested, seen, depth + 1);
    if (count > nestedMax) nestedMax = count;
  }
  if (nestedMax > 0) return nestedMax;

  return Object.entries(value).some(
    ([key, nested]) => !TRUST_META_KEYS.has(key) && nested != null && nested !== '',
  )
    ? 1
    : 0;
}

function isEmptyShell(value: unknown): boolean {
  if (Array.isArray(value)) return false;
  if (!isRecord(value)) return false;
  const keys = Object.keys(value);
  if (keys.length === 0) return true;
  const hasWrapperSignal = keys.some((key) => TRUST_META_KEYS.has(key));
  return hasWrapperSignal && !hasBusinessValue(value);
}

function shouldEvaluateEmptyShell(path: string[]): boolean {
  if (path.length === 0) return true;
  const last = path[path.length - 1];
  return path.length === 1 && (last === 'data' || last === 'result' || last === 'payload');
}

function describeFallbackRecord(record: Record<string, unknown>, path: string[]): string | null {
  const pathKey = path.join('.');
  const isResultContractMeta = pathKey.includes('result_contract.platformMeta');
  const trust = readDataQuality(record);
  const acceptsPartialTrust = trust?.status === 'partial';
  const sampleCount = trustSampleCount(trust);
  const hasSamplesOrBusinessValue = sampleCount > 0 || hasBusinessValue(record);
  if (trust?.degraded && trust.status !== 'partial') {
    if (trust.status === 'degraded' && hasSamplesOrBusinessValue) return null;
    return compactReasons(trust.reasons, trust.qualityFlags, trust.emptyReason).join('；')
      || `数据质量状态为 ${trust.status}`;
  }
  if (record.success === false || record.ok === false) {
    return compactReason(record.error ?? record.message) || '上游返回失败状态';
  }
  if (record.degraded === true && !acceptsPartialTrust && !isResultContractMeta && !hasBusinessValue(record)) {
    return compactReason(
      record.message
        ?? record.fallback_reason
        ?? record.fallbackReason
        ?? record.degraded_reason
        ?? record.degradedReason,
    ) || '上游能力暂不可用';
  }
  if ((record.fallback_used === true || record.local_fallback_used === true) && !hasBusinessValue(record)) {
    return compactReason(record.fallback_reason ?? record.fallbackReason ?? record.message) || '上游能力已回退，不接受降级结果';
  }
  if (record.fallback && typeof record.fallback === 'object') {
    const fallback = record.fallback as Record<string, unknown>;
    if (fallback.used === true && !hasBusinessValue(record)) {
      return compactReason(fallback.reason) || '上游能力已回退，不接受降级结果';
    }
  }
  const fallbackReason = compactReason(record.fallback_reason ?? record.fallbackReason);
  if (fallbackReason && !acceptsPartialTrust && !isResultContractMeta && !hasBusinessValue(record)) return fallbackReason;
  const degradedReason = compactReason(record.degraded_reason ?? record.degradedReason);
  if (degradedReason && !acceptsPartialTrust && !isResultContractMeta && !hasBusinessValue(record)) return degradedReason;
  const sectionErrors = compactReason(record.section_errors);
  if (sectionErrors) return sectionErrors;
  const message = compactReason(record.message);
  if (/已返回空结果|降级到缓存|降级到空结果|暂时不可用/i.test(message)) {
    return message;
  }
  if (shouldEvaluateEmptyShell(path) && isEmptyShell(record)) {
    return '上游返回空壳数据';
  }
  return null;
}

function findFallbackReason(value: unknown, seen = new Set<unknown>(), depth = 0, path: string[] = []): string | null {
  if (value == null || depth > 6 || seen.has(value)) return null;
  if (!isRecord(value)) return null;
  seen.add(value);

  const ownReason = describeFallbackRecord(value, path);
  if (ownReason) return ownReason;
  const ownTrust = readDataQuality(value);
  if (ownTrust?.status === 'partial') return null;

  for (const [key, nested] of Object.entries(value)) {
    if (!nested || typeof nested !== 'object') continue;
    const hit = Array.isArray(nested)
      ? nested.map((item, index) => findFallbackReason(item, seen, depth + 1, [...path, key, String(index)])).find(Boolean)
      : findFallbackReason(nested, seen, depth + 1, [...path, key]);
    if (hit) return hit;
  }
  return null;
}

export function rejectFallbackPayload(payload: unknown, options: { allowEmpty?: boolean } = {}): string | null {
  const reason = findFallbackReason(payload);
  if (reason && options.allowEmpty && findDataTrust(payload)?.status === 'empty') return null;
  if (reason) return reason;
  if (isEmptyShell(payload)) return '上游返回空壳数据';
  return null;
}

export function classifyDataTrustForDisplay(payload: unknown, trustOverride?: DataTrust | null): DataDisplayDecision {
  const trust = trustOverride ?? extractDataTrust(payload);
  const fallbackReason = rejectFallbackPayload(payload, { allowEmpty: true });
  const sampleCount = Math.max(trustSampleCount(trust), deriveBusinessSampleCount(payload));
  const reasons = compactReasons(trust.reasons, trust.qualityFlags, trust.emptyReason, fallbackReason);
  const status = trust.status;
  const emptyShell = trust.qualityFlags.includes('empty_shell') || /空壳/.test(String(fallbackReason ?? ''));
  const blockingReason =
    fallbackReason
    || reasons[0]
    || (status === 'unavailable' ? '上游数据源不可用' : status === 'conflict' ? '上游数据源存在冲突' : undefined);

  if (emptyShell || fallbackReason || status === 'unavailable' || status === 'conflict') {
    return {
      disposition: 'blocking',
      status,
      canRenderData: false,
      shouldShowQualityBanner: false,
      isBlocking: true,
      isValidEmpty: false,
      sampleCount,
      reasons,
      blockingReason,
    };
  }

  if (status === 'empty') {
    return {
      disposition: 'valid-empty',
      status,
      canRenderData: false,
      shouldShowQualityBanner: false,
      isBlocking: false,
      isValidEmpty: true,
      sampleCount: 0,
      reasons,
    };
  }

  if (status === 'partial') {
    if (sampleCount > 0) {
      return {
        disposition: 'partial-valid',
        status,
        canRenderData: true,
        shouldShowQualityBanner: true,
        isBlocking: false,
        isValidEmpty: false,
        sampleCount,
        reasons,
      };
    }
    return {
      disposition: 'blocking',
      status,
      canRenderData: false,
      shouldShowQualityBanner: false,
      isBlocking: true,
      isValidEmpty: false,
      sampleCount,
      reasons,
      blockingReason: blockingReason ?? '部分可用数据未包含有效业务样本',
    };
  }

  if (status === 'degraded') {
    if (sampleCount > 0) {
      return {
        disposition: 'degraded-valid',
        status,
        canRenderData: true,
        shouldShowQualityBanner: true,
        isBlocking: false,
        isValidEmpty: false,
        sampleCount,
        reasons,
      };
    }
    return {
      disposition: 'blocking',
      status,
      canRenderData: false,
      shouldShowQualityBanner: false,
      isBlocking: true,
      isValidEmpty: false,
      sampleCount,
      reasons,
      blockingReason: blockingReason ?? '降级结果未包含有效业务样本',
    };
  }

  return {
    disposition: 'trusted',
    status,
    canRenderData: payload != null,
    shouldShowQualityBanner: false,
    isBlocking: false,
    isValidEmpty: false,
    sampleCount,
    reasons,
  };
}

function findDataTrust(value: unknown, seen = new Set<unknown>(), depth = 0): DataTrust | null {
  if (value == null || depth > 6 || seen.has(value)) return null;
  if (!isRecord(value)) return null;
  seen.add(value);
  const own = readDataQuality(value);
  if (own) return own;
  const platformMeta = value.result_contract && isRecord(value.result_contract)
    ? (value.result_contract as Record<string, unknown>).platformMeta
    : null;
  if (isRecord(platformMeta) && platformMeta.degraded === true) {
    const reasons = compactReasons(platformMeta.fallbackReason, platformMeta.degraded_reason);
    return {
      status: 'degraded',
      degraded: true,
      reasons: reasons.length > 0 ? reasons : ['result_contract platformMeta degraded'],
      qualityFlags: [],
      sources: [],
    };
  }
  for (const nested of Object.values(value)) {
    if (!nested || typeof nested !== 'object') continue;
    if (Array.isArray(nested)) {
      for (const item of nested) {
        const hit = findDataTrust(item, seen, depth + 1);
        if (hit) return hit;
      }
    } else {
      const hit = findDataTrust(nested, seen, depth + 1);
      if (hit) return hit;
    }
  }
  return null;
}

export function extractDataTrust(payload: unknown): DataTrust {
  const direct = findDataTrust(payload);
  if (direct) return direct;
  const fallbackReason = rejectFallbackPayload(payload);
  if (fallbackReason) {
    return {
      status: 'degraded',
      degraded: true,
      reasons: [fallbackReason],
      qualityFlags: [],
      sources: [],
    };
  }
  if (isEmptyShell(payload)) {
    return {
      status: 'empty',
      degraded: true,
      reasons: ['上游返回空壳数据'],
      qualityFlags: ['empty_shell'],
      sources: [],
      emptyReason: '上游返回空壳数据',
    };
  }
  return {
    status: 'trusted',
    degraded: false,
    reasons: [],
    qualityFlags: [],
    sources: [],
  };
}

export function getApiErrorAcceptanceStatus(error: unknown): ApiAcceptanceStatus | null {
  return error instanceof ApiError && error.acceptanceStatus ? error.acceptanceStatus : null;
}

export function isPrerequisiteMissingError(error: unknown): boolean {
  return getApiErrorAcceptanceStatus(error) === 'prerequisite_missing';
}

export function isUnavailableApiError(error: unknown): boolean {
  const status = getApiErrorAcceptanceStatus(error);
  return status === 'unavailable' || status === 'degraded';
}

function unwrapRedundantDataLayers(payload: unknown): unknown {
  let current = payload;
  for (let depth = 0; depth < 3; depth += 1) {
    if (!current || typeof current !== 'object' || Array.isArray(current)) {
      return current;
    }

    const record = current as Record<string, unknown>;
    if (!Object.prototype.hasOwnProperty.call(record, 'data')) {
      return current;
    }

    const keys = Object.keys(record);
    const wrapperOnly = keys.every(
      (key) =>
        key === 'data' ||
        key === 'success' ||
        key === 'ok' ||
        key === 'traceId' ||
        key === 'message' ||
        key === 'error',
    );

    if (!wrapperOnly) {
      return current;
    }

    current = record.data ?? null;
  }

  return current;
}

export function unwrapApiEnvelope<T = unknown>(
  payload: unknown,
): {
  data: unknown;
  traceId?: string;
  errorMessage?: string;
} {
  if (!payload || typeof payload !== 'object') {
    return { data: payload };
  }

  const envelope = payload as Envelope<T> & Record<string, unknown>;
  const traceId = typeof envelope.traceId === 'string' ? envelope.traceId : undefined;
  const statusFlag =
    typeof envelope.success === 'boolean'
      ? envelope.success
      : typeof envelope.ok === 'boolean'
        ? envelope.ok
        : undefined;

  if (statusFlag === false) {
    return {
      data: null,
      traceId,
      errorMessage: extractApiErrorMessage(envelope, '请求失败'),
    };
  }

  if (Object.prototype.hasOwnProperty.call(envelope, 'data')) {
    return { data: unwrapRedundantDataLayers(envelope.data ?? null), traceId };
  }

  return { data: unwrapRedundantDataLayers(payload), traceId };
}

export function fmt(v: unknown): string {
  return v == null || v === '' ? '-' : String(v);
}

export function cacheText(c?: CacheMeta['cache']): string {
  if (!c) return '-';
  return `${c.hit ? '命中' : '未命中'}(${c.backend ?? 'none'}) TTL=${c.ttlSeconds ?? '-'}s`;
}
