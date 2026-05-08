import { getBffOrigin } from '@/lib/bff-base';

const HOP_BY_HOP_HEADERS = new Set([
  'connection',
  'content-length',
  'host',
  'keep-alive',
  'transfer-encoding',
]);
const UPSTREAM_TIMEOUT_MS = 65_000;

export const dynamic = 'force-dynamic';
export const runtime = 'nodejs';
export const maxDuration = 120;

function buildUpstreamUrl(requestUrl: string, pathSegments: string[]) {
  const upstream = new URL(requestUrl);
  upstream.protocol = new URL(getBffOrigin()).protocol;
  upstream.host = new URL(getBffOrigin()).host;
  upstream.pathname = `/api/${pathSegments.join('/')}`;
  return upstream;
}

function forwardRequestHeaders(request: Request) {
  const headers = new Headers();
  request.headers.forEach((value, key) => {
    if (HOP_BY_HOP_HEADERS.has(key.toLowerCase())) return;
    headers.set(key, value);
  });
  return headers;
}

function copyResponseHeaders(upstream: Response) {
  const headers = new Headers();
  upstream.headers.forEach((value, key) => {
    if (HOP_BY_HOP_HEADERS.has(key.toLowerCase())) return;
    if (key.toLowerCase() === 'set-cookie') return;
    headers.set(key, value);
  });
  const setCookies: string[] = typeof upstream.headers.getSetCookie === 'function'
    ? upstream.headers.getSetCookie()
    : [upstream.headers.get('set-cookie')].filter((value): value is string => Boolean(value));
  for (const value of setCookies) {
    headers.append('set-cookie', value);
  }
  return headers;
}

function isAbortLikeError(error: unknown): boolean {
  if (error instanceof DOMException && error.name === 'AbortError') return true;
  if (!(error instanceof Error)) return false;
  return /abort(?:ed|error)|client closed|request was aborted|operation was aborted/i.test(error.message);
}

function jsonResponse(status: number, body: Record<string, unknown>) {
  return Response.json(body, { status });
}

function isStreamingPath(pathSegments: string[]) {
  const path = `/${pathSegments.join('/')}`;
  return path === '/chat/completions';
}

async function proxy(request: Request, context: { params: { path?: string[] } }) {
  const pathSegments = context.params.path ?? [];
  const upstreamUrl = buildUpstreamUrl(request.url, pathSegments);
  const method = request.method.toUpperCase();
  const body =
    method === 'GET' || method === 'HEAD'
      ? undefined
      : Buffer.from(await request.arrayBuffer());
  const streaming = isStreamingPath(pathSegments);
  const upstreamController = streaming ? null : new AbortController();
  const upstreamTimer = upstreamController
    ? setTimeout(() => upstreamController.abort(new DOMException('BFF upstream timeout', 'AbortError')), UPSTREAM_TIMEOUT_MS)
    : null;

  try {
    const upstream = await fetch(upstreamUrl, {
      method,
      headers: forwardRequestHeaders(request),
      body,
      cache: 'no-store',
      redirect: 'manual',
      signal: streaming ? request.signal : upstreamController?.signal,
    });

    const headers = copyResponseHeaders(upstream);
    const contentType = upstream.headers.get('content-type') ?? '';
    if (/text\/event-stream|application\/x-ndjson/i.test(contentType)) {
      return new Response(upstream.body, {
        status: upstream.status,
        statusText: upstream.statusText,
        headers,
      });
    }

    const payload = await upstream.arrayBuffer();
    return new Response(payload, {
      status: upstream.status,
      statusText: upstream.statusText,
      headers,
    });
  } catch (error) {
    if (streaming && (request.signal.aborted || isAbortLikeError(error))) {
      return new Response(null, { status: 499, statusText: 'Client Closed Request' });
    }
    if (upstreamController?.signal.aborted) {
      return jsonResponse(504, {
        success: false,
        acceptanceStatus: 'degraded',
        error: {
          code: 'BFF_PROXY_UPSTREAM_TIMEOUT',
          message: 'BFF 代理等待上游服务响应较慢，请稍后重试',
          detail: error instanceof Error ? error.message : String(error),
        },
      });
    }
    return jsonResponse(503, {
      success: false,
      error: {
        code: 'BFF_PROXY_UPSTREAM_UNAVAILABLE',
        message: 'BFF 代理暂时无法连接上游服务',
        detail: error instanceof Error ? error.message : String(error),
      },
    });
  } finally {
    if (upstreamTimer) clearTimeout(upstreamTimer);
  }
}

export async function GET(request: Request, context: { params: { path?: string[] } }) {
  return proxy(request, context);
}

export async function POST(request: Request, context: { params: { path?: string[] } }) {
  return proxy(request, context);
}

export async function PUT(request: Request, context: { params: { path?: string[] } }) {
  return proxy(request, context);
}

export async function PATCH(request: Request, context: { params: { path?: string[] } }) {
  return proxy(request, context);
}

export async function DELETE(request: Request, context: { params: { path?: string[] } }) {
  return proxy(request, context);
}

export async function HEAD(request: Request, context: { params: { path?: string[] } }) {
  return proxy(request, context);
}
