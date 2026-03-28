'use client';

import { useMemo, useState } from 'react';
import Link from 'next/link';
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

function asRecord(value: unknown): Record<string, unknown> {
    return value && typeof value === 'object' && !Array.isArray(value)
        ? value as Record<string, unknown>
        : {};
}

function unwrapToolData(value: unknown, depth = 0): Record<string, unknown> {
    if (depth > 4) return {};
    const record = asRecord(value);
    if (!record.data || typeof record.data !== 'object' || Array.isArray(record.data)) {
        return record;
    }

    const keys = Object.keys(record);
    const wrapperOnly = keys.every((key) => [
        'data',
        'success',
        'ok',
        'error',
        'message',
        'source',
        'cached',
        'timestamp',
        'backend_requested',
        'backend_used',
        'fallback_used',
        'fallback_reason',
        'latency_ms',
        'traceId',
    ].includes(key));

    if (!wrapperOnly) {
        return record;
    }

    return unwrapToolData(record.data, depth + 1);
}

function readNumber(value: unknown): number | undefined {
    if (value == null || value === '') return undefined;
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : undefined;
}

function normalizeOptionItem(value: unknown): OptionChainItem {
    const item = asRecord(value);
    return {
        type: typeof item.type === 'string' ? item.type.toLowerCase() : undefined,
        strike: readNumber(item.strike ?? item.strikePrice ?? item.exercise_price),
        last: readNumber(item.last ?? item.lastPrice ?? item.price ?? item.close),
        lastPrice: readNumber(item.lastPrice ?? item.last ?? item.price ?? item.close),
        changePercent: readNumber(item.changePercent ?? item.change_pct),
        openInterest: readNumber(item.openInterest ?? item.open_interest ?? item.oi),
        impliedVolatility: readNumber(item.impliedVolatility ?? item.implied_volatility ?? item.iv),
        iv: readNumber(item.iv ?? item.impliedVolatility ?? item.implied_volatility),
    };
}

function normalizeOptionChainData(raw: unknown): OptionChainData {
    const payload = unwrapToolData(raw);
    const underlying = asRecord(payload.underlying);
    const selectedExpiryRaw = payload.selectedExpiry ?? payload.expiryMonths;

    return {
        underlying: Object.keys(underlying).length > 0 ? {
            code: typeof underlying.code === 'string' ? underlying.code : undefined,
            name: typeof underlying.name === 'string' ? underlying.name : undefined,
            price: readNumber(underlying.price ?? underlying.last ?? underlying.lastPrice),
            time: typeof underlying.time === 'string' ? underlying.time : undefined,
            date: typeof underlying.date === 'string' ? underlying.date : undefined,
        } : undefined,
        selectedExpiry: Array.isArray(selectedExpiryRaw)
            ? selectedExpiryRaw.map((item) => String(item)).filter(Boolean)
            : typeof selectedExpiryRaw === 'string' && selectedExpiryRaw
                ? [selectedExpiryRaw]
                : [],
        options: Array.isArray(payload.options) ? payload.options.map((item) => normalizeOptionItem(item)) : [],
    };
}

function normalizeTextRecord(value: unknown): Record<string, string> | undefined {
    const record = asRecord(value);
    const entries = Object.entries(record)
        .map(([key, item]) => [key, String(item ?? '').trim()] as const)
        .filter(([, item]) => item);
    return entries.length > 0 ? Object.fromEntries(entries) : undefined;
}

function normalizeGreeksData(raw: unknown): GreeksData {
    const payload = unwrapToolData(raw);
    return {
        code: typeof payload.code === 'string' ? payload.code : undefined,
        option_type: typeof payload.option_type === 'string' ? payload.option_type : undefined,
        spot: readNumber(payload.spot),
        strike: readNumber(payload.strike),
        option_price: payload.option_price != null ? String(payload.option_price) : undefined,
        volatility: payload.volatility != null ? String(payload.volatility) : undefined,
        risk_free_rate: payload.risk_free_rate != null ? String(payload.risk_free_rate) : undefined,
        time_to_maturity: payload.time_to_maturity != null ? String(payload.time_to_maturity) : undefined,
        greeks: normalizeTextRecord(payload.greeks),
        interpretation: normalizeTextRecord(payload.interpretation),
    };
}

