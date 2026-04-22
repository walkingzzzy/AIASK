import { getBffOrigin } from '@/lib/bff-base';

function copyUpstreamAuthHeaders(upstream: Response) {
  const headers = new Headers();
  const upstreamContentType = upstream.headers.get('content-type');
  if (upstreamContentType) headers.set('content-type', upstreamContentType);

  const setCookies: string[] = typeof upstream.headers.getSetCookie === 'function'
    ? upstream.headers.getSetCookie()
    : [upstream.headers.get('set-cookie')].filter((value): value is string => Boolean(value));
  for (const value of setCookies) {
    headers.append('set-cookie', value);
  }

  return headers;
}

export async function POST(request: Request) {
  const body = await request.text();
  const contentType = request.headers.get('content-type') ?? 'application/json';
  const cookie = request.headers.get('cookie');

  const upstream = await fetch(`${getBffOrigin()}/api/auth/register`, {
    method: 'POST',
    headers: {
      'content-type': contentType,
      ...(cookie ? { cookie } : {}),
    },
    body,
    cache: 'no-store',
    redirect: 'manual',
  });

  return new Response(await upstream.text(), {
    status: upstream.status,
    headers: copyUpstreamAuthHeaders(upstream),
  });
}
