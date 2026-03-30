import { getBffOrigin } from '@/lib/bff-base';

export const dynamic = 'force-dynamic';

const PROBE_TIMEOUT_MS = 2500;

export async function GET() {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), PROBE_TIMEOUT_MS);

  try {
    const response = await fetch(`${getBffOrigin()}/api/health/mcp`, {
      method: 'GET',
      cache: 'no-store',
      signal: controller.signal,
    });

    return Response.json(
      {
        reachable: true,
        status: response.status,
      },
      {
        headers: {
          'cache-control': 'no-store, must-revalidate',
        },
      },
    );
  } catch {
    return Response.json(
      {
        reachable: false,
        status: 0,
      },
      {
        headers: {
          'cache-control': 'no-store, must-revalidate',
        },
      },
    );
  } finally {
    clearTimeout(timer);
  }
}
