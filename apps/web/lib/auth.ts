const BFF = process.env.NEXT_PUBLIC_BFF_BASE_URL ?? 'http://127.0.0.1:3001/api';

type RefreshResponse = { accessToken: string; refreshToken: string; expiresIn: number };

export function readCookie(name: string): string {
  const items = document.cookie.split(';').map((v) => v.trim());
  const hit = items.find((v) => v.startsWith(`${name}=`));
  return hit ? decodeURIComponent(hit.split('=').slice(1).join('=')) : '';
}

export function writeCookie(name: string, value: string, maxAge: number) {
  document.cookie = `${name}=${encodeURIComponent(value)}; Path=/; Max-Age=${maxAge}; SameSite=Lax`;
}

export function clearCookies() {
  document.cookie = 'access_token=; Path=/; Max-Age=0; SameSite=Lax';
  document.cookie = 'refresh_token=; Path=/; Max-Age=0; SameSite=Lax';
}

export function redirectToLogin(returnPath?: string) {
  const p = returnPath ?? window.location.pathname;
  window.location.href = `/login?redirect=${encodeURIComponent(p)}`;
}

export async function ensureAccessToken(): Promise<string | null> {
  const accessToken = readCookie('access_token');
  const refreshToken = readCookie('refresh_token');
  if (!accessToken && !refreshToken) return null;
  if (accessToken) {
    try {
      const me = await fetch(`${BFF}/auth/me`, { headers: { authorization: `Bearer ${accessToken}` }, cache: 'no-store' });
      if (me.ok && (await me.json())?.authenticated) return accessToken;
    } catch { /* fall through to refresh */ }
  }
  if (!refreshToken) return null;
  try {
    const resp = await fetch(`${BFF}/auth/refresh`, {
      method: 'POST', headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ refreshToken }), cache: 'no-store',
    });
    if (!resp.ok) return null;
    const d = (await resp.json()) as RefreshResponse;
    writeCookie('access_token', d.accessToken, d.expiresIn);
    writeCookie('refresh_token', d.refreshToken, 7 * 24 * 60 * 60);
    return d.accessToken;
  } catch { return null; }
}
