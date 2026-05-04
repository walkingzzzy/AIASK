'use client';

import { useEffect, useState } from 'react';

export function useSlowFlag(active: boolean, delayMs = 6000) {
  const [slow, setSlow] = useState(false);

  useEffect(() => {
    const timer = window.setTimeout(() => setSlow(active), active ? delayMs : 0);
    return () => window.clearTimeout(timer);
  }, [active, delayMs]);

  return slow;
}
