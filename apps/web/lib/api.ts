import { refreshAuth, clearLoggedIn, hasLoggedInHint, redirectToLogin } from './auth';
import { markBffAvailable, markBffUnavailable } from './bff-availability';
import { getBffBaseUrl } from './bff-base';
import type { CacheMeta, Envelope } from '@aiask/shared-types';

export type { CacheMeta, Envelope } from '@aiask/shared-types';
export type ApiAcceptanceStatus = 'unavailable' | 'prerequisite_missing' | 'degraded';

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

function findFirstRecord(value: unknown, seen = new Set<unknown>(), depth = 0): Record<string, unknown> | null {
  if (!value || typeof value !== 'object' || depth > 5 || seen.has(value)) return null;
  seen.add(value);
  if (!Array.isArray(value)) {
    const record = value as Record<string, unknown>;
    if (
      record.degraded === true ||
      record.fallback != null ||
      record.fallback_reason != null ||
      record.fallbackReason != null ||
      typeof record.message === 'string'
    ) {
      return record;
    }
    for (const nested of Object.values(record)) {
      const hit = findFirstRecord(nested, seen, depth + 1);
      if (hit) return hit;
    }
    return record;
  }
  for (const item of value) {
    const hit = findFirstRecord(item, seen, depth + 1);
    if (hit) return hit;
  }
  return null;
}

export function rejectFallbackPayload(payload: unknown): string | null {
  const record = findFirstRecord(payload);
  if (!record) return null;

  if (record.degraded === true) {
    return typeof record.message === 'string' && record.message.trim() ? record.message : '上游能力暂不可用';
  }
  if (record.fallback && typeof record.fallback === 'object') {
    const fallback = record.fallback as Record<string, unknown>;
    if (fallback.used === true) {
      return typeof fallback.reason === 'string' && fallback.reason.trim()
        ? fallback.reason
        : '上游能力已回退，不接受降级结果';
    }
  }
  const fallbackReason = record.fallback_reason ?? record.fallbackReason;
  if (Array.isArray(fallbackReason) && fallbackReason.some((item) => String(item).trim())) {
    return fallbackReason.map((item) => String(item).trim()).filter(Boolean).join('；');
  }
  if (typeof fallbackReason === 'string' && fallbackReason.trim()) {
    return fallbackReason.trim();
  }
  const message = typeof record.message === 'string' ? record.message.trim() : '';
  if (/已返回空结果|降级到缓存|降级到空结果|暂时不可用/i.test(message)) {
    return message;
  }
  return null;
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
