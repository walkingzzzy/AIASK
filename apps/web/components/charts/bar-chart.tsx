'use client';

import { useMemo } from 'react';
import { Chart } from './chart';
import { COLORS, CHART_GRID } from './chart-colors';

type BarItem = { label: string; value: number; color?: string };

export function BarChart({
  items,
  height = 320,
  className = '',
  horizontal = false,
  yAxisName,
  colorByValue = false,
}: {
  items: BarItem[];
  height?: number;
  className?: string;
  horizontal?: boolean;
  yAxisName?: string;
  colorByValue?: boolean;
}) {
  const option = useMemo(() => {
    const labels = items.map((i) => i.label);
    const values = items.map((i) => i.value);
    const colors = colorByValue
      ? items.map((i) => (i.value >= 0 ? COLORS.up : COLORS.down))
      : items.map((i, idx) => i.color ?? COLORS.series[idx % COLORS.series.length]);

    const categoryAxis = { type: 'category' as const, data: labels };
    const valueAxis = { type: 'value' as const, name: yAxisName, scale: true };

    return {
      tooltip: { trigger: 'axis' },
      grid: { ...CHART_GRID, left: horizontal ? 100 : 50 },
      xAxis: horizontal ? valueAxis : categoryAxis,
      yAxis: horizontal ? categoryAxis : valueAxis,
      series: [{
        type: 'bar',
        data: values.map((v, i) => ({ value: v, itemStyle: { color: colors[i] } })),
      }],
    };
  }, [items, horizontal, yAxisName, colorByValue]);

  return <Chart option={option} height={height} className={className} />;
}
