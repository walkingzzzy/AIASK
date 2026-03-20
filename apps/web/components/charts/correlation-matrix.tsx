'use client';

import { useMemo, useState } from 'react';
import { Chart } from './chart';
import { useApiQuery } from '@/hooks/use-api-query';

/**
 * T-032: CorrelationMatrix
 * Portfolio stock correlation heatmap matrix (-1 to +1, color mapped).
 */
export function CorrelationMatrix({
    codes,
    height = 400,
    className = '',
}: {
    codes: string[];
    height?: number;
    className?: string;
}) {
    const [window, setWindow] = useState(60);
    type HeatmapTooltipParam = { data?: [number, number, number] };

    const corrQ = useApiQuery<unknown>(
        codes.length >= 2 ? `/portfolio/correlation?codes=${codes.join(',')}&window=${window}` : null,
        { parse: (raw) => raw },
    );

    const { labels, matrix } = useMemo(() => {
        const raw = corrQ.data as Record<string, unknown> | undefined;
        const corrMatrix = raw?.matrix ?? raw?.correlation ?? raw?.data;

        if (Array.isArray(corrMatrix) && corrMatrix.length > 0) {
            const lbls = (raw?.labels ?? raw?.names ?? codes) as string[];
            const data: [number, number, number][] = [];
            (corrMatrix as number[][]).forEach((row, i) => {
                row.forEach((val, j) => {
                    data.push([i, j, +val.toFixed(3)]);
                });
            });
            return { labels: lbls, matrix: data };
        }

        return { labels: codes, matrix: [] };
    }, [corrQ.data, codes]);

    const option = useMemo(() => ({
        tooltip: {
            formatter: (p: HeatmapTooltipParam) => {
                const [x, y, v] = p.data ?? [0, 0, 0];
                return `${labels[x]} × ${labels[y]}<br/>相关系数: <b>${v}</b>`;
            },
        },
        grid: { left: 80, right: 40, top: 40, bottom: 40 },
        xAxis: { type: 'category', data: labels, axisLabel: { fontSize: 10, rotate: 45 } },
        yAxis: { type: 'category', data: labels, axisLabel: { fontSize: 10 } },
        visualMap: {
            min: -1, max: 1,
            calculable: true,
            orient: 'horizontal',
            left: 'center',
            bottom: 0,
            inRange: { color: ['#27ae60', '#f1f2f6', '#e74c3c'] },
            textStyle: { fontSize: 10 },
        },
        series: [{
            type: 'heatmap',
            data: matrix,
            label: { show: matrix.length <= 64, fontSize: 10 },
            emphasis: { itemStyle: { shadowBlur: 10, shadowColor: 'rgba(0,0,0,0.5)' } },
        }],
    }), [labels, matrix]);

    if (codes.length < 2) {
        return <p className="text-text-secondary text-sm text-center py-8">请选择至少2只股票计算相关性</p>;
    }

    return (
        <div className={className}>
            <div className="flex gap-2 mb-2 justify-end">
                {[30, 60, 90, 180, 360].map((w) => (
                    <button
                        key={w}
                        onClick={() => setWindow(w)}
                        className={`text-[11px] px-2 py-0.5 rounded cursor-pointer ${window === w ? 'bg-primary/20 text-primary border border-primary/40' : 'text-text-secondary border border-transparent'
                            }`}
                    >
                        {w}天
                    </button>
                ))}
            </div>
            {corrQ.isFetching && matrix.length === 0 ? (
                <p className="text-text-secondary text-sm text-center py-8">计算相关性...</p>
            ) : matrix.length === 0 ? (
                <p className="text-text-secondary text-sm text-center py-8">暂无相关性数据</p>
            ) : (
                <Chart option={option} height={height} />
            )}
        </div>
    );
}
