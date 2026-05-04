'use client';

import { useCallback, useSyncExternalStore } from 'react';

export function useMobile(breakpoint = 768) {
  const query = `(max-width: ${breakpoint}px)`;

  const subscribe = useCallback((onStoreChange: () => void) => {
    if (typeof window === 'undefined') return () => {};
    const mq = window.matchMedia(query);

    const handler = () => onStoreChange();
    if (typeof mq.addEventListener === 'function') {
      mq.addEventListener('change', handler);
      return () => mq.removeEventListener('change', handler);
    }

    mq.addListener(handler);
    return () => mq.removeListener(handler);
  }, [query]);

  const getSnapshot = useCallback(() => {
    if (typeof window === 'undefined') return false;
    return window.matchMedia(query).matches;
  }, [query]);

  return useSyncExternalStore(subscribe, getSnapshot, () => false);
}
