'use client';

import { useMemo } from 'react';
import { Chart } from './chart';
import { COLORS } from './chart-colors';

type WaterfallItem = { name: string; value: number };

/**
 * T-033: WaterfallChart
 * Portfolio return attribution breakdown (sector allocation / stock selection / interaction).
 */
export function WaterfallChart({
    data,
    height = 300,
    className = '',
}: {
    data: WaterfallItem[];
    height?: number;
    className?: string;
}) {
    const option = useMemo(() => {
        const categories = data.map((d) => d.name);
        // Calculate cumulative for "invisible" base bars
        const base: number[] = [];
        const values: number[] = [];
        let cum = 0;
        data.forEach((d) => {
            if (d.value >= 0) {
                base.push(cum);
                values.push(d.value);
                cum += d.value;
            } else {
                cum += d.value;
                base.push(cum);
                values.push(Math.abs(d.value));
            }
        });

        return {
            tooltip: {
                formatter: (p: any) => {
                    const idx = p.dataIndex;
                    if (p.seriesIndex === 0) return '';
                    const v = data[idx].value;
                    return `${data[idx].name}: ${v >= 0 ? '+' : ''}${v.toFixed(2)}%`;
                },
            },
            grid: { left: 60, right: 20, top: 20, bottom: 40 },
            xAxis: { type: 'category', data: categories, axisLabel: { fontSize: 11 } },
            yAxis: { type: 'value', axisLabel: { formatter: '{value}%', fontSize: 10 } },
            series: [
                {
                    name: 'base',
                    type: 'bar',
                    stack: 'waterfall',
                    itemStyle: { color: 'transparent' },
                    emphasis: { itemStyle: { color: 'transparent' } },
                    data: base,
                },
                {
                    name: '归因',
                    type: 'bar',
                    stack: 'waterfall',
                    data: values.map((v, i) => ({
                        value: v,
                        itemStyle: { color: data[i].value >= 0 ? COLORS.up : COLORS.down },
                    })),
                    label: {
                        show: true,
                        position: 'top',
                        fontSize: 10,
                        formatter: (p: any) => {
                            const orig = data[p.dataIndex].value;
                            return `${orig >= 0 ? '+' : ''}${orig.toFixed(2)}%`;
                        },
                    },
                },
            ],
        };
    }, [data]);

    if (!data.length) return <p className="text-text-secondary text-sm text-center py-4">暂无归因数据</p>;
    return <Chart option={option} height={height} className={className} />;
}
