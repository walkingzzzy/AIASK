import { NextRequest, NextResponse } from 'next/server';

function hasSessionToken(request: NextRequest) {
  return request.cookies.get('logged_in')?.value === '1';
}

const protectedPrefixes = ['/market', '/fundamental', '/research', '/alerts', '/strategy', '/risk', '/user', '/settings', '/assistant', '/tdx', '/fund-flow', '/factor', '/valuation', '/technical', '/sentiment', '/search', '/data', '/chat', '/paper-trading', '/watchlist', '/notifications'];

export function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;
  const hasSession = hasSessionToken(request);

  if (protectedPrefixes.some((prefix) => pathname.startsWith(prefix)) && !hasSession) {
    const loginUrl = request.nextUrl.clone();
    loginUrl.pathname = '/login';
    loginUrl.searchParams.set('redirect', pathname);
    return NextResponse.redirect(loginUrl);
  }

  if (pathname.startsWith('/login') && hasSession) {
    const marketUrl = request.nextUrl.clone();
    marketUrl.pathname = '/market';
    marketUrl.search = '';
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
  matcher: ['/market/:path*', '/fundamental/:path*', '/research/:path*', '/alerts/:path*', '/strategy/:path*', '/risk/:path*', '/user/:path*', '/settings/:path*', '/assistant/:path*', '/tdx/:path*', '/fund-flow/:path*', '/factor/:path*', '/valuation/:path*', '/technical/:path*', '/sentiment/:path*', '/search/:path*', '/data/:path*', '/chat/:path*', '/paper-trading/:path*', '/watchlist/:path*', '/notifications/:path*', '/login', '/register'],
};

