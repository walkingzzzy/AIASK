const FALLBACK_BFF_BASE_URL = 'http://localhost:3001/api';
const FALLBACK_WS_URL = 'ws://localhost:3001';

function jsonScript(value: unknown) {
  return `window.__AIASK_RUNTIME__=${JSON.stringify(value)};`;
}

function deriveWsUrl(bffBaseUrl: string) {
  try {
    const parsed = new URL(bffBaseUrl);
    parsed.protocol = parsed.protocol === 'https:' ? 'wss:' : 'ws:';
    parsed.pathname = '';
    parsed.search = '';
    parsed.hash = '';
    return parsed.toString().replace(/\/$/, '');
  } catch {
    return FALLBACK_WS_URL;
  }
}

export const dynamic = 'force-dynamic';

export function GET() {
  const bffBaseUrl = process.env.BFF_BASE_URL?.trim() || process.env.NEXT_PUBLIC_BFF_BASE_URL?.trim() || FALLBACK_BFF_BASE_URL;
  const wsUrl = process.env.WS_URL?.trim() || process.env.NEXT_PUBLIC_WS_URL?.trim() || deriveWsUrl(bffBaseUrl);

  return new Response(jsonScript({ bffBaseUrl, wsUrl }), {
    headers: {
      'content-type': 'application/javascript; charset=utf-8',
      'cache-control': 'no-store, must-revalidate',
    },
  });
}
