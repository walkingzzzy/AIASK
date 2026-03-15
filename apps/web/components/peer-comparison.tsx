'use client';

import { useMemo } from 'react';
import { SectionCard, KpiGrid, KpiCard, Badge } from '@/components/ui';
import { useApiQuery } from '@/hooks/use-api-query';
import { extractArray, fmtNum, fmtPct, fmtAmount } from '@/lib/data-utils';

/**
 * T-020: PeerComparisonTable
 * Shows top 10 peers in the same industry with key metrics.
 */
export function PeerComparisonTable({ code }: { code: string }) {
    const peerQ = useApiQuery<unknown>(
        `/fundamental/peers?code=${encodeURIComponent(code)}`,
        { parse: (raw) => raw },
    );

    const peers = useMemo(() => {
        const numOrNull = (value: unknown): number | null => {
            if (value == null || value === '') return null;
            const parsed = Number(value);
            return Number.isFinite(parsed) ? parsed : null;
        };

        const arr = extractArray(peerQ.data, 'peers', 'items', 'data', 'stocks');
        return arr.slice(0, 10).map((p: Record<string, unknown>) => ({
            code: String(p.code ?? p.stock_code ?? ''),
            name: String(p.name ?? p.stock_name ?? ''),
            marketCap: numOrNull(p.market_cap ?? p.marketCap ?? p.total_mv),
            pe: numOrNull(p.pe ?? p.PE ?? p.pe_ttm),
            pb: numOrNull(p.pb ?? p.PB),
            roe: numOrNull(p.roe ?? p.ROE),
            revenueGrowth: numOrNull(p.revenue_growth ?? p.revenueGrowth ?? p.rev_yoy),
            profitGrowth: numOrNull(p.profit_growth ?? p.profitGrowth ?? p.net_yoy),
            price: numOrNull(p.price ?? p.close),
            changePct: numOrNull(p.change_pct ?? p.changePercent ?? p.pct_chg),
        }));
    }, [peerQ.data]);

    if (peerQ.isFetching && peers.length === 0) {
        return <p className="text-text-secondary text-sm py-4 text-center">加载同行业数据...</p>;
    }

    if (peers.length === 0) {
        return <p className="text-text-secondary text-sm py-4 text-center">暂无同行业对比数据</p>;
    }

    return (
        <div className="overflow-x-auto">
            <table className="w-full text-sm">
                <thead>
                    <tr className="border-b border-glass-border text-text-secondary text-xs">
                        <th className="text-left py-2 px-2 whitespace-nowrap">代码</th>
                        <th className="text-left py-2 px-2 whitespace-nowrap">名称</th>
                        <th className="text-right py-2 px-2 whitespace-nowrap">市值</th>
                        <th className="text-right py-2 px-2 whitespace-nowrap">PE</th>
                        <th className="text-right py-2 px-2 whitespace-nowrap">PB</th>
                        <th className="text-right py-2 px-2 whitespace-nowrap">ROE</th>
                        <th className="text-right py-2 px-2 whitespace-nowrap">营收增速</th>
                        <th className="text-right py-2 px-2 whitespace-nowrap">利润增速</th>
                        <th className="text-right py-2 px-2 whitespace-nowrap">涨跌幅</th>
                    </tr>
                </thead>
                <tbody>
                    {peers.map((p) => {
                        const isTarget = p.code === code;
                        return (
                            <tr
                                key={p.code}
                                className={`border-b border-glass-border/50 ${isTarget ? 'bg-primary/10 font-semibold' : 'hover:bg-white/5'}`}
                            >
                                <td className="py-2 px-2 whitespace-nowrap">
                                    {p.code}
                                    {isTarget && <Badge variant="info" className="ml-1 text-[10px]">当前</Badge>}
                                </td>
                                <td className="py-2 px-2 whitespace-nowrap">{p.name || '--'}</td>
                                <td className="py-2 px-2 text-right whitespace-nowrap">{p.marketCap != null ? fmtAmount(p.marketCap) : '--'}</td>
                                <td className="py-2 px-2 text-right whitespace-nowrap">
                                    {p.pe == null ? '--' : p.pe > 0 ? fmtNum(p.pe, 1) : '亏损'}
                                </td>
                                <td className="py-2 px-2 text-right whitespace-nowrap">{p.pb != null ? fmtNum(p.pb, 2) : '--'}</td>
                                <td className="py-2 px-2 text-right whitespace-nowrap">{p.roe != null ? fmtPct(p.roe) : '--'}</td>
                                <td className={`py-2 px-2 text-right whitespace-nowrap ${p.revenueGrowth == null ? 'text-text-secondary' : p.revenueGrowth >= 0 ? 'text-danger' : 'text-success'}`}>
                                    {p.revenueGrowth != null ? fmtPct(p.revenueGrowth) : '--'}
                                </td>
                                <td className={`py-2 px-2 text-right whitespace-nowrap ${p.profitGrowth == null ? 'text-text-secondary' : p.profitGrowth >= 0 ? 'text-danger' : 'text-success'}`}>
                                    {p.profitGrowth != null ? fmtPct(p.profitGrowth) : '--'}
                                </td>
                                <td className={`py-2 px-2 text-right whitespace-nowrap ${p.changePct == null ? 'text-text-secondary' : p.changePct >= 0 ? 'text-danger' : 'text-success'}`}>
                                    {p.changePct != null ? `${p.changePct >= 0 ? '+' : ''}${fmtPct(p.changePct)}` : '--'}
                                </td>
                            </tr>
                        );
                    })}
                </tbody>
            </table>
        </div>
    );
}
