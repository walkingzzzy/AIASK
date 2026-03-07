'use client';

import { useMemo, useState } from 'react';
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

function calcEMA(closes: number[], period: number): number[] {
  const ema: number[] = [];
  const k = 2 / (period + 1);
  closes.forEach((c, i) => {
    if (i === 0) ema.push(c);
    else ema.push(c * k + ema[i - 1] * (1 - k));
  });
  return ema;
}

function calcMACD(data: KlinePoint[], fast = 12, slow = 26, signal = 9) {
  const closes = data.map((d) => d.close);
  const emaFast = calcEMA(closes, fast);
  const emaSlow = calcEMA(closes, slow);
  const dif = emaFast.map((v, i) => +(v - emaSlow[i]).toFixed(4));
  const dea = calcEMA(dif, signal).map((v) => +v.toFixed(4));
  const hist = dif.map((v, i) => +((v - dea[i]) * 2).toFixed(4));
  return { dif, dea, hist };
}

function calcRSI(data: KlinePoint[], period = 14): (number | null)[] {
  const result: (number | null)[] = [];
  for (let i = 0; i < data.length; i++) {
    if (i < period) { result.push(null); continue; }
    let gains = 0, losses = 0;
    for (let j = i - period + 1; j <= i; j++) {
      const diff = data[j].close - data[j - 1].close;
      if (diff > 0) gains += diff; else losses -= diff;
    }
    const rs = losses === 0 ? 100 : gains / losses;
    result.push(+(100 - 100 / (1 + rs)).toFixed(2));
  }
  return result;
}

function calcKDJ(data: KlinePoint[], n = 9, m1 = 3, m2 = 3) {
  const kArr: (number | null)[] = [];
  const dArr: (number | null)[] = [];
  const jArr: (number | null)[] = [];
  let prevK = 50, prevD = 50;
  for (let i = 0; i < data.length; i++) {
    if (i < n - 1) { kArr.push(null); dArr.push(null); jArr.push(null); continue; }
    let high = -Infinity, low = Infinity;
    for (let j = i - n + 1; j <= i; j++) {
      if (data[j].high > high) high = data[j].high;
      if (data[j].low < low) low = data[j].low;
    }
    const rsv = high === low ? 50 : ((data[i].close - low) / (high - low)) * 100;
    const k = (2 / m1) * rsv + (1 - 2 / m1) * prevK;
    const d = (2 / m2) * k + (1 - 2 / m2) * prevD;
    const j = 3 * k - 2 * d;
    kArr.push(+k.toFixed(2));
    dArr.push(+d.toFixed(2));
    jArr.push(+j.toFixed(2));
    prevK = k; prevD = d;
  }
  return { k: kArr, d: dArr, j: jArr };
}

type SubIndicator = 'none' | 'macd' | 'rsi' | 'kdj';

