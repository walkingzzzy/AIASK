/**
 * 通用折线图 / 柱状图
 */

import React, { useEffect, useMemo, useRef, useState } from 'react';
import * as echarts from 'echarts';

interface ChartSeries {
    name: string;
    data: number[];
}

interface ChartVariant {
    label: string;
    chartType: 'line' | 'bar';
    x: string[];
    series: ChartSeries[];
    unit?: string;
}

interface ChartView {
    views: Record<string, ChartVariant>;
    defaultView: string;
}

interface ChartPanelProps {
    title?: string;
    data: unknown;
}

const parseNumber = (value: unknown): number => {
    if (typeof value === 'number') return value;
    if (typeof value === 'string') {
        const normalized = value.replace(/[^0-9.-]/g, '');
        const parsed = Number.parseFloat(normalized);
        return Number.isNaN(parsed) ? 0 : parsed;
    }
    return 0;
};

const normalizeSingle = (data: unknown): Omit<ChartVariant, 'label'> | null => {
    if (!data || typeof data !== 'object') return null;
    const payload = data as Record<string, unknown>;

    if (Array.isArray(payload.x) && Array.isArray(payload.series)) {
        return {
            chartType: (payload.chartType as 'line' | 'bar') || 'line',
            x: payload.x as string[],
            series: payload.series as ChartSeries[],
            unit: payload.unit as string | undefined,
        };
    }

    if (Array.isArray(payload.daily)) {
        const daily = payload.daily as Array<{ date: string; total?: number }>;
        return {
            chartType: 'line',
            x: daily.map(item => item.date),
            series: [
                {
                    name: '北向资金',
                    data: daily.map(item => (item.total ?? 0) / 100000000),
                },
            ],
            unit: '亿',
        };
    }

    if (Array.isArray(payload.all)) {
        const list = payload.all as Array<{ name: string; netInflow?: string | number; netOutflow?: string | number }>;
        return {
            chartType: 'bar',
            x: list.map(item => item.name),
            series: [
                {
                    name: '板块资金',
                    data: list.map(item => {
                        const value = item.netInflow ?? item.netOutflow ?? 0;
                        return parseNumber(value);
                    }),
                },
            ],
            unit: '亿',
        };
    }

    if (Array.isArray(payload.sectors)) {
        const list = payload.sectors as Array<{ name: string; netInflow?: string | number; volume?: string | number }>;
        return {
            chartType: 'bar',
            x: list.map(item => item.name),
            series: [
                {
                    name: '板块资金',
                    data: list.map(item => parseNumber(item.netInflow ?? item.volume ?? 0)),
                },
            ],
            unit: '亿',
        };
    }

    return null;
};

const normalizeChartData = (data: unknown): ChartView | null => {
    if (!data || typeof data !== 'object') return null;
    const payload = data as Record<string, unknown>;

    if (payload.variants && typeof payload.variants === 'object') {
        const views: Record<string, ChartVariant> = {};
        const variants = payload.variants as Record<string, { label?: string; data?: unknown }>;
        Object.entries(variants).forEach(([key, value]) => {
            const normalized = normalizeSingle(value.data ?? value);
            if (normalized) {
                views[key] = {
                    label: value.label || key,
                    ...normalized,
                };
            }
        });

        const defaultView = (payload.defaultView as string) || Object.keys(views)[0];
        if (defaultView) {
            return { views, defaultView };
        }
        return null;
    }

    const single = normalizeSingle(payload);
    if (!single) return null;
    return {
        views: {
            default: { label: '资金流向', ...single },
        },
        defaultView: 'default',
    };
};

const ChartPanel: React.FC<ChartPanelProps> = ({ title, data }) => {
    const chartRef = useRef<HTMLDivElement>(null);
    const normalized = useMemo(() => normalizeChartData(data), [data]);
    const viewKeys = normalized ? Object.keys(normalized.views) : [];
    const [activeView, setActiveView] = useState<string>(normalized?.defaultView || '');

    useEffect(() => {
        if (normalized?.defaultView) {
            setActiveView(normalized.defaultView);
        }
    }, [normalized?.defaultView]);

    const currentView = normalized && activeView ? normalized.views[activeView] : undefined;

    useEffect(() => {
        if (!chartRef.current) return;
        const chart = echarts.init(chartRef.current);

        if (!currentView || currentView.x.length === 0) {
            chart.setOption({
                title: { text: '暂无图表数据', left: 'center', top: 'center' },
            });
            return () => chart.dispose();
        }

        const isLine = currentView.chartType === 'line';

        chart.setOption({
            title: {
                text: '',
            },
            legend: {
                data: currentView.series.map(seriesItem => seriesItem.name),
                top: 18,
                left: 'center',
                textStyle: { fontSize: 11 },
            },
            tooltip: {
                trigger: isLine ? 'axis' : 'item',
            },
            dataZoom: isLine
                ? [
                    { type: 'inside', start: 0, end: 100 },
                    { type: 'slider', height: 14 },
                ]
                : undefined,
            grid: { left: 20, right: 20, top: 60, bottom: isLine ? 20 : 40 },
            xAxis: {
                type: 'category',
                data: currentView.x,
                axisLabel: { interval: isLine ? 'auto' : 0, rotate: isLine ? 0 : 30 },
            },
            yAxis: {
                type: 'value',
                axisLabel: {
                    formatter: (value: number) => `${value}${currentView.unit || ''}`,
                },
            },
            series: currentView.series.map(seriesItem => ({
                name: seriesItem.name,
                type: currentView.chartType,
                data: seriesItem.data,
                smooth: isLine,
                symbolSize: isLine ? 6 : 0,
                barMaxWidth: isLine ? undefined : 24,
                itemStyle: !isLine
                    ? {
                        color: (params: { value: number }) => (params.value >= 0 ? '#ef5350' : '#26a69a'),
                    }
                    : undefined,
                markPoint: isLine
                    ? {
                        data: [
                            { type: 'max', name: '峰值' },
                            { type: 'min', name: '谷值' },
                        ],
                    }
                    : undefined,
            })),
        });

        const resizeObserver = new ResizeObserver(() => {
            chart.resize();
        });
        resizeObserver.observe(chartRef.current);

        return () => {
            resizeObserver.disconnect();
            chart.dispose();
        };
    }, [currentView]);

    return (
        <div className="visualization chart-panel">
            {title && <div className="visualization-title">{title}</div>}
            {viewKeys.length > 1 && (
                <div className="chart-toggle">
                    {viewKeys.map(key => (
                        <button
                            key={key}
                            className={key === activeView ? 'active' : ''}
                            onClick={() => setActiveView(key)}
                        >
                            {normalized?.views[key]?.label || key}
                        </button>
                    ))}
                </div>
            )}
            <div ref={chartRef} className="chart-panel-canvas" />
        </div>
    );
};

export default ChartPanel;
