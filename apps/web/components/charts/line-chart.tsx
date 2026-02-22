'use client';

import { useMemo } from 'react';
import { Chart } from './chart';
import { COLORS, CHART_GRID } from './chart-colors';

type Series = {
  name: string;
  data: number[];
  type?: 'line' | 'bar';
  color?: string;
  areaStyle?: boolean;
  yAxisIndex?: number;
};

export function LineChart({
  categories,
  series,
  height = 320,
  className = '',
  yAxisName,
  y2AxisName,
  compact = false,
}: {
  categories: string[];
  series: Series[];
  height?: number;
  className?: string;
  yAxisName?: string;
  y2AxisName?: string;
  compact?: boolean;
}) {
  const option = useMemo(() => {
    const yAxis: Record<string, unknown>[] = [
      { type: 'value', name: compact ? undefined : yAxisName, scale: true, show: !compact },
    ];
    if (y2AxisName) yAxis.push({ type: 'value', name: y2AxisName, scale: true });
    return {
      tooltip: compact ? { show: false } : { trigger: 'axis' },
      legend: compact ? { show: false } : { data: series.map((s) => s.name) },
      grid: compact ? { top: 2, right: 2, bottom: 2, left: 2 } : CHART_GRID,
      xAxis: { type: 'category', data: categories, show: !compact },
      yAxis,
      series: series.map((s, i) => ({
        name: s.name,
        type: s.type ?? 'line',
        data: s.data,
        yAxisIndex: s.yAxisIndex ?? 0,
        smooth: true,
        symbol: compact ? 'none' : 'emptyCircle',
        itemStyle: { color: s.color ?? COLORS.series[i % COLORS.series.length] },
        ...(s.areaStyle || compact ? { areaStyle: { opacity: compact ? 0.1 : 0.15 } } : {}),
      })),
    };
  }, [categories, series, yAxisName, y2AxisName, compact]);

  return <Chart option={option} height={height} className={className} />;
}
