'use client';

import { usePathname } from 'next/navigation';
import { AlertToastProvider } from '@/components/alert-toast';
import { Spotlight } from '@/components/spotlight';
import { MobileBottomNav } from '@/components/mobile-nav';
import { WatchlistInit } from '@/components/watchlist-init';
import { isPublicPathname } from '@/lib/public-routes';

export function GlobalOverlays() {
  const pathname = usePathname();

  if (isPublicPathname(pathname)) {
    return null;
  }

  return (
    <>
      <AlertToastProvider />
      <Spotlight />
      <MobileBottomNav />
      <WatchlistInit />
    </>
  );
}
