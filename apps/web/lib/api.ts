import { ensureAccessToken, clearCookies, redirectToLogin } from './auth';
import type { CacheMeta } from '@aiask/shared-types';

export type { CacheMeta, Envelope } from '@aiask/shared-types';

export const BFF_BASE = process.env.NEXT_PUBLIC_BFF_BASE_URL ?? 'http://127.0.0.1:3001/api';

/** Authenticated fetch wrapper — handles token refresh + 401 redirect */
export async function authedFetch(path: string, init?: RequestInit): Promise<Response> {
  const token = await ensureAccessToken();
  if (!token) { clearCookies(); redirectToLogin(); throw new Error('未登录'); }
  const headers: Record<string, string> = { authorization: `Bearer ${token}` };
  if (init?.headers) Object.assign(headers, init.headers);
  const resp = await fetch(`${BFF_BASE}${path}`, { ...init, headers, cache: 'no-store' });
  if (resp.status === 401) { clearCookies(); redirectToLogin(); throw new Error('登录已过期'); }
  return resp;
}

export function fmt(v: unknown): string {
  return v == null || v === '' ? '-' : String(v);
}

export function cacheText(c?: CacheMeta['cache']): string {
  if (!c) return '-';
  return `${c.hit ? '命中' : '未命中'}(${c.backend ?? 'none'}) TTL=${c.ttlSeconds ?? '-'}s`;
}
