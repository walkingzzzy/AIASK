'use client';

import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { PageContainer, SectionCard, StockCodeInput } from '@/components/ui';
import { ErrorState, LoadingState } from '@/components/status-state';
import { BFF_BASE } from '@/lib/api';

// Ensure generic typing aligns with other modules
type OptionGreek = {
    delta: number;
    gamma: number;
    theta: number;
    vega: number;
    rho: number;
    implied_volatility: number;
};

type OptionContract = {
    symbol: string;
    strike: number;
    lastPrice: number;
    bid: number;
    ask: number;
    volume: number;
    openInterest: number;
    impliedVolatility?: number;
};

type OptionData = {
    calls: OptionContract[];
    puts: OptionContract[];
    expirationDate: string;
};

export default function OptionsPage() {
    const [symbol, setSymbol] = useState('510300'); // Default to 300 ETF
    const [querySymbol, setQuerySymbol] = useState('510300');

    const { data: chainData, isLoading: chainLoading, error: chainError } = useQuery({
        queryKey: ['options:chain', querySymbol],
        queryFn: async () => {
            const res = await fetch(`${BFF_BASE}/v1/options/chain/${querySymbol}`, { credentials: 'include' });
            if (!res.ok) throw new Error('期权链获取失败');
            const payload = await res.json();
            return payload.data?.data || payload.data || [];
        },
        staleTime: 60 * 1000,
    });

    const { data: greeksData, isLoading: greeksLoading, error: greeksError } = useQuery({
        queryKey: ['options:greeks', querySymbol],
        queryFn: async () => {
            const res = await fetch(`${BFF_BASE}/v1/options/greeks/${querySymbol}`, { credentials: 'include' });
            if (!res.ok) throw new Error('期权Greeks获取失败');
            const payload = await res.json();
            return payload.data?.data || payload.data || {};
        },
        staleTime: 60 * 1000,
    });

    const handleSearch = (e: React.FormEvent) => {
        e.preventDefault();
        if (symbol.trim()) {
            setQuerySymbol(symbol.trim().toUpperCase());
        }
    };

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
                <ErrorState text="数据获取失败" hint={chainError?.message || greeksError?.message || '未知错误，此代码可能无期权标的'} />
            )}

            <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                <SectionCard className="col-span-1 md:col-span-3">
                    <h3 className="font-bold text-lg mb-4">T型报价牌 (T-Quote) - {querySymbol}</h3>
                    <div>
                        {chainLoading ? (
                            <LoadingState text="加载期权链中..." />
                        ) : chainData && Array.isArray(chainData) && chainData.length > 0 ? (
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
                                        {chainData.slice(0, 20).map((row: any, i: number) => {
                                            const call = row.call || {};
                                            const put = row.put || {};
                                            const strike = row.strike || row.strike_price || '-';

                                            return (
                                                <tr key={i} className="text-sm hover:bg-surface-alt border-b border-glass-border/50">
                                                    <td className="text-right py-2 px-2 text-red-500 font-mono">{call.last || '-'}</td>
                                                    <td className="text-right py-2 px-2 text-red-500">{call.pct_change ? `${call.pct_change}%` : '-'}</td>
                                                    <td className="text-right py-2 px-2 text-text-muted">{call.oi || '-'}</td>
                                                    <td className="text-right py-2 px-2 font-mono text-blue-500/80">{call.iv ? `${(call.iv * 100).toFixed(2)}%` : '-'}</td>

                                                    <td className="text-center border-x border-glass-border font-bold bg-surface-alt py-2 px-2">{strike}</td>

                                                    <td className="text-left py-2 px-2 text-green-500 font-mono">{put.last || '-'}</td>
                                                    <td className="text-left py-2 px-2 text-green-500">{put.pct_change ? `${put.pct_change}%` : '-'}</td>
                                                    <td className="text-left py-2 px-2 text-text-muted">{put.oi || '-'}</td>
                                                    <td className="text-left py-2 px-2 font-mono text-blue-500/80">{put.iv ? `${(put.iv * 100).toFixed(2)}%` : '-'}</td>
                                                </tr>
                                            );
                                        })}
                                    </tbody>
                                </table>
                            </div>
                        ) : (
                            <div className="h-32 flex items-center justify-center text-text-muted">
                                暂无期权链数据
                            </div>
                        )}
                    </div>
                </SectionCard>

                <SectionCard className="col-span-1 md:col-span-3">
                    <h3 className="font-bold text-lg mb-4">希腊字母与波动率 (Greeks & IV)</h3>
                    <div>
                        {greeksLoading ? (
                            <LoadingState text="计算 Greeks 中..." />
                        ) : (
                            <div className="h-64 flex items-center justify-center border border-glass-border rounded-md bg-surface-alt">
                                <p className="text-sm text-text-muted">图表渲染区：隐含波动率微笑曲线 (Volatility Smile) 与 Greeks 曲面</p>
                            </div>
                        )}
                    </div>
                </SectionCard>
            </div>
        </PageContainer>
    );
}
