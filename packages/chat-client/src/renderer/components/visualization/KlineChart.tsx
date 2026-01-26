/**
 * K线图表
 */

import React, { useEffect, useRef, useState } from 'react';
import * as echarts from 'echarts';

interface KlineChartProps {
    title?: string;
    data: unknown;
}

type KlineItem = {
    date: string;
    open: number;
    close: number;
    low: number;
    high: number;
    volume?: number;
};

const calculateMA = (dayCount: number, data: KlineItem[]): Array<number | null> => {
    const result: Array<number | null> = [];
    for (let i = 0; i < data.length; i += 1) {
        if (i < dayCount) {
            result.push(null);
            continue;
        }
        let sum = 0;
        for (let j = 0; j < dayCount; j += 1) {
            sum += data[i - j].close;
        }
        result.push(Number((sum / dayCount).toFixed(2)));
    }
    return result;
};

const resolveIndex = (value: unknown, categories: string[], fallback: number): number => {
    if (typeof value === 'number') return Math.max(0, Math.min(categories.length - 1, value));
    if (typeof value === 'string') {
        const idx = categories.indexOf(value);
        if (idx >= 0) return idx;
    }
    return fallback;
};

const KlineChart: React.FC<KlineChartProps> = ({ title, data }) => {
    const chartRef = useRef<HTMLDivElement>(null);
    const [maSelection, setMaSelection] = useState({
        MA5: true,
        MA10: true,
        MA20: true,
        MA60: true,
    });
    const [rangeText, setRangeText] = useState('区间收益: --');

    useEffect(() => {
        if (!chartRef.current) return;

        const chart = echarts.init(chartRef.current);
        const payload = data && typeof data === 'object'
            ? (data as { klines?: KlineItem[]; name?: string; code?: string })
            : undefined;
        const klines = payload?.klines || [];

        if (klines.length === 0) {
            chart.setOption({
                title: { text: '暂无K线数据', left: 'center', top: 'center' },
            });
            return () => chart.dispose();
        }

        const categories = klines.map(k => k.date);
        const values = klines.map(k => [k.open, k.close, k.low, k.high]);
        const ma5 = calculateMA(5, klines);
        const ma10 = calculateMA(10, klines);
        const ma20 = calculateMA(20, klines);
        const ma60 = calculateMA(60, klines);

        const updateRangeReturn = (startIndex: number, endIndex: number) => {
            const start = klines[startIndex]?.close;
            const end = klines[endIndex]?.close;
            if (start === undefined || end === undefined) return;
            const change = ((end - start) / start) * 100;
            setRangeText(`区间收益: ${change.toFixed(2)}%`);
        };

        updateRangeReturn(0, klines.length - 1);

        chart.setOption({
            title: {
                text: title || `${payload?.name || ''} ${payload?.code || ''}`.trim(),
                left: 0,
                textStyle: { fontSize: 12 },
            },
            tooltip: {
                trigger: 'axis',
                axisPointer: { type: 'cross' },
            },
            legend: {
                data: ['K线', 'MA5', 'MA10', 'MA20', 'MA60'],
                top: 20,
                textStyle: { fontSize: 11 },
                selected: {
                    K线: true,
                    MA5: maSelection.MA5,
                    MA10: maSelection.MA10,
                    MA20: maSelection.MA20,
                    MA60: maSelection.MA60,
                },
            },
            dataZoom: [
                { type: 'inside', start: 0, end: 100 },
                { type: 'slider', height: 14 },
            ],
            grid: { left: 20, right: 20, top: 60, bottom: 20 },
            xAxis: {
                type: 'category',
                data: categories,
                scale: true,
                boundaryGap: false,
                axisLine: { onZero: false },
                splitLine: { show: false },
            },
            yAxis: {
                scale: true,
                splitLine: { show: true },
            },
            series: [
                {
                    type: 'candlestick',
                    name: 'K线',
                    data: values,
                    itemStyle: {
                        color: '#ef5350',
                        color0: '#26a69a',
                        borderColor: '#ef5350',
                        borderColor0: '#26a69a',
                    },
                },
                {
                    name: 'MA5',
                    type: 'line',
                    data: ma5,
                    smooth: true,
                    showSymbol: false,
                    lineStyle: { width: 1 },
                },
                {
                    name: 'MA10',
                    type: 'line',
                    data: ma10,
                    smooth: true,
                    showSymbol: false,
                    lineStyle: { width: 1 },
                },
                {
                    name: 'MA20',
                    type: 'line',
                    data: ma20,
                    smooth: true,
                    showSymbol: false,
                    lineStyle: { width: 1 },
                },
                {
                    name: 'MA60',
                    type: 'line',
                    data: ma60,
                    smooth: true,
                    showSymbol: false,
                    lineStyle: { width: 1 },
                },
            ],
        });

        chart.on('dataZoom', params => {
            const batch = (params as { batch?: Array<Record<string, unknown>> }).batch?.[0] || {};
            const hasStartValue = typeof batch.startValue !== 'undefined';
            const hasEndValue = typeof batch.endValue !== 'undefined';
            const startFallback = 0;
            const endFallback = klines.length - 1;

            const startIndex = hasStartValue
                ? resolveIndex(batch.startValue, categories, startFallback)
                : Math.round(((batch.start as number) || 0) / 100 * (klines.length - 1));
            const endIndex = hasEndValue
                ? resolveIndex(batch.endValue, categories, endFallback)
                : Math.round(((batch.end as number) || 100) / 100 * (klines.length - 1));

            updateRangeReturn(Math.min(startIndex, endIndex), Math.max(startIndex, endIndex));
        });

        const resizeObserver = new ResizeObserver(() => {
            chart.resize();
        });
        resizeObserver.observe(chartRef.current);

        return () => {
            resizeObserver.disconnect();
            chart.dispose();
        };
    }, [data, title, maSelection]);

    return (
        <div className="visualization kline-chart">
            {title && <div className="visualization-title">{title}</div>}
            <div className="kline-controls">
                <span>均线</span>
                {(['MA5', 'MA10', 'MA20', 'MA60'] as const).map(key => (
                    <button
                        key={key}
                        className={maSelection[key] ? 'active' : ''}
                        onClick={() =>
                            setMaSelection(prev => ({
                                ...prev,
                                [key]: !prev[key],
                            }))
                        }
                    >
                        {key}
                    </button>
                ))}
                <span className="kline-range">{rangeText}</span>
            </div>
            <div ref={chartRef} className="kline-chart-canvas" />
        </div>
    );
};

export default KlineChart;
