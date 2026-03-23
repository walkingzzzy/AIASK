import { refreshAuth, clearLoggedIn, redirectToLogin } from './auth';
import { getBffBaseUrl } from './bff-base';
import type { CacheMeta, Envelope } from '@aiask/shared-types';

export type { CacheMeta, Envelope } from '@aiask/shared-types';

export const BFF_BASE = getBffBaseUrl();

/** Guard: only one redirect to login at a time */
let redirecting = false;

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
  opts?: { noStore?: boolean },
): Promise<Response> {
  const headers: Record<string, string> = {};
  if (init?.headers) Object.assign(headers, init.headers);

  const requestInit: RequestInit = {
    ...init,
    headers,
    credentials: 'include',
    ...(opts?.noStore ? { cache: init?.cache ?? 'no-store' as RequestCache } : {}),
  };

  const resp = await fetch(`${BFF_BASE}${path}`, requestInit);
  if (resp.status === 401) {
    const refreshed = await refreshAuth();
    if (refreshed) {
      return fetch(`${BFF_BASE}${path}`, requestInit);
    }
    return redirectAfterAuthExpired();
  }
  return resp;
}

/** Authenticated fetch wrapper — relies on HttpOnly cookies, handles 401 auto-refresh */
export async function authedFetch(path: string, init?: RequestInit): Promise<Response> {
  return authedFetchCore(path, init);
}

/** Authenticated streaming fetch wrapper — aligns chat/SSE requests with authedFetch auth semantics. */
export async function authedStreamFetch(path: string, init?: RequestInit): Promise<Response> {
  return authedFetchCore(path, init, { noStore: true });
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
    return { data: envelope.data ?? null, traceId };
  }

  return { data: payload, traceId };
}

export function fmt(v: unknown): string {
  return v == null || v === '' ? '-' : String(v);
}

export function cacheText(c?: CacheMeta['cache']): string {
  if (!c) return '-';
  return `${c.hit ? '命中' : '未命中'}(${c.backend ?? 'none'}) TTL=${c.ttlSeconds ?? '-'}s`;
}
