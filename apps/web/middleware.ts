import { NextRequest, NextResponse } from 'next/server';

function hasSessionToken(request: NextRequest) {
  return request.cookies.get('logged_in')?.value === '1';
}

const protectedPrefixes = ['/admin', '/market', '/stock', '/fundamental', '/research', '/alerts', '/strategy', '/risk', '/user', '/settings', '/assistant', '/fund-flow', '/factor', '/valuation', '/technical', '/sentiment', '/search', '/data', '/chat', '/paper-trading', '/portfolio', '/watchlist', '/notifications'];

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

  if (protectedPrefixes.some((prefix) => pathname.startsWith(prefix)) && !hasSession) {
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
  matcher: ['/admin/:path*', '/market/:path*', '/stock/:path*', '/fundamental/:path*', '/research/:path*', '/alerts/:path*', '/strategy/:path*', '/risk/:path*', '/user/:path*', '/settings/:path*', '/assistant/:path*', '/fund-flow/:path*', '/factor/:path*', '/valuation/:path*', '/technical/:path*', '/sentiment/:path*', '/search/:path*', '/data/:path*', '/chat/:path*', '/paper-trading/:path*', '/portfolio/:path*', '/watchlist/:path*', '/notifications/:path*', '/login', '/register'],
};
