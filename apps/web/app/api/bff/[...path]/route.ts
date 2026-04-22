import { getBffOrigin } from '@/lib/bff-base';

const HOP_BY_HOP_HEADERS = new Set([
  'connection',
  'content-length',
  'host',
  'keep-alive',
  'transfer-encoding',
]);

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

async function proxy(request: Request, context: { params: { path?: string[] } }) {
  const pathSegments = context.params.path ?? [];
  const upstreamUrl = buildUpstreamUrl(request.url, pathSegments);
  const method = request.method.toUpperCase();
  const body =
    method === 'GET' || method === 'HEAD'
      ? undefined
      : Buffer.from(await request.arrayBuffer());

  const upstream = await fetch(upstreamUrl, {
    method,
    headers: forwardRequestHeaders(request),
    body,
    cache: 'no-store',
    redirect: 'manual',
  });

  return new Response(upstream.body, {
    status: upstream.status,
    statusText: upstream.statusText,
    headers: copyResponseHeaders(upstream),
  });
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
