'use client';

import { useMemo } from 'react';
import { Chart } from './chart';
import { COLORS } from './chart-colors';

export function GaugeChart({
  value,
  min = 0,
  max = 100,
  title = '',
  height = 260,
  className = '',
  zones,
}: {
  value: number;
  min?: number;
  max?: number;
  title?: string;
  height?: number;
  className?: string;
  zones?: Array<{ start: number; end: number; color: string }>;
}) {
  const option = useMemo(() => ({
    series: [{
      type: 'gauge',
      min,
      max,
      progress: { show: true, width: 14 },
      axisLine: {
        lineStyle: {
          width: 14,
          color: zones
            ? zones.map((z) => [z.end / max, z.color])
            : [[0.3, COLORS.down], [0.7, COLORS.warning], [1, COLORS.up]],
        },
      },
      axisTick: { show: false },
      splitLine: { length: 10, lineStyle: { width: 2 } },
      pointer: { width: 5 },
      title: { show: !!title, offsetCenter: [0, '70%'], fontSize: 14 },
      detail: { valueAnimation: true, fontSize: 28, offsetCenter: [0, '40%'], formatter: '{value}' },
      data: [{ value, name: title }],
    }],
  }), [value, min, max, title, zones]);

  return <Chart option={option} height={height} className={className} />;
}
