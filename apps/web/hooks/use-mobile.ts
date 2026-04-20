'use client';

import { useLayoutEffect, useState } from 'react';

export function useMobile(breakpoint = 768) {
  const [isMobile, setIsMobile] = useState(false);

  useLayoutEffect(() => {
    if (typeof window === 'undefined') return;
    const mq = window.matchMedia(`(max-width: ${breakpoint}px)`);
    setIsMobile(mq.matches);

    const handler = (e: MediaQueryListEvent) => setIsMobile(e.matches);
    if (typeof mq.addEventListener === 'function') {
      mq.addEventListener('change', handler);
      return () => mq.removeEventListener('change', handler);
    }

    mq.addListener(handler);
    return () => mq.removeListener(handler);
  }, [breakpoint]);

  return isMobile;
}
