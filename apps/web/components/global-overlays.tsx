'use client';

import { AlertToastProvider } from '@/components/alert-toast';
import { Spotlight } from '@/components/spotlight';
import { MobileBottomNav } from '@/components/mobile-nav';
import { WatchlistInit } from '@/components/watchlist-init';
import { WorkspaceSync } from '@/components/workspace-sync';
import { useStablePathname } from '@/hooks/use-stable-pathname';
import { isPublicPathname } from '@/lib/public-routes';

export function GlobalOverlays() {
  const pathname = useStablePathname();

  if (isPublicPathname(pathname)) {
    return null;
  }

  return (
    <>
      <AlertToastProvider />
      <Spotlight />
      <MobileBottomNav />
      <WatchlistInit />
      <WorkspaceSync />
    </>
  );
}
