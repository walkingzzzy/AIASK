'use client';

import { useMemo } from 'react';
import { Chart } from './chart';
import { COLORS, CHART_GRID } from './chart-colors';

type KlinePoint = { date: string; open: number; close: number; low: number; high: number; volume?: number };

export function CandlestickChart({
  data,
  height = 360,
  className = '',
}: {
  data: KlinePoint[];
  height?: number;
  className?: string;
}) {
  const option = useMemo(() => ({
    tooltip: { trigger: 'axis' },
    grid: CHART_GRID,
    xAxis: { type: 'category', data: data.map((d) => d.date.slice(0, 10)) },
    yAxis: { scale: true },
    series: [{
      type: 'candlestick',
      data: data.map((d) => [d.open, d.close, d.low, d.high]),
      itemStyle: { color: COLORS.up, color0: COLORS.down, borderColor: COLORS.up, borderColor0: COLORS.down },
    }],
  }), [data]);

  if (!data.length) return <p className="text-text-secondary text-sm">暂无K线数据</p>;
  return <Chart option={option} height={height} className={className} />;
}
