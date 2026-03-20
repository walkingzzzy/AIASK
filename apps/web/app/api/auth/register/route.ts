import { getBffOrigin } from '@/lib/bff-base';

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

  const headers = new Headers();
  const upstreamContentType = upstream.headers.get('content-type');
  if (upstreamContentType) headers.set('content-type', upstreamContentType);

  const setCookie = upstream.headers.get('set-cookie');
  if (setCookie) headers.set('set-cookie', setCookie);

  return new Response(await upstream.text(), {
    status: upstream.status,
    headers,
  });
}

