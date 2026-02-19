import { NextRequest, NextResponse } from 'next/server';

function hasSessionToken(request: NextRequest) {
  const accessToken = request.cookies.get('access_token')?.value;
  const refreshToken = request.cookies.get('refresh_token')?.value;
  return Boolean(
    (accessToken && accessToken.trim().length > 0) ||
      (refreshToken && refreshToken.trim().length > 0),
  );
}

const protectedPrefixes = ['/market', '/fundamental', '/research', '/alerts', '/strategy', '/risk', '/user', '/assistant', '/tdx', '/fund-flow', '/factor', '/valuation', '/technical', '/sentiment', '/search', '/data', '/chat'];

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

  return NextResponse.next();
}

export const config = {
  matcher: ['/market/:path*', '/fundamental/:path*', '/research/:path*', '/alerts/:path*', '/strategy/:path*', '/risk/:path*', '/user/:path*', '/assistant/:path*', '/tdx/:path*', '/fund-flow/:path*', '/factor/:path*', '/valuation/:path*', '/technical/:path*', '/sentiment/:path*', '/search/:path*', '/data/:path*', '/chat/:path*', '/login'],
};

