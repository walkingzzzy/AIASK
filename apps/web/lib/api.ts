import { refreshAuth, clearLoggedIn, redirectToLogin } from './auth';
import type { CacheMeta } from '@aiask/shared-types';

export type { CacheMeta, Envelope } from '@aiask/shared-types';

export const BFF_BASE = process.env.NEXT_PUBLIC_BFF_BASE_URL ?? 'http://localhost:3001/api';


/** Guard: only one redirect to login at a time */
let redirecting = false;

/** Authenticated fetch wrapper — relies on HttpOnly cookies, handles 401 auto-refresh */
export async function authedFetch(path: string, init?: RequestInit): Promise<Response> {
  const headers: Record<string, string> = {};
  if (init?.headers) Object.assign(headers, init.headers);

  const requestInit: RequestInit = {
    ...init,
    headers,
    credentials: 'include',
  };

  const resp = await fetch(`${BFF_BASE}${path}`, requestInit);
  if (resp.status === 401) {
    const refreshed = await refreshAuth();
    if (refreshed) {
      return fetch(`${BFF_BASE}${path}`, requestInit);
    }
    if (!redirecting) {
      redirecting = true;
      clearLoggedIn();
      redirectToLogin();
    }
    throw new Error('登录已过期');
  }
  return resp;
}

export function fmt(v: unknown): string {
  return v == null || v === '' ? '-' : String(v);
}

export function cacheText(c?: CacheMeta['cache']): string {
  if (!c) return '-';
  return `${c.hit ? '命中' : '未命中'}(${c.backend ?? 'none'}) TTL=${c.ttlSeconds ?? '-'}s`;
}
