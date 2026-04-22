const FALLBACK_PROTOCOL = 'http:';
const FALLBACK_HOST = 'localhost';
const FALLBACK_PORT = '3001';
const LOCAL_LOOPBACK_HOSTS = new Set(['localhost', '127.0.0.1']);
const SERVER_LOOPBACK_HOST = '127.0.0.1';

type RuntimePublicConfig = {
  bffBaseUrl?: string;
  wsUrl?: string;
};

declare global {
  interface Window {
    __AIASK_RUNTIME__?: RuntimePublicConfig;
  }
}

function shouldRewriteLocalHostname(hostname: string, currentHostname: string) {
  return LOCAL_LOOPBACK_HOSTS.has(hostname) && LOCAL_LOOPBACK_HOSTS.has(currentHostname) && hostname !== currentHostname;
}

function normalizeConfiguredUrl(raw: string) {
  const trimmed = raw.trim();
  if (!trimmed) return null;

  if (typeof window !== 'undefined' && trimmed.startsWith('/')) {
    return new URL(trimmed, window.location.origin).toString().replace(/\/$/, '');
  }

  try {
    const parsed = new URL(trimmed);
    if (typeof window !== 'undefined' && shouldRewriteLocalHostname(parsed.hostname, window.location.hostname)) {
      parsed.hostname = window.location.hostname;
    } else if (typeof window === 'undefined' && LOCAL_LOOPBACK_HOSTS.has(parsed.hostname)) {
      // Server-side route handlers should prefer a concrete loopback address so
      // local BFF fetches do not depend on IPv6 localhost resolution.
      parsed.hostname = SERVER_LOOPBACK_HOST;
    }
    return parsed.toString().replace(/\/$/, '');
  } catch {
    return null;
  }
}

function readRuntimeConfig(): RuntimePublicConfig | null {
  if (typeof window === 'undefined') return null;
  return window.__AIASK_RUNTIME__ ?? null;
}

function configuredBaseUrl() {
  const runtimeValue = readRuntimeConfig()?.bffBaseUrl;
  if (runtimeValue) {
    const normalized = normalizeConfiguredUrl(runtimeValue);
    if (normalized) return normalized;
  }

  const envValue = process.env.BFF_BASE_URL?.trim() || process.env.NEXT_PUBLIC_BFF_BASE_URL?.trim();
  if (!envValue) return null;
  return normalizeConfiguredUrl(envValue);
}

export function getBffBaseUrl() {
  const configured = configuredBaseUrl();
  if (configured) return configured;

  if (typeof window !== 'undefined') {
    return `${window.location.protocol}//${window.location.hostname}:${FALLBACK_PORT}/api`;
  }

  return `${FALLBACK_PROTOCOL}//${FALLBACK_HOST}:${FALLBACK_PORT}/api`;
}

export function getBffOrigin() {
  const configured = configuredBaseUrl();
  if (configured) {
    try {
      return new URL(configured).origin;
    } catch {
      // Fall through to runtime-derived defaults.
    }
  }

  if (typeof window !== 'undefined') {
    return `${window.location.protocol}//${window.location.hostname}:${FALLBACK_PORT}`;
  }

  return `${FALLBACK_PROTOCOL}//${FALLBACK_HOST}:${FALLBACK_PORT}`;
}

export function getRuntimeWsUrl() {
  const runtimeValue = readRuntimeConfig()?.wsUrl;
  if (runtimeValue) {
    const normalized = normalizeConfiguredUrl(runtimeValue);
    if (normalized) return normalized;
  }

  const envValue = process.env.WS_URL?.trim() || process.env.NEXT_PUBLIC_WS_URL?.trim();
  if (!envValue) return null;
  return normalizeConfiguredUrl(envValue);
}