export default function OptionsPage() {
    const [symbol, setSymbol] = useState('510300'); // Default to 300 ETF
    const [querySymbol, setQuerySymbol] = useState('510300');
    const exampleSymbols = ['510050', '510300'];

    const { data: chainData, isPending: chainLoading, error: chainError, refetch: refetchChain } = useApiQuery<OptionChainData>(
        `/v1/options/chain/${querySymbol}`,
        { staleTime: 60 * 1000, parse: normalizeOptionChainData },
    );

    const { data: greeksData, isPending: greeksLoading, error: greeksError, refetch: refetchGreeks } = useApiQuery<GreeksData>(
        `/v1/options/greeks/${querySymbol}`,
        { staleTime: 60 * 1000, parse: normalizeGreeksData },
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
    const showChainLoading = (chainLoading || greeksLoading) && pairedRows.length === 0 && !chainError;
    const showGreeksLoading = (greeksLoading || chainLoading) && greekEntries.length === 0 && !greeksError;
    const showChainEmpty = !chainLoading && !greeksLoading && pairedRows.length === 0 && !chainError;
    const showGreeksEmpty = !greeksLoading && !chainLoading && greekEntries.length === 0 && !greeksError;

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

                <form onSubmit={handleSearch} className="grid gap-2 w-full md:w-auto">
                    <label htmlFor="options-symbol" className="grid gap-1 text-xs text-text-secondary">
                        <span>期权标的代码</span>
                        <div className="flex gap-2 w-full md:w-auto flex-wrap">
                            <input
                                id="options-symbol"
                                value={symbol}
                                onChange={(e) => setSymbol(e.target.value)}
                                placeholder="输入标的代码 (如 510300)"
                                className="w-full md:w-[250px] border border-glass-border bg-surface px-3 py-2 rounded-md"
                            />
                            <button type="submit" className="bg-primary text-white px-4 py-2 rounded-md">
                                查询
                            </button>
                        </div>
                    </label>
                    <div className="flex gap-2 flex-wrap">
                        {exampleSymbols.map((item) => (
                            <button
                                key={item}
                                type="button"
                                onClick={() => {
                                    setSymbol(item);
                                    setQuerySymbol(item);
                                }}
                                className="px-3 py-1 rounded-full border border-border text-xs cursor-pointer hover:bg-surface-alt"
                            >
                                示例 {item}
                            </button>
                        ))}
                    </div>
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
                        {showChainLoading ? (
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
                        ) : showChainEmpty ? (
                            <EmptyState
                                text="当前标的暂无期权链数据"
                                hint="先切换到 50ETF 或 300ETF 这类覆盖度更高的示例标的，能更快确认页面、数据源和期权链结构是否正常。"
                                action={
                                    <>
                                        {exampleSymbols.map((item) => (
                                            <button
                                                key={`chain-${item}`}
                                                type="button"
                                                onClick={() => {
                                                    setSymbol(item);
                                                    setQuerySymbol(item);
                                                }}
                                                className="px-3 py-1.5 rounded border border-border text-sm cursor-pointer hover:bg-surface-alt"
                                            >
                                                切换到 {item}
                                            </button>
                                        ))}
                                        <button type="button" onClick={() => void refetchChain()} className="px-3 py-1.5 rounded border border-primary text-primary text-sm cursor-pointer hover:bg-primary/5">
                                            重新加载
                                        </button>
                                        <Link href="/research" className="px-3 py-1.5 rounded border border-border text-sm no-underline text-inherit hover:bg-surface-alt">
                                            去研究页看标的背景
                                        </Link>
                                    </>
                                }
                            />
                        ) : null}
                    </div>
                </SectionCard>

                <SectionCard className="col-span-1 md:col-span-3">
                    <h3 className="font-bold text-lg mb-4">希腊字母与波动率 (Greeks & IV)</h3>
                    <div>
                        {showGreeksLoading ? (
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
                        ) : showGreeksEmpty ? (
                            <EmptyState
                                text="当前暂无 Greeks 数据"
                                hint="当前会等同批期权链一起返回后再判断是否真的为空，避免你在加载过程中误以为没有结果。若持续为空，通常意味着当前标的或参数覆盖不足。"
                                action={
                                    <>
                                        <button
                                            type="button"
                                            onClick={() => {
                                                setSymbol('510300');
                                                setQuerySymbol('510300');
                                            }}
                                            className="px-3 py-1.5 rounded border border-primary text-primary text-sm cursor-pointer hover:bg-primary/5"
                                        >
                                            用 510300 重试
                                        </button>
                                        <button type="button" onClick={() => void refetchGreeks()} className="px-3 py-1.5 rounded border border-border text-sm cursor-pointer hover:bg-surface-alt">
                                            重新计算
                                        </button>
                                        <Link href="/market" className="px-3 py-1.5 rounded border border-border text-sm no-underline text-inherit hover:bg-surface-alt">
                                            回行情页确认标的
                                        </Link>
                                    </>
                                }
                            />
                        ) : null}
                    </div>
                </SectionCard>
            </div>
        </PageContainer>
    );
}
