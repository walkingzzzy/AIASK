'use client';

import { useMemo } from 'react';
import { Chart } from './chart';
import { useApiQuery } from '@/hooks/use-api-query';
import { extractArray } from '@/lib/data-utils';

type TreemapTooltipParam = {
    name?: string;
    data?: { changePct?: number };
};

/**
 * T-030: TreemapChart
 * Sector heatmap where area = market cap weight, color = change percent.
 */
export function TreemapChart({
    height = 400,
    className = '',
}: {
    height?: number;
    className?: string;
}) {
    const sectorQ = useApiQuery<unknown>('/market/blocks?block_type=industry', {
        refetchInterval: 60000,
        parse: (raw) => raw,
    });

    const treeData = useMemo(() => {
        const sectors = extractArray(sectorQ.data, 'sectors', 'items', 'data', '板块');
        return sectors.map((s: Record<string, unknown>) => {
            const name = String(s.name ?? s.sector_name ?? s.板块名称 ?? '');
            const changePct = Number(s.change_pct ?? s.pct_chg ?? s.涨跌幅 ?? 0);
            const marketCap = Number(s.market_cap ?? s.total_mv ?? s.总市值 ?? Math.abs(changePct) * 100 + 100);
            const stocks = extractArray(s, 'stocks', 'items').slice(0, 5).map((st: Record<string, unknown>) => ({
                name: String(st.name ?? st.stock_name ?? ''),
                value: Number(st.market_cap ?? st.total_mv ?? 10),
                changePct: Number(st.change_pct ?? st.pct_chg ?? 0),
            }));

            return {
                name,
                value: marketCap,
                changePct,
                children: stocks.length > 0 ? stocks.map((st) => ({
                    name: st.name,
                    value: st.value,
                    itemStyle: { color: getHeatColor(st.changePct) },
                })) : undefined,
                itemStyle: { color: getHeatColor(changePct) },
                label: { formatter: `${name}\n${changePct >= 0 ? '+' : ''}${changePct.toFixed(2)}%` },
            };
        });
    }, [sectorQ.data]);

    const option = useMemo(() => ({
        tooltip: {
            formatter: (info: TreemapTooltipParam) => {
                const pct = info.data?.changePct ?? 0;
                return `<b>${info.name}</b><br/>涨跌: ${pct >= 0 ? '+' : ''}${Number(pct).toFixed(2)}%`;
            },
        },
        series: [{
            type: 'treemap',
            data: treeData,
            roam: false,
            nodeClick: false,
            width: '100%',
            height: '100%',
            breadcrumb: { show: true, top: 4 },
            label: { show: true, fontSize: 11, color: '#fff', textShadowBlur: 2, textShadowColor: 'rgba(0,0,0,0.5)' },
            levels: [
                { itemStyle: { borderColor: '#333', borderWidth: 2, gapWidth: 2 } },
                { itemStyle: { borderColor: '#555', borderWidth: 1, gapWidth: 1 } },
            ],
        }],
    }), [treeData]);

    if (sectorQ.isFetching && treeData.length === 0) {
        return <p className="text-text-secondary text-sm text-center py-8">加载板块数据...</p>;
    }
    if (treeData.length === 0) {
        return <p className="text-text-secondary text-sm text-center py-8">暂无板块数据</p>;
    }

    return <Chart option={option} height={height} className={className} />;
}

function getHeatColor(pct: number): string {
    if (pct >= 5) return '#c0392b';
    if (pct >= 3) return '#e74c3c';
    if (pct >= 1) return '#e67e73';
    if (pct >= 0) return '#f5b7b1';
    if (pct >= -1) return '#abebc6';
    if (pct >= -3) return '#58d68d';
    if (pct >= -5) return '#27ae60';
    return '#1e8449';
}
