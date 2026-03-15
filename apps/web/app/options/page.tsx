'use client';

import { useMemo, useState } from 'react';
import { PageContainer, SectionCard } from '@/components/ui';
import { EmptyState, ErrorState, LoadingState } from '@/components/status-state';
import { useApiQuery } from '@/hooks/use-api-query';

type OptionChainItem = {
    type?: string;
    strike?: number;
    last?: number;
    lastPrice?: number;
    changePercent?: number;
    openInterest?: number;
    impliedVolatility?: number;
    iv?: number;
};

type OptionChainData = {
    underlying?: {
        code?: string;
        name?: string;
        price?: number;
        time?: string;
        date?: string;
    };
    selectedExpiry?: string[];
    options?: OptionChainItem[];
};

type GreeksData = {
    code?: string;
    option_type?: string;
    spot?: number;
    strike?: number;
    option_price?: string;
    volatility?: string;
    risk_free_rate?: string;
    time_to_maturity?: string;
    greeks?: Record<string, string>;
    interpretation?: Record<string, string>;
};

export default function OptionsPage() {
    const [symbol, setSymbol] = useState('510300'); // Default to 300 ETF
    const [querySymbol, setQuerySymbol] = useState('510300');

    const { data: chainData, isPending: chainLoading, error: chainError, refetch: refetchChain } = useApiQuery<OptionChainData>(
        `/v1/options/chain/${querySymbol}`,
        { staleTime: 60 * 1000 },
    );

    const { data: greeksData, isPending: greeksLoading, error: greeksError, refetch: refetchGreeks } = useApiQuery<GreeksData>(
        `/v1/options/greeks/${querySymbol}`,
        { staleTime: 60 * 1000 },
    );

    const pairedRows = useMemo(() => {
        const items = Array.isArray(chainData?.options) ? chainData.options : [];
        const map = new Map<number, { strike: number; call?: OptionChainItem; put?: OptionChainItem }>();

        items.forEach((item) => {
            const strike = Number(item.strike ?? 0);
            if (!Number.isFinite(strike) || strike <= 0) return;
            const current = map.get(strike) ?? { strike };
            if ((item.type ?? '').toLowerCase() === 'put') current.put = item;
            else current.call = item;
            map.set(strike, current);
        });

        return Array.from(map.values())
            .sort((a, b) => a.strike - b.strike)
            .slice(0, 20);
    }, [chainData]);

    const greekEntries = useMemo(() => {
        if (!greeksData?.greeks || typeof greeksData.greeks !== 'object') return [];
        return Object.entries(greeksData.greeks);
    }, [greeksData]);

    const interpretationEntries = useMemo(() => {
        if (!greeksData?.interpretation || typeof greeksData.interpretation !== 'object') return [];
        return Object.entries(greeksData.interpretation);
    }, [greeksData]);

    const handleSearch = (e: React.FormEvent) => {
        e.preventDefault();
        const nextSymbol = symbol.trim().toUpperCase();
        if (nextSymbol) {
            if (nextSymbol === querySymbol) {
                void refetchChain();
                void refetchGreeks();
                return;
            }
            setQuerySymbol(nextSymbol);
        }
    };

    const fmtPrice = (value: number | undefined, digits = 4) => (
        typeof value === 'number' && Number.isFinite(value) ? value.toFixed(digits) : '-'
    );

    const fmtPercent = (value: number | undefined) => (
        typeof value === 'number' && Number.isFinite(value) ? `${value.toFixed(2)}%` : '-'
    );

    return (
        <PageContainer>
            <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4 mb-6">
                <div>
                    <h1 className="text-3xl font-bold tracking-tight flex items-center gap-2">
                        <span>📈</span>
                        期权全景分析 (Options)
                    </h1>
                    <p className="text-muted-foreground mt-1 text-sm text-text-muted">全面洞察期权链分布、隐含波动率偏倚与希腊字母</p>
                </div>

                <form onSubmit={handleSearch} className="flex gap-2 w-full md:w-auto">
                    <input
                        value={symbol}
                        onChange={(e) => setSymbol(e.target.value)}
                        placeholder="输入标的代码 (如 510300)"
                        className="w-full md:w-[250px] border border-glass-border bg-surface px-3 py-2 rounded-md"
                    />
                    <button type="submit" className="bg-primary text-white px-4 py-2 rounded-md">
                        查询
                    </button>
                </form>
            </div>

            {(chainError || greeksError) && (
                <ErrorState text="数据获取失败" hint={chainError || greeksError || '未知错误，此代码可能无期权标的'} />
            )}

            <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                <SectionCard className="col-span-1 md:col-span-3">
                    <h3 className="font-bold text-lg mb-4">T型报价牌 (T-Quote) - {querySymbol}</h3>
                    {chainData?.underlying ? (
                        <div className="mb-3 text-sm text-text-muted flex flex-wrap gap-x-4 gap-y-1">
                            <span>{chainData.underlying.name ?? chainData.underlying.code ?? querySymbol}</span>
                            <span>现价 {fmtPrice(chainData.underlying.price, 3)}</span>
                            <span>到期月 {(chainData.selectedExpiry ?? []).join(', ') || '-'}</span>
                            <span>{chainData.underlying.date ?? ''} {chainData.underlying.time ?? ''}</span>
                        </div>
                    ) : null}
                    <div>
                        {chainLoading ? (
                            <LoadingState text="加载期权链中..." />
                        ) : pairedRows.length > 0 ? (
                            <div className="border border-glass-border rounded-md overflow-x-auto">
                                <table className="w-full text-sm text-left">
                                    <thead className="bg-surface-alt">
                                        <tr>
                                            <th className="text-center py-2 border-b border-glass-border" colSpan={4}>认购 (Call)</th>
                                            <th className="text-center bg-muted/80 border-x border-b border-glass-border font-bold text-primary">行权价 (Strike)</th>
                                            <th className="text-center py-2 border-b border-glass-border" colSpan={4}>认沽 (Put)</th>
                                        </tr>
                                        <tr className="text-xs text-text-muted border-b border-glass-border">
                                            <th className="text-right py-2 px-2">最新</th>
                                            <th className="text-right py-2 px-2">涨跌幅</th>
                                            <th className="text-right py-2 px-2">持仓</th>
                                            <th className="text-right py-2 px-2">IV</th>

                                            <th className="border-x border-glass-border"></th>

                                            <th className="text-left py-2 px-2">最新</th>
                                            <th className="text-left py-2 px-2">涨跌幅</th>
                                            <th className="text-left py-2 px-2">持仓</th>
                                            <th className="text-left py-2 px-2">IV</th>
                                        </tr>
                                    </thead>
                                    <tbody>
                                        {pairedRows.map((row, i) => {
                                            const call = row.call ?? {};
                                            const put = row.put ?? {};
                                            const callLast = typeof call.last === 'number' ? call.last : call.lastPrice;
                                            const putLast = typeof put.last === 'number' ? put.last : put.lastPrice;
                                            const callIv = typeof call.iv === 'number' ? call.iv : call.impliedVolatility;
                                            const putIv = typeof put.iv === 'number' ? put.iv : put.impliedVolatility;

                                            return (
                                                <tr key={i} className="text-sm hover:bg-surface-alt border-b border-glass-border/50">
                                                    <td className="text-right py-2 px-2 text-red-500 font-mono">{fmtPrice(callLast)}</td>
                                                    <td className="text-right py-2 px-2 text-red-500">{fmtPercent(call.changePercent)}</td>
                                                    <td className="text-right py-2 px-2 text-text-muted">{call.openInterest ?? '-'}</td>
                                                    <td className="text-right py-2 px-2 font-mono text-blue-500/80">{typeof callIv === 'number' ? `${(callIv * 100).toFixed(2)}%` : '-'}</td>

                                                    <td className="text-center border-x border-glass-border font-bold bg-surface-alt py-2 px-2">{fmtPrice(row.strike, 3)}</td>

                                                    <td className="text-left py-2 px-2 text-green-500 font-mono">{fmtPrice(putLast)}</td>
                                                    <td className="text-left py-2 px-2 text-green-500">{fmtPercent(put.changePercent)}</td>
                                                    <td className="text-left py-2 px-2 text-text-muted">{put.openInterest ?? '-'}</td>
                                                    <td className="text-left py-2 px-2 font-mono text-blue-500/80">{typeof putIv === 'number' ? `${(putIv * 100).toFixed(2)}%` : '-'}</td>
                                                </tr>
                                            );
                                        })}
                                    </tbody>
                                </table>
                            </div>
                        ) : (
                            <EmptyState text="暂无期权链数据" />
                        )}
                    </div>
                </SectionCard>

                <SectionCard className="col-span-1 md:col-span-3">
                    <h3 className="font-bold text-lg mb-4">希腊字母与波动率 (Greeks & IV)</h3>
                    <div>
                        {greeksLoading ? (
                            <LoadingState text="计算 Greeks 中..." />
                        ) : greekEntries.length > 0 ? (
                            <div className="space-y-4">
                                <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                                    <div className="rounded-md border border-glass-border bg-surface-alt p-3 text-sm">
                                        <div className="text-text-muted mb-1">标的/类型</div>
                                        <div className="font-semibold">{greeksData?.code ?? querySymbol} / {(greeksData?.option_type ?? '-').toUpperCase()}</div>
                                    </div>
                                    <div className="rounded-md border border-glass-border bg-surface-alt p-3 text-sm">
                                        <div className="text-text-muted mb-1">标的价 / 行权价</div>
                                        <div className="font-semibold">{fmtPrice(greeksData?.spot, 3)} / {fmtPrice(greeksData?.strike, 3)}</div>
                                    </div>
                                    <div className="rounded-md border border-glass-border bg-surface-alt p-3 text-sm">
                                        <div className="text-text-muted mb-1">理论价格</div>
                                        <div className="font-semibold">{greeksData?.option_price ?? '-'}</div>
                                    </div>
                                </div>

                                <div className="grid grid-cols-1 md:grid-cols-5 gap-3">
                                    {greekEntries.map(([name, value]) => (
                                        <div key={name} className="rounded-md border border-glass-border bg-surface-alt p-3">
                                            <div className="text-xs uppercase tracking-wider text-text-muted mb-1">{name}</div>
                                            <div className="font-semibold">{value}</div>
                                        </div>
                                    ))}
                                </div>

                                <div className="rounded-md border border-glass-border bg-surface-alt p-4">
                                    <div className="text-sm font-semibold mb-2">Greeks 解读</div>
                                    <div className="space-y-1 text-sm text-text-muted">
                                        {interpretationEntries.map(([name, value]) => (
                                            <div key={name}><span className="font-medium text-text-primary">{name}:</span> {value}</div>
                                        ))}
                                    </div>
                                    <div className="mt-3 text-xs text-text-muted">
                                        波动率 {greeksData?.volatility ?? '-'} / 无风险利率 {greeksData?.risk_free_rate ?? '-'} / 到期时间 {greeksData?.time_to_maturity ?? '-'}
                                    </div>
                                </div>
                            </div>
                        ) : (
                            <EmptyState text="暂无 Greeks 数据" />
                        )}
                    </div>
                </SectionCard>
            </div>
        </PageContainer>
    );
}
