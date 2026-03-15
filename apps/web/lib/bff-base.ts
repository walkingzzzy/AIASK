const FALLBACK_PROTOCOL = 'http:';
const FALLBACK_HOST = 'localhost';
const FALLBACK_PORT = '3001';
const LOCAL_LOOPBACK_HOSTS = new Set(['localhost', '127.0.0.1']);

function shouldRewriteLocalHostname(hostname: string, currentHostname: string) {
  return LOCAL_LOOPBACK_HOSTS.has(hostname) && LOCAL_LOOPBACK_HOSTS.has(currentHostname) && hostname !== currentHostname;
}

function rewriteLocalUrl(raw: string) {
  if (typeof window === 'undefined') return raw;
  try {
    const parsed = new URL(raw);
    if (shouldRewriteLocalHostname(parsed.hostname, window.location.hostname)) {
      parsed.hostname = window.location.hostname;
      return parsed.toString().replace(/\/$/, '');
    }
  } catch {
    // Ignore malformed env values and fall through.
  }
  return raw;
}

function envBase() {
  const raw = process.env.NEXT_PUBLIC_BFF_BASE_URL?.trim();
  return raw ? rewriteLocalUrl(raw) : null;
}

export function getBffBaseUrl() {
  const configured = envBase();
  if (configured) return configured;

  if (typeof window !== 'undefined') {
    return `${window.location.protocol}//${window.location.hostname}:${FALLBACK_PORT}/api`;
  }

  return `${FALLBACK_PROTOCOL}//${FALLBACK_HOST}:${FALLBACK_PORT}/api`;
}

export function getBffOrigin() {
  const configured = envBase();
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