export function CandlestickChart({
  data,
  height = 420,
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
  const [subIndicator, setSubIndicator] = useState<SubIndicator>('macd');
  const hasVolume = showVolume && data.some((d) => d.volume != null && d.volume > 0);
  const hasTime = data.length > 0 && data[0].date.length > 10;
  const dates = useMemo(() => data.map((d) => hasTime ? d.date.slice(5) : d.date.slice(0, 10)), [data, hasTime]);

  const hasSub = subIndicator !== 'none' && data.length > 0;
  const totalHeight = hasSub ? height + 120 : height;

  const option = useMemo(() => {
    // Grid layout
    const grids: Record<string, unknown>[] = [
      { left: 50, right: 20, top: 40, bottom: hasSub ? '40%' : hasVolume ? '28%' : 40 },
    ];
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

    let gridIdx = 1;

    // Volume sub-chart
    if (hasVolume) {
      grids.push({ left: 50, right: 20, top: hasSub ? '64%' : '76%', height: hasSub ? '10%' : '14%' });
      xAxes.push({ type: 'category', data: dates, gridIndex: gridIdx, boundaryGap: true, axisLabel: { show: false } });
      yAxes.push({ gridIndex: gridIdx, scale: true, splitNumber: 2, axisLabel: { show: false }, splitLine: { show: false } });
      series.push({
        name: '成交量', type: 'bar', xAxisIndex: gridIdx, yAxisIndex: gridIdx,
        data: data.map((d) => ({
          value: d.volume ?? 0,
          itemStyle: { color: d.close >= d.open ? COLORS.up : COLORS.down, opacity: 0.5 },
        })),
      });
      gridIdx++;
    }

    // Sub-indicator chart
    if (hasSub) {
      grids.push({ left: 50, right: 20, top: '78%', height: '16%' });
      xAxes.push({ type: 'category', data: dates, gridIndex: gridIdx, boundaryGap: true, axisLabel: { show: false } });
      yAxes.push({ gridIndex: gridIdx, scale: true, splitNumber: 2, axisLabel: { fontSize: 10 }, splitLine: { show: false } });

      if (subIndicator === 'macd') {
        const macd = calcMACD(data);
        series.push(
          { name: 'DIF', type: 'line', xAxisIndex: gridIdx, yAxisIndex: gridIdx, data: macd.dif, symbol: 'none', lineStyle: { width: 1, color: '#1a73e8' } },
          { name: 'DEA', type: 'line', xAxisIndex: gridIdx, yAxisIndex: gridIdx, data: macd.dea, symbol: 'none', lineStyle: { width: 1, color: '#f59e0b' } },
          {
            name: 'MACD', type: 'bar', xAxisIndex: gridIdx, yAxisIndex: gridIdx,
            data: macd.hist.map((v) => ({ value: v, itemStyle: { color: v >= 0 ? COLORS.up : COLORS.down } })),
          },
        );
      } else if (subIndicator === 'rsi') {
        series.push(
          { name: 'RSI(14)', type: 'line', xAxisIndex: gridIdx, yAxisIndex: gridIdx, data: calcRSI(data, 14), symbol: 'none', lineStyle: { width: 1, color: '#8b5cf6' } },
          { name: 'RSI(6)', type: 'line', xAxisIndex: gridIdx, yAxisIndex: gridIdx, data: calcRSI(data, 6), symbol: 'none', lineStyle: { width: 1, color: '#ec4899' } },
        );
        // Overbought/oversold reference lines
        yAxes[yAxes.length - 1] = {
          ...yAxes[yAxes.length - 1],
          min: 0, max: 100,
          axisLabel: { fontSize: 10 },
        };
      } else if (subIndicator === 'kdj') {
        const kdj = calcKDJ(data);
        series.push(
          { name: 'K', type: 'line', xAxisIndex: gridIdx, yAxisIndex: gridIdx, data: kdj.k, symbol: 'none', lineStyle: { width: 1, color: '#1a73e8' } },
          { name: 'D', type: 'line', xAxisIndex: gridIdx, yAxisIndex: gridIdx, data: kdj.d, symbol: 'none', lineStyle: { width: 1, color: '#f59e0b' } },
          { name: 'J', type: 'line', xAxisIndex: gridIdx, yAxisIndex: gridIdx, data: kdj.j, symbol: 'none', lineStyle: { width: 1, color: '#ec4899' } },
        );
      }
    }

    const xAxisIndices = Array.from({ length: gridIdx + 1 }, (_, i) => i);
    const dataZoom = [
      { type: 'inside', xAxisIndex: xAxisIndices, start: 0, end: 100 },
      { type: 'slider', xAxisIndex: xAxisIndices, bottom: 4, height: 18, start: 0, end: 100 },
    ];

    return {
      tooltip: { trigger: 'axis', axisPointer: { type: 'cross' } },
      legend: showMA ? { data: ['MA5', 'MA10', 'MA20', 'MA60'], top: 4, textStyle: { fontSize: 11 } } : undefined,
      grid: grids,
      xAxis: xAxes,
      yAxis: yAxes,
      dataZoom,
      series,
    };
  }, [data, dates, hasVolume, showMA, subIndicator, hasSub]);

  if (!data.length) return <p className="text-text-secondary text-sm">暂无K线数据</p>;

  return (
    <div className={className}>
      {/* Indicator selector */}
      <div className="flex gap-1 mb-2 justify-end">
        {(['none', 'macd', 'rsi', 'kdj'] as SubIndicator[]).map((ind) => (
          <button
            key={ind}
            onClick={() => setSubIndicator(ind)}
            className={`text-[11px] px-2 py-0.5 rounded cursor-pointer transition-colors ${subIndicator === ind
                ? 'bg-primary/20 text-primary border border-primary/40'
                : 'text-text-secondary hover:text-text border border-transparent'
              }`}
          >
            {ind === 'none' ? '无副图' : ind.toUpperCase()}
          </button>
        ))}
      </div>
      <Chart option={option} height={totalHeight} />
    </div>
  );
}
