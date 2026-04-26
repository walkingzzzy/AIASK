'use client';

import type { ComponentProps } from 'react';
import ProgressiveWorkbenchSection from '@/components/progressive-workbench-section';
import { useMobile } from '@/hooks/use-mobile';
import { RESPONSIVE_BREAKPOINTS } from '@/lib/responsive-layout';

type ResponsiveResultWorkbenchProps = ComponentProps<typeof ProgressiveWorkbenchSection> & {
  compactMode?: 'hidden' | 'strip';
};

export default function ResponsiveResultWorkbench({
  compactMode = 'hidden',
  summaryMode = 'strip',
  ...props
}: ResponsiveResultWorkbenchProps) {
  const compactLayout = useMobile(RESPONSIVE_BREAKPOINTS.splitCollapse);

  if (compactLayout && compactMode === 'hidden') {
    return null;
  }

  return <ProgressiveWorkbenchSection {...props} summaryMode={summaryMode} />;
}
