'use client';

import { useMemo } from 'react';
import { useSearchParams } from 'next/navigation';

export function useStableSearchParams() {
  const searchParams = useSearchParams();
  return useMemo(() => searchParams ?? new URLSearchParams(), [searchParams]);
}
