'use client';

import { useMemo } from 'react';
import { Chart } from './chart';
import { COLORS } from './chart-colors';

type Slice = { name: string; value: number; color?: string };

export function PieChart({
  data,
  height = 300,
  className = '',
  donut = false,
}: {
  data: Slice[];
  height?: number;
  className?: string;
  donut?: boolean;
}) {
  const option = useMemo(() => ({
    tooltip: { trigger: 'item', formatter: '{b}: {c} ({d}%)' },
    legend: { orient: 'vertical' as const, right: 10, top: 'center' },
    series: [{
      type: 'pie',
      radius: donut ? ['40%', '70%'] : '65%',
      center: ['40%', '50%'],
      data: data.map((d, i) => ({ name: d.name, value: d.value, itemStyle: { color: d.color ?? COLORS.series[i % COLORS.series.length] } })),
      emphasis: { itemStyle: { shadowBlur: 10, shadowOffsetX: 0, shadowColor: 'rgba(0,0,0,0.2)' } },
      label: { formatter: '{b}\n{d}%' },
    }],
  }), [data, donut]);

  return <Chart option={option} height={height} className={className} />;
}
