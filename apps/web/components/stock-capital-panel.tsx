'use client';

import { useMemo } from 'react';
import { SectionCard, KpiGrid, KpiCard } from '@/components/ui';
import { useApiQuery } from '@/hooks/use-api-query';
import { extractObject, extractArray, fmtNum, fmtPct, fmtAmount } from '@/lib/data-utils';
import { PieChart } from '@/components/charts';

/**
 * T-018: StockCapitalPanel
 * Shows share structure pie chart + top 10 shareholders table.
 */
export function StockCapitalPanel({ code }: { code: string }) {
    const capitalQ = useApiQuery<unknown>(
        `/fundamental/capital?code=${encodeURIComponent(code)}`,
        { parse: (raw) => raw },
    );

    const data = useMemo(() => {
        const obj = extractObject(capitalQ.data) as Record<string, unknown>;
        const totalShares = Number(obj.total_shares ?? obj.totalShares ?? obj.total_capital ?? 0);
        const floatShares = Number(obj.float_shares ?? obj.floatShares ?? obj.float_capital ?? 0);
        const restrictedShares = Number(obj.restricted_shares ?? obj.restrictedShares ?? 0) || Math.max(0, totalShares - floatShares);

        const rawHolders = Array.isArray(obj.holders)
            ? obj.holders
            : Array.isArray(obj.top_holders)
                ? obj.top_holders
                : Array.isArray(obj.top10)
                    ? obj.top10
                    : Array.isArray(obj.shareholders)
                        ? obj.shareholders
                        : [];

        const holders = rawHolders
            .slice(0, 10)
            .map((h: Record<string, unknown>) => ({
                name: String(h.name ?? h.holder_name ?? h.shareholder ?? ''),
                shares: Number(h.shares ?? h.hold_num ?? h.quantity ?? 0),
                ratio: Number(h.ratio ?? h.hold_ratio ?? h.percent ?? 0),
                change: String(h.change ?? h.in_de ?? h.direction ?? ''),
            }));

        return { totalShares, floatShares, restrictedShares, holders };
    }, [capitalQ.data]);

    if (capitalQ.isFetching && !capitalQ.data) {
        return <p className="text-text-secondary text-sm text-center py-4">加载股本数据...</p>;
    }

    if (!capitalQ.data) {
        return <p className="text-text-secondary text-sm text-center py-4">暂无股本数据</p>;
    }

    const pieData = [
        { name: '流通A股', value: data.floatShares },
        { name: '限售股', value: data.restrictedShares },
    ].filter((d) => d.value > 0);

    return (
        <div className="space-y-4">
            <KpiGrid cols={3}>
                <KpiCard title="总股本" value={fmtAmount(data.totalShares)} suffix="股" />
                <KpiCard title="流通股" value={fmtAmount(data.floatShares)} suffix="股" />
                <KpiCard title="限售股" value={fmtAmount(data.restrictedShares)} suffix="股" />
            </KpiGrid>

            {pieData.length > 0 && (
                <div>
                    <h4 className="text-sm font-semibold mb-2">股本结构</h4>
                    <PieChart data={pieData} height={200} />
                </div>
            )}

            {data.holders.length > 0 && (
                <div>
                    <h4 className="text-sm font-semibold mb-2">前十大股东</h4>
                    <div className="overflow-x-auto">
                        <table className="w-full text-sm">
                            <thead>
                                <tr className="border-b border-glass-border text-text-secondary text-xs">
                                    <th className="text-left py-1.5 px-2">#</th>
                                    <th className="text-left py-1.5 px-2">股东名称</th>
                                    <th className="text-right py-1.5 px-2">持股数</th>
                                    <th className="text-right py-1.5 px-2">占比</th>
                                    <th className="text-center py-1.5 px-2">变动</th>
                                </tr>
                            </thead>
                            <tbody>
                                {data.holders.map((h, i) => (
                                    <tr key={i} className="border-b border-glass-border/50 hover:bg-white/5">
                                        <td className="py-1.5 px-2 text-text-secondary">{i + 1}</td>
                                        <td className="py-1.5 px-2 max-w-[200px] truncate">{h.name}</td>
                                        <td className="py-1.5 px-2 text-right">{fmtAmount(h.shares)}</td>
                                        <td className="py-1.5 px-2 text-right">{fmtPct(h.ratio)}</td>
                                        <td className={`py-1.5 px-2 text-center ${h.change.includes('增') || h.change.includes('新') ? 'text-danger' :
                                            h.change.includes('减') ? 'text-success' : 'text-text-secondary'
                                            }`}>
                                            {h.change || '不变'}
                                        </td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                </div>
            )}
        </div>
    );
}
