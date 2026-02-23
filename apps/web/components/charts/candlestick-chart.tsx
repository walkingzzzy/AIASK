'use client';

import { useMemo } from 'react';
import { Chart } from './chart';
import { COLORS } from './chart-colors';

type KlinePoint = { date: string; open: number; close: number; low: number; high: number; volume?: number };

function calcMA(data: KlinePoint[], period: number): (number | null)[] {
  return data.map((_, i) => {
    if (i < period - 1) return null;
    let sum = 0;
    for (let j = i - period + 1; j <= i; j++) sum += data[j].close;
    return +(sum / period).toFixed(2);
  });
}

export function CandlestickChart({
  data,
  height = 360,
  className = '',
  showMA = true,
  showVolume = true,
}: {
  data: KlinePoint[];
  height?: number;
  className?: string;
  showMA?: boolean;
  showVolume?: boolean;
}) {
  const hasVolume = showVolume && data.some((d) => d.volume != null && d.volume > 0);
  const dates = useMemo(() => data.map((d) => d.date.slice(0, 10)), [data]);

  const option = useMemo(() => {
    const grids = [{ left: 50, right: 20, top: 40, bottom: hasVolume ? '28%' : 40 }];
    const xAxes: Record<string, unknown>[] = [{ type: 'category', data: dates, boundaryGap: true }];
    const yAxes: Record<string, unknown>[] = [{ scale: true, splitArea: { show: true, areaStyle: { color: ['transparent', 'rgba(0,0,0,0.02)'] } } }];
    const series: Record<string, unknown>[] = [
      {
        type: 'candlestick',
        data: data.map((d) => [d.open, d.close, d.low, d.high]),
        itemStyle: { color: COLORS.up, color0: COLORS.down, borderColor: COLORS.up, borderColor0: COLORS.down },
      },
    ];

    if (showMA) {
      const maColors = ['#1a73e8', '#f59e0b', '#8b5cf6', '#ec4899'];
      [5, 10, 20, 60].forEach((p, i) => {
        series.push({
          name: `MA${p}`, type: 'line', data: calcMA(data, p),
          smooth: true, lineStyle: { width: 1 }, symbol: 'none',
          itemStyle: { color: maColors[i] },
        });
      });
    }

    const dataZoom = [
      { type: 'inside', xAxisIndex: hasVolume ? [0, 1] : [0], start: 0, end: 100 },
      { type: 'slider', xAxisIndex: hasVolume ? [0, 1] : [0], bottom: 4, height: 18, start: 0, end: 100 },
    ];

    if (hasVolume) {
      grids.push({ left: 50, right: 20, top: '76%' as unknown as number, bottom: 30 });
      xAxes.push({ type: 'category', data: dates, gridIndex: 1, boundaryGap: true, axisLabel: { show: false } });
      yAxes.push({ gridIndex: 1, scale: true, splitNumber: 2, axisLabel: { show: false }, splitLine: { show: false } });
      series.push({
        name: '成交量', type: 'bar', xAxisIndex: 1, yAxisIndex: 1,
        data: data.map((d) => ({
          value: d.volume ?? 0,
          itemStyle: { color: d.close >= d.open ? COLORS.up : COLORS.down, opacity: 0.5 },
        })),
      });
    }

    return {
      tooltip: { trigger: 'axis', axisPointer: { type: 'cross' } },
      legend: showMA ? { data: ['MA5', 'MA10', 'MA20', 'MA60'], top: 4, textStyle: { fontSize: 11 } } : undefined,
      grid: grids,
      xAxis: xAxes,
      yAxis: yAxes,
      dataZoom,
      series,
    };
  }, [data, dates, hasVolume, showMA]);

  if (!data.length) return <p className="text-text-secondary text-sm">暂无K线数据</p>;
  return <Chart option={option} height={height} className={className} />;
}
