'use client';

import { useMemo } from 'react';
import { Chart } from './chart';
import { useApiQuery } from '@/hooks/use-api-query';
import { extractArray } from '@/lib/data-utils';

/**
 * T-031: SankeyChart
 * Northbound fund flow visualization: North → Industry → Stock.
 */
export function SankeyChart({
    height = 400,
    className = '',
}: {
    height?: number;
    className?: string;
}) {
    const flowQ = useApiQuery<unknown>('/fund-flow/north', {
        refetchInterval: 120000,
        parse: (raw) => raw,
    });

    const { nodes, links } = useMemo(() => {
        const flows = extractArray(flowQ.data, 'flows', 'items', 'data');
        const nodeSet = new Set<string>();
        const linkArr: { source: string; target: string; value: number }[] = [];

        nodeSet.add('北向资金');

        flows.forEach((f: Record<string, unknown>) => {
            const industry = String(f.industry ?? f.sector ?? f.行业 ?? '其他');
            const stock = String(f.name ?? f.stock_name ?? f.股票名称 ?? '');
            const amount = Math.abs(Number(f.amount ?? f.net_buy ?? f.净买入 ?? 0));

            if (amount <= 0) return;

            nodeSet.add(industry);
            if (stock) nodeSet.add(stock);

            // Check if link already exists for this industry
            const existing = linkArr.find((l) => l.source === '北向资金' && l.target === industry);
            if (existing) existing.value += amount;
            else linkArr.push({ source: '北向资金', target: industry, value: amount });

            if (stock) {
                linkArr.push({ source: industry, target: stock, value: amount });
            }
        });

        // If no data, provide sample structure
        if (linkArr.length === 0) {
            return { nodes: [], links: [] };
        }

        return {
            nodes: Array.from(nodeSet).map((n) => ({ name: n })),
            links: linkArr.slice(0, 50), // Limit for performance
        };
    }, [flowQ.data]);

    const option = useMemo(() => ({
        tooltip: { trigger: 'item', triggerOn: 'mousemove' },
        series: [{
            type: 'sankey',
            data: nodes,
            links,
            emphasis: { focus: 'adjacency' },
            lineStyle: { color: 'gradient', curveness: 0.5 },
            label: { fontSize: 11 },
            nodeWidth: 20,
            nodeGap: 12,
        }],
    }), [nodes, links]);

    if (flowQ.isFetching && nodes.length === 0) {
        return <p className="text-text-secondary text-sm text-center py-8">加载资金流向数据...</p>;
    }
    if (nodes.length === 0) {
        return <p className="text-text-secondary text-sm text-center py-8">暂无北向资金流向数据</p>;
    }

    return <Chart option={option} height={height} className={className} />;
}
