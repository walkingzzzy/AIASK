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
}: {
  categories: string[];
  series: Series[];
  height?: number;
  className?: string;
  yAxisName?: string;
  y2AxisName?: string;
}) {
  const option = useMemo(() => {
    const yAxis: Record<string, unknown>[] = [{ type: 'value', name: yAxisName, scale: true }];
    if (y2AxisName) yAxis.push({ type: 'value', name: y2AxisName, scale: true });
    return {
      tooltip: { trigger: 'axis' },
      legend: { data: series.map((s) => s.name) },
      grid: CHART_GRID,
      xAxis: { type: 'category', data: categories },
      yAxis,
      series: series.map((s, i) => ({
        name: s.name,
        type: s.type ?? 'line',
        data: s.data,
        yAxisIndex: s.yAxisIndex ?? 0,
        smooth: true,
        itemStyle: { color: s.color ?? COLORS.series[i % COLORS.series.length] },
        ...(s.areaStyle ? { areaStyle: { opacity: 0.15 } } : {}),
      })),
    };
  }, [categories, series, yAxisName, y2AxisName]);

  return <Chart option={option} height={height} className={className} />;
}
