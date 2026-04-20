'use client';

import { usePathname } from 'next/navigation';

export function useStablePathname() {
  return usePathname() ?? '';
}
