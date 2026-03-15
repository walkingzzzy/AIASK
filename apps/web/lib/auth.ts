import { getBffBaseUrl } from './bff-base';

const BFF = getBffBaseUrl();

/** 设置非敏感登录指示器（供 middleware 判断） */
export function setLoggedIn() {
  document.cookie = 'logged_in=1; Path=/; Max-Age=604800; SameSite=Lax';
}

/** 清除登录指示器 */
export function clearLoggedIn() {
  document.cookie = 'logged_in=; Path=/; Max-Age=0; SameSite=Lax';
}

/** 跳转到登录页 */
export function redirectToLogin(returnPath?: string) {
  const p = returnPath ?? `${window.location.pathname}${window.location.search}`;
  window.location.href = `/login?redirect=${encodeURIComponent(p)}`;
}

/** Singleton refresh lock — prevents multiple parallel refresh calls */
let refreshPromise: Promise<boolean> | null = null;

/** 尝试用 HttpOnly refresh cookie 刷新 access token */
export async function refreshAuth(): Promise<boolean> {
  // If a refresh is already in flight, reuse it
  if (refreshPromise) return refreshPromise;

  refreshPromise = (async () => {
    try {
      const resp = await fetch(`${BFF}/auth/refresh`, {
        method: 'POST',
        credentials: 'include',
        cache: 'no-store',
      });
      return resp.ok;
    } catch {
      return false;
    } finally {
      refreshPromise = null;
    }
  })();

  return refreshPromise;
}
