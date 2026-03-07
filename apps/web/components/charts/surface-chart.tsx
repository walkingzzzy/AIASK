'use client';

import { useMemo, useState } from 'react';
import { Chart } from './chart';

/**
 * T-034: Options Greeks Surface Chart
 * 3D volatility surface (strike × expiry × IV) and Greeks sensitivity charts.
 */
export function SurfaceChart({
    data,
    height = 400,
    className = '',
}: {
    data: {
        strikes: number[];
        expiries: string[];
        ivMatrix: number[][]; // [expiry][strike]
        greeks?: {
            delta?: number[][];
            gamma?: number[][];
            theta?: number[][];
            vega?: number[][];
        };
    };
    height?: number;
    className?: string;
}) {
    const [view, setView] = useState<'iv' | 'delta' | 'gamma' | 'theta' | 'vega'>('iv');

    const option = useMemo(() => {
        const { strikes, expiries, ivMatrix, greeks } = data;

        let matrix: number[][];
        let title: string;
        let min: number;
        let max: number;

        switch (view) {
            case 'delta':
                matrix = greeks?.delta ?? ivMatrix;
                title = 'Delta';
                min = -1; max = 1;
                break;
            case 'gamma':
                matrix = greeks?.gamma ?? ivMatrix;
                title = 'Gamma';
                min = 0; max = Math.max(...matrix.flat());
                break;
            case 'theta':
                matrix = greeks?.theta ?? ivMatrix;
                title = 'Theta';
                min = Math.min(...matrix.flat()); max = 0;
                break;
            case 'vega':
                matrix = greeks?.vega ?? ivMatrix;
                title = 'Vega';
                min = 0; max = Math.max(...matrix.flat());
                break;
            default:
                matrix = ivMatrix;
                title = '隐含波动率 IV';
                min = 0; max = Math.max(...matrix.flat());
        }

        // Flatten to 3D data: [strikeIdx, expiryIdx, value]
        const surfaceData: [number, number, number][] = [];
        matrix.forEach((row, ei) => {
            row.forEach((val, si) => {
                surfaceData.push([si, ei, +val.toFixed(4)]);
            });
        });

        return {
            tooltip: {
                formatter: (p: any) => {
                    const [si, ei, v] = p.data;
                    return `行权价: ${strikes[si]}<br/>到期: ${expiries[ei]}<br/>${title}: ${v}`;
                },
            },
            grid: { left: 80, right: 40, top: 30, bottom: 60 },
            xAxis: { type: 'category', data: strikes.map(String), name: '行权价', axisLabel: { fontSize: 10 } },
            yAxis: { type: 'category', data: expiries, name: '到期日', axisLabel: { fontSize: 10 } },
            visualMap: {
                min, max,
                calculable: true,
                orient: 'horizontal',
                left: 'center',
                bottom: 0,
                inRange: {
                    color: view === 'theta'
                        ? ['#e74c3c', '#f1f2f6', '#27ae60']
                        : ['#3498db', '#2ecc71', '#f1c40f', '#e74c3c'],
                },
                textStyle: { fontSize: 10 },
            },
            series: [{
                type: 'heatmap',
                data: surfaceData,
                label: { show: surfaceData.length <= 100, fontSize: 9 },
                emphasis: { itemStyle: { shadowBlur: 10, shadowColor: 'rgba(0,0,0,0.5)' } },
            }],
        };
    }, [data, view]);

    if (!data.strikes.length || !data.expiries.length) {
        return <p className="text-text-secondary text-sm text-center py-8">暂无期权曲面数据</p>;
    }

    return (
        <div className={className}>
            <div className="flex gap-1 mb-2 justify-end">
                {(['iv', 'delta', 'gamma', 'theta', 'vega'] as const).map((v) => (
                    <button
                        key={v}
                        onClick={() => setView(v)}
                        className={`text-[11px] px-2 py-0.5 rounded cursor-pointer ${view === v
                                ? 'bg-primary/20 text-primary border border-primary/40'
                                : 'text-text-secondary border border-transparent'
                            }`}
                    >
                        {v === 'iv' ? 'IV曲面' : v.charAt(0).toUpperCase() + v.slice(1)}
                    </button>
                ))}
            </div>
            <Chart option={option} height={height} />
        </div>
    );
}
