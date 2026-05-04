import { NextResponse } from 'next/server';

export function GET() {
  return new NextResponse(null, {
    status: 307,
    headers: { location: '/favicon.svg' },
  });
}
