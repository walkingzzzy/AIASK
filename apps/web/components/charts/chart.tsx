'use client';

import dynamic from 'next/dynamic';

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
  if (loading) {
    return (
      <div className={`flex items-center justify-center text-text-secondary ${className}`} style={{ height }}>
        加载中...
      </div>
    );
  }
  return <ReactECharts option={option} style={{ height }} className={className} notMerge lazyUpdate />;
}
