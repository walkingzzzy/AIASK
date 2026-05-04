'use client';

import dynamic from 'next/dynamic';
import { useEffect, useRef, useState } from 'react';

const ReactECharts = dynamic(() => import('echarts-for-react'), { ssr: false });

// eslint-disable-next-line @typescript-eslint/no-explicit-any
export type ChartOption = Record<string, any>;

export function Chart({
  option,
  height = 360,
  className = '',
  loading = false,
}: {
  option: ChartOption;
  height?: number | string;
  className?: string;
  loading?: boolean;
}) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const [hasSize, setHasSize] = useState(false);

  useEffect(() => {
    const node = containerRef.current;
    if (!node) return;

    let rafId: number | null = null;
    const updateSize = () => {
      if (rafId != null) window.cancelAnimationFrame(rafId);
      rafId = window.requestAnimationFrame(() => {
        const rect = node.getBoundingClientRect();
        setHasSize(rect.width > 0 && rect.height > 0);
        rafId = null;
      });
    };

    updateSize();

    if (typeof ResizeObserver === 'undefined') {
      updateSize();
      return () => {
        if (rafId != null) window.cancelAnimationFrame(rafId);
      };
    }

    const observer = new ResizeObserver(updateSize);
    observer.observe(node);
    return () => {
      observer.disconnect();
      if (rafId != null) window.cancelAnimationFrame(rafId);
    };
  }, []);

  if (loading) {
    return (
      <div
        ref={containerRef}
        className={`flex items-center justify-center text-text-secondary ${className}`}
        style={{ height }}
      >
        加载中...
      </div>
    );
  }
  return (
    <div ref={containerRef} className={className} style={{ width: '100%', height, minHeight: height, minWidth: 0 }}>
      {hasSize ? <ReactECharts option={option} style={{ width: '100%', height: '100%' }} notMerge lazyUpdate /> : null}
    </div>
  );
}
