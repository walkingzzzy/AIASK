import { refreshAuth, clearLoggedIn, redirectToLogin } from './auth';
import { getBffBaseUrl } from './bff-base';
import type { CacheMeta, Envelope } from '@aiask/shared-types';

export type { CacheMeta, Envelope } from '@aiask/shared-types';

/** Guard: only one redirect to login at a time */
let redirecting = false;

type AuthFetchOptions = {
  noStore?: boolean;
  redirectOnUnauthorized?: boolean;
};

async function redirectAfterAuthExpired(): Promise<never> {
  if (!redirecting) {
    redirecting = true;
    clearLoggedIn();
    redirectToLogin();
    setTimeout(() => { redirecting = false; }, 3000);
  }
  throw new Error('登录已过期');
}

async function authedFetchCore(
  path: string,
  init?: RequestInit,
  opts?: AuthFetchOptions,
): Promise<Response> {
  const headers: Record<string, string> = {};
  if (init?.headers) Object.assign(headers, init.headers);

  const requestInit: RequestInit = {
    ...init,
    headers,
    credentials: 'include',
    ...(opts?.noStore ? { cache: init?.cache ?? 'no-store' as RequestCache } : {}),
  };
  const bffBase = getBffBaseUrl();

  const resp = await fetch(`${bffBase}${path}`, requestInit);
  if (resp.status === 401) {
    const refreshed = await refreshAuth();
    if (refreshed) {
      return fetch(`${bffBase}${path}`, requestInit);
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
export async function authedFetch(path: string, init?: RequestInit, opts?: Omit<AuthFetchOptions, 'noStore'>): Promise<Response> {
  return authedFetchCore(path, init, opts);
}

/** Authenticated streaming fetch wrapper — aligns chat/SSE requests with authedFetch auth semantics. */
export async function authedStreamFetch(path: string, init?: RequestInit, opts?: Omit<AuthFetchOptions, 'noStore'>): Promise<Response> {
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
    const wrapperOnly = keys.every((key) => (
      key === 'data'
      || key === 'success'
      || key === 'ok'
      || key === 'traceId'
      || key === 'message'
      || key === 'error'
    ));

    if (!wrapperOnly) {
      return current;
    }

    current = record.data ?? null;
  }

  return current;
}

export function unwrapApiEnvelope<T = unknown>(payload: unknown): {
  data: unknown;
  traceId?: string;
  errorMessage?: string;
} {
  if (!payload || typeof payload !== 'object') {
    return { data: payload };
  }

  const envelope = payload as Envelope<T> & Record<string, unknown>;
  const traceId = typeof envelope.traceId === 'string' ? envelope.traceId : undefined;
  const statusFlag = typeof envelope.success === 'boolean'
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
