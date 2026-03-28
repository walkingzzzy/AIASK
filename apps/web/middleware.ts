import { NextRequest, NextResponse } from 'next/server';

// UX-only guard: real security is enforced by BFF AuthGuard (JWT + HttpOnly cookie).
// The `logged_in` cookie is a non-HttpOnly hint set by the frontend — it cannot be
// trusted for security but prevents unauthenticated users from seeing a flash of
// protected content before the API rejects them.
const PROTECTED_PREFIXES = [
  '/',
  '/admin',
  '/market',
  '/stock',
  '/fundamental',
  '/research',
  '/alerts',
  '/strategy',
  '/strategy-market',
  '/risk',
  '/user',
  '/settings',
  '/assistant',
  '/fund-flow',
  '/factor',
  '/factor-analysis',
  '/valuation',
  '/technical',
  '/sentiment',
  '/search',
  '/data',
  '/chat',
  '/paper-trading',
  '/portfolio',
  '/watchlist',
  '/notifications',
  '/backtest',
  '/options',
  '/macro',
  '/events',
  '/execution',
  '/performance',
  '/screener',
  '/decision',
  '/workspace-templates',
  '/skills',
] as const;
const authPagePaths = ['/login', '/register'] as const;
function hasSessionToken(request: NextRequest) {
  return request.cookies.get('logged_in')?.value === '1';
}

function matchesPrefix(pathname: string, prefix: string) {
  return pathname === prefix || pathname.startsWith(`${prefix}/`);
}

function resolveRedirectTarget(request: NextRequest) {
  const raw = request.nextUrl.searchParams.get('redirect');
  if (!raw || !raw.startsWith('/')) return null;
  try {
    return new URL(raw, request.nextUrl.origin);
  } catch {
    return null;
  }
}

export function middleware(request: NextRequest) {
  const { pathname, search } = request.nextUrl;
  const hasSession = hasSessionToken(request);

  if (PROTECTED_PREFIXES.some((prefix) => matchesPrefix(pathname, prefix)) && !hasSession) {
    const loginUrl = request.nextUrl.clone();
    loginUrl.pathname = '/login';
    loginUrl.search = '';
    loginUrl.searchParams.set('redirect', `${pathname}${search}`);
    return NextResponse.redirect(loginUrl);
  }

  if (pathname.startsWith('/login') && hasSession) {
    const redirectTarget = resolveRedirectTarget(request);
    const marketUrl = request.nextUrl.clone();
    if (redirectTarget) {
      marketUrl.pathname = redirectTarget.pathname;
      marketUrl.search = redirectTarget.search;
    } else {
      marketUrl.pathname = '/market';
      marketUrl.search = '';
    }
    return NextResponse.redirect(marketUrl);
  }

  if (pathname.startsWith('/register') && hasSession) {
    const marketUrl = request.nextUrl.clone();
    marketUrl.pathname = '/market';
    marketUrl.search = '';
    return NextResponse.redirect(marketUrl);
  }

  return NextResponse.next();
}

export const config = {
  matcher: [
    '/',
    '/admin/:path*',
    '/market/:path*',
    '/stock/:path*',
    '/fundamental/:path*',
    '/research/:path*',
    '/alerts/:path*',
    '/strategy/:path*',
    '/strategy-market/:path*',
    '/risk/:path*',
    '/user/:path*',
    '/settings/:path*',
    '/assistant/:path*',
    '/fund-flow/:path*',
    '/factor/:path*',
    '/factor-analysis/:path*',
    '/valuation/:path*',
    '/technical/:path*',
    '/sentiment/:path*',
    '/search/:path*',
    '/data/:path*',
    '/chat/:path*',
    '/paper-trading/:path*',
    '/portfolio/:path*',
    '/watchlist/:path*',
    '/notifications/:path*',
    '/backtest/:path*',
    '/options/:path*',
    '/macro/:path*',
    '/events/:path*',
    '/execution/:path*',
    '/performance/:path*',
    '/screener/:path*',
    '/decision/:path*',
    '/workspace-templates/:path*',
    '/skills/:path*',
    '/login',
    '/register',
  ],
};
