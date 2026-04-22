'use client';

import { useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import ResultWorkbench from '@/components/result-workbench';
import { PageContainer, SectionCard } from '@/components/ui';
import { EmptyState, ErrorState, LoadingState } from '@/components/status-state';
import { useApiQuery } from '@/hooks/use-api-query';
import { usePageActions } from '@/hooks/use-page-actions';
import { usePageContext } from '@/hooks/use-page-context';
import { buildLocalResultContract, defaultWorkbenchTask, evidenceToSummary } from '@/lib/result-workbench';

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

type SmirkPoint = {
    strike?: number;
    moneyness?: number;
    call_iv?: number;
    put_iv?: number;
    avg_iv?: number;
    skew?: number;
};

type SmirkData = {
    underlying?: {
        code?: string;
        name?: string;
        price?: number;
    };
    selected_expiry?: string[];
    curve?: SmirkPoint[];
    spot?: number;
    time_to_maturity?: number;
    atm_iv?: number;
    point_count?: number;
    degraded?: boolean;
    message?: string;
};

type PairedOptionRow = {
    strike: number;
    call?: OptionChainItem;
    put?: OptionChainItem;
};

type GreekSelection = {
    type: 'call' | 'put';
    strike: number;
    last?: number;
    iv?: number;
};

function asRecord(value: unknown): Record<string, unknown> {
    return value && typeof value === 'object' && !Array.isArray(value)
        ? value as Record<string, unknown>
        : {};
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
    const payload = asRecord(raw);
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
    const payload = asRecord(raw);
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

function normalizeSmirkPoint(raw: unknown): SmirkPoint {
    const payload = asRecord(raw);
    return {
        strike: readNumber(payload.strike),
        moneyness: readNumber(payload.moneyness),
        call_iv: readNumber(payload.call_iv),
        put_iv: readNumber(payload.put_iv),
        avg_iv: readNumber(payload.avg_iv),
        skew: readNumber(payload.skew),
    };
}

function normalizeSmirkData(raw: unknown): SmirkData {
    const payload = asRecord(raw);
    const underlying = asRecord(payload.underlying);
    const selectedExpiryRaw = payload.selected_expiry ?? payload.selectedExpiry;
    return {
        underlying: Object.keys(underlying).length > 0 ? {
            code: typeof underlying.code === 'string' ? underlying.code : undefined,
            name: typeof underlying.name === 'string' ? underlying.name : undefined,
            price: readNumber(underlying.price),
        } : undefined,
        selected_expiry: Array.isArray(selectedExpiryRaw)
            ? selectedExpiryRaw.map((item) => String(item)).filter(Boolean)
            : typeof selectedExpiryRaw === 'string' && selectedExpiryRaw
                ? [selectedExpiryRaw]
                : [],
        curve: Array.isArray(payload.curve) ? payload.curve.map((item) => normalizeSmirkPoint(item)) : [],
        spot: readNumber(payload.spot),
        time_to_maturity: readNumber(payload.time_to_maturity),
        atm_iv: readNumber(payload.atm_iv),
        point_count: readNumber(payload.point_count),
        degraded: payload.degraded === true,
        message: typeof payload.message === 'string' ? payload.message : undefined,
    };
}

function buildGreekSelection(type: 'call' | 'put', row: PairedOptionRow): GreekSelection | null {
    const option = type === 'call' ? row.call : row.put;
    if (!option) {
        return null;
    }
    const last = typeof option.last === 'number' ? option.last : option.lastPrice;
    const iv = typeof option.iv === 'number' ? option.iv : option.impliedVolatility;
    return {
        type,
        strike: row.strike,
        ...(typeof last === 'number' ? { last } : {}),
        ...(typeof iv === 'number' ? { iv } : {}),
    };
}

function resolveDefaultGreekSelection(rows: PairedOptionRow[], underlyingPrice?: number): GreekSelection | null {
    if (rows.length === 0) {
        return null;
    }
    const ordered = [...rows].sort((left, right) => {
        if (typeof underlyingPrice !== 'number') return left.strike - right.strike;
        return Math.abs(left.strike - underlyingPrice) - Math.abs(right.strike - underlyingPrice);
    });
    for (const row of ordered) {
        const callSelection = buildGreekSelection('call', row);
        if (callSelection) return callSelection;
        const putSelection = buildGreekSelection('put', row);
        if (putSelection) return putSelection;
    }
    return null;
}

export default function OptionsPage() {
    const [symbol, setSymbol] = useState('510300'); // Default to 300 ETF
    const [querySymbol, setQuerySymbol] = useState('510300');
    const [selectedGreekLeg, setSelectedGreekLeg] = useState<GreekSelection | null>(null);
    const exampleSymbols = ['510050', '510300'];

    const { data: chainData, isPending: chainLoading, error: chainError, refetch: refetchChain } = useApiQuery<OptionChainData>(
        `/v1/options/chain/${querySymbol}`,
        { staleTime: 60 * 1000, parse: normalizeOptionChainData },
    );

    const greekQueryString = useMemo(() => {
        if (!selectedGreekLeg) {
            return '';
        }
        const params = new URLSearchParams();
        params.set('optionType', selectedGreekLeg.type);
        params.set('strike', String(selectedGreekLeg.strike));
        if (typeof chainData?.underlying?.price === 'number') {
            params.set('spot', String(chainData.underlying.price));
        }
        if (typeof selectedGreekLeg.iv === 'number' && Number.isFinite(selectedGreekLeg.iv) && selectedGreekLeg.iv > 0) {
            params.set('volatility', String(selectedGreekLeg.iv));
        }
        return params.toString();
    }, [chainData?.underlying?.price, selectedGreekLeg]);

    const { data: greeksData, isPending: greeksLoading, error: greeksError, refetch: refetchGreeks } = useApiQuery<GreeksData>(
        `/v1/options/greeks/${querySymbol}${greekQueryString ? `?${greekQueryString}` : ''}`,
        { staleTime: 60 * 1000, parse: normalizeGreeksData },
    );

    const { data: smirkData, isPending: smirkLoading, error: smirkError, refetch: refetchSmirk } = useApiQuery<SmirkData>(
        `/v1/options/smirk/${querySymbol}`,
        { staleTime: 60 * 1000, parse: normalizeSmirkData },
    );

    const pairedRows = useMemo<PairedOptionRow[]>(() => {
        const items = Array.isArray(chainData?.options) ? chainData.options : [];
        const map = new Map<number, PairedOptionRow>();

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

    useEffect(() => {
        setSelectedGreekLeg(null);
    }, [querySymbol]);

    useEffect(() => {
        if (pairedRows.length === 0) {
            setSelectedGreekLeg(null);
            return;
        }

        setSelectedGreekLeg((current) => {
            const fallback = resolveDefaultGreekSelection(pairedRows, chainData?.underlying?.price);
            if (!fallback) {
                return null;
            }
            if (!current) {
                return fallback;
            }
            const selectedRow = pairedRows.find((row) => row.strike === current.strike);
            if (!selectedRow) {
                return fallback;
            }
            const nextSelection = buildGreekSelection(current.type, selectedRow);
            return nextSelection ?? fallback;
        });
    }, [chainData?.underlying?.price, pairedRows]);

    const greekEntries = useMemo(() => {
        if (!greeksData?.greeks || typeof greeksData.greeks !== 'object') return [];
        return Object.entries(greeksData.greeks);
    }, [greeksData]);

    const interpretationEntries = useMemo(() => {
        if (!greeksData?.interpretation || typeof greeksData.interpretation !== 'object') return [];
        return Object.entries(greeksData.interpretation);
    }, [greeksData]);
    const smirkRows = useMemo(() => Array.isArray(smirkData?.curve) ? smirkData.curve : [], [smirkData]);
    const selectedSmirkPoint = useMemo(() => {
        if (!selectedGreekLeg) return null;
        return smirkRows.find((row) => typeof row.strike === 'number' && row.strike === selectedGreekLeg.strike) ?? null;
    }, [selectedGreekLeg, smirkRows]);
    const showChainLoading = (chainLoading || greeksLoading) && pairedRows.length === 0 && !chainError;
    const showGreeksLoading = (greeksLoading || chainLoading) && greekEntries.length === 0 && !greeksError;
    const showChainEmpty = !chainLoading && !greeksLoading && pairedRows.length === 0 && !chainError;
    const showGreeksEmpty = !greeksLoading && !chainLoading && greekEntries.length === 0 && !greeksError;
    const showSmirkLoading = smirkLoading && smirkRows.length === 0 && !smirkError;
    const showSmirkEmpty = !smirkLoading && smirkRows.length === 0 && !smirkError;

    const handleSearch = (e: React.FormEvent) => {
        e.preventDefault();
        const nextSymbol = symbol.trim().toUpperCase();
        if (nextSymbol) {
            if (nextSymbol === querySymbol) {
                void refetchChain();
                void refetchGreeks();
                void refetchSmirk();
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
    const optionsSummary = pairedRows.length > 0
        ? `${querySymbol} 当前已加载 ${pairedRows.length} 个行权价层级，Greeks ${greekEntries.length} 项，Smirk 点位 ${smirkRows.length} 个。`
        : `${querySymbol} 当前暂无完整期权链，建议先切到 510050 或 510300，确认是不是单标的覆盖不足。`;
    const optionsActions = useMemo(
        () => [
            {
                id: 'options.refresh-current',
                label: `刷新 ${querySymbol}`,
                description: '重新拉取当前标的的期权链、Greeks 和波动率偏斜',
                keywords: ['期权', '刷新', querySymbol],
                scope: 'page' as const,
                pageKey: 'options',
                run: async () => {
                    await Promise.all([refetchChain(), refetchGreeks(), refetchSmirk()]);
                    return { message: `已刷新 ${querySymbol} 的期权数据` };
                },
            },
            {
                id: 'options.use-510300',
                label: '切到 510300',
                description: '使用覆盖更稳定的 300ETF 期权样例',
                keywords: ['510300', 'ETF'],
                scope: 'page' as const,
                pageKey: 'options',
                run: () => {
                    setSymbol('510300');
                    setQuerySymbol('510300');
                    return { message: '已切到 510300' };
                },
            },
            {
                id: 'options.use-510050',
                label: '切到 510050',
                description: '使用上证 50ETF 期权样例',
                keywords: ['510050', 'ETF'],
                scope: 'page' as const,
                pageKey: 'options',
                run: () => {
                    setSymbol('510050');
                    setQuerySymbol('510050');
                    return { message: '已切到 510050' };
                },
            },
        ],
        [querySymbol, refetchChain, refetchGreeks, refetchSmirk],
    );
    usePageActions(optionsActions);
    const optionsResult = buildLocalResultContract({
        summary: optionsSummary,
        availableViews: pairedRows.length > 1 || smirkRows.length > 0 ? ['compare', 'visual'] : [],
        pageActions: optionsActions,
        preferredActionIds: ['options.refresh-current', 'options.use-510300', 'options.use-510050'],
        recommendedLinks: [
            { id: 'options-link-market', label: '去行情页确认标的', href: `/market?code=${encodeURIComponent(querySymbol)}` },
            { id: 'options-link-research', label: '去研究页补背景', href: `/research?code=${encodeURIComponent(querySymbol)}` },
            { id: 'options-link-risk', label: '去风险页', href: `/risk?code=${encodeURIComponent(querySymbol)}` },
        ],
        evidence: [
            { label: '标的代码', value: querySymbol },
            { label: '期权链层级', value: String(pairedRows.length) },
            { label: 'Greeks 项数', value: String(greekEntries.length) },
            { label: 'Smirk 点位', value: String(smirkRows.length) },
            { label: '标的现价', value: fmtPrice(chainData?.underlying?.price, 3) },
            { label: '选中腿', value: selectedGreekLeg ? `${selectedGreekLeg.type}/${fmtPrice(selectedGreekLeg.strike, 3)}` : '-' },
        ],
        riskNotes: [
            ...(chainError ? [chainError] : []),
            ...(greeksError ? [greeksError] : []),
            ...(smirkError ? [smirkError] : []),
            ...(smirkData?.degraded ? ['隐含波动率偏斜结果来自降级链路，需谨慎解读。'] : []),
            ...(pairedRows.length === 0 ? ['当前没有完整的期权链结果。'] : []),
        ],
        freshness: chainData?.underlying?.date || chainData?.underlying?.time
            ? { asOf: `${chainData.underlying.date ?? ''} ${chainData.underlying.time ?? ''}`.trim(), label: '期权快照' }
            : null,
        platformMeta: {
            sourceTool: 'options',
            sourceChain: ['options-chain', 'options-greeks', 'options-smirk'],
            degraded: Boolean(smirkData?.degraded || chainError || greeksError || smirkError),
            fallbackReason: [smirkData?.message, chainError, greeksError, smirkError].filter((item): item is string => Boolean(item)),
        },
        workbenchTask: defaultWorkbenchTask('options', `复查期权 ${querySymbol}`, '/options', 'options-review', {
            symbol: querySymbol,
            chainLevels: pairedRows.length,
            smirkPoints: smirkRows.length,
        }),
    });
    usePageContext({
        pageKey: 'options',
        title: '期权全景分析',
        summary: optionsSummary,
        objectType: 'derivative',
        objectId: querySymbol,
        resultType: 'options-analysis',
        tags: [
            querySymbol,
            pairedRows.length > 0 ? `${pairedRows.length} 个行权价层级` : '期权链待确认',
            selectedGreekLeg ? `${selectedGreekLeg.type === 'call' ? '认购' : '认沽'}腿` : '等待选腿',
        ],
        suggestions: [
            '总结当前期权链结构和最值得继续看的价位',
            '解释当前 Greeks 和隐含波动率偏斜意味着什么',
            '判断下一步应该回行情页、研究页还是风险页',
        ],
        recommendedActions: optionsResult.recommendedActions ?? [],
        recommendedLinks: optionsResult.recommendedLinks ?? [],
        evidenceSummary: evidenceToSummary(optionsResult.evidence),
        riskNotes: optionsResult.riskNotes ?? [],
        freshness: optionsResult.freshness ?? null,
        raw: {
            symbol: querySymbol,
            pairedRows: pairedRows.length,
            greekCount: greekEntries.length,
            smirkPoints: smirkRows.length,
            selectedGreekLeg,
        },
    });

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

            <ResultWorkbench pageKey="options" title="期权结果工作台" result={optionsResult} />

            {(chainError || greeksError || smirkError) && (
                <ErrorState text="数据获取失败" hint={chainError || greeksError || smirkError || '未知错误，此代码可能无期权标的'} />
            )}

            <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                <SectionCard className="col-span-1 md:col-span-3">
                    <h3 className="font-bold text-lg mb-4">T型报价牌 (T-Quote) - {querySymbol}</h3>
                    <div className="mb-3 text-xs text-text-muted">
                        点击认购或认沽“最新”报价，可将下方 Greeks 计算切换到对应期权腿。
                    </div>
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
                                            const callSelected = selectedGreekLeg?.type === 'call' && selectedGreekLeg?.strike === row.strike;
                                            const putSelected = selectedGreekLeg?.type === 'put' && selectedGreekLeg?.strike === row.strike;
                                            const rowSelected = selectedGreekLeg?.strike === row.strike;

                                            return (
                                                <tr key={i} className={`text-sm border-b border-glass-border/50 ${rowSelected ? 'bg-primary/5' : 'hover:bg-surface-alt'}`}>
                                                    <td className="text-right py-2 px-2 text-red-500 font-mono">
                                                        {typeof callLast === 'number' ? (
                                                            <button
                                                                type="button"
                                                                onClick={() => setSelectedGreekLeg(buildGreekSelection('call', row))}
                                                                className={`w-full rounded px-2 py-1 text-right font-mono text-inherit ${callSelected ? 'bg-primary/10 ring-1 ring-primary/35' : 'hover:bg-primary/5'}`}
                                                            >
                                                                {fmtPrice(callLast)}
                                                            </button>
                                                        ) : '-'}
                                                    </td>
                                                    <td className="text-right py-2 px-2 text-red-500">{fmtPercent(call.changePercent)}</td>
                                                    <td className="text-right py-2 px-2 text-text-muted">{call.openInterest ?? '-'}</td>
                                                    <td className="text-right py-2 px-2 font-mono text-blue-500/80">{typeof callIv === 'number' ? `${(callIv * 100).toFixed(2)}%` : '-'}</td>

                                                    <td className={`text-center border-x border-glass-border font-bold py-2 px-2 ${rowSelected ? 'bg-primary/10 text-primary' : 'bg-surface-alt'}`}>{fmtPrice(row.strike, 3)}</td>

                                                    <td className="text-left py-2 px-2 text-green-500 font-mono">
                                                        {typeof putLast === 'number' ? (
                                                            <button
                                                                type="button"
                                                                onClick={() => setSelectedGreekLeg(buildGreekSelection('put', row))}
                                                                className={`w-full rounded px-2 py-1 text-left font-mono text-inherit ${putSelected ? 'bg-primary/10 ring-1 ring-primary/35' : 'hover:bg-primary/5'}`}
                                                            >
                                                                {fmtPrice(putLast)}
                                                            </button>
                                                        ) : '-'}
                                                    </td>
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
                        <div className="mb-4 grid grid-cols-1 md:grid-cols-4 gap-3">
                            <div className="rounded-md border border-glass-border bg-surface-alt p-3 text-sm">
                                <div className="text-text-muted mb-1">当前选中腿</div>
                                <div className="font-semibold">
                                    {selectedGreekLeg ? `${selectedGreekLeg.type === 'call' ? '认购' : '认沽'} / ${fmtPrice(selectedGreekLeg.strike, 3)}` : '等待选择'}
                                </div>
                            </div>
                            <div className="rounded-md border border-glass-border bg-surface-alt p-3 text-sm">
                                <div className="text-text-muted mb-1">市场最新价</div>
                                <div className="font-semibold">{fmtPrice(selectedGreekLeg?.last, 4)}</div>
                            </div>
                            <div className="rounded-md border border-glass-border bg-surface-alt p-3 text-sm">
                                <div className="text-text-muted mb-1">使用 IV</div>
                                <div className="font-semibold">
                                    {typeof selectedGreekLeg?.iv === 'number' ? `${(selectedGreekLeg.iv * 100).toFixed(2)}%` : '-'}
                                </div>
                            </div>
                            <div className="rounded-md border border-glass-border bg-surface-alt p-3 text-sm">
                                <div className="text-text-muted mb-1">标的现价</div>
                                <div className="font-semibold">{fmtPrice(chainData?.underlying?.price, 3)}</div>
                            </div>
                        </div>

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

                <SectionCard className="col-span-1 md:col-span-3">
                    <h3 className="font-bold text-lg mb-4">隐含波动率偏斜 (Smirk)</h3>
                    <div>
                        {showSmirkLoading ? (
                            <LoadingState text="加载隐含波动率曲线中..." />
                        ) : smirkRows.length > 0 ? (
                            <div className="space-y-4">
                                <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
                                    <div className="rounded-md border border-glass-border bg-surface-alt p-3 text-sm">
                                        <div className="text-text-muted mb-1">ATM IV</div>
                                        <div className="font-semibold">
                                            {typeof smirkData?.atm_iv === 'number' ? `${(smirkData.atm_iv * 100).toFixed(2)}%` : '-'}
                                        </div>
                                    </div>
                                    <div className="rounded-md border border-glass-border bg-surface-alt p-3 text-sm">
                                        <div className="text-text-muted mb-1">曲线点数</div>
                                        <div className="font-semibold">{smirkData?.point_count ?? smirkRows.length}</div>
                                    </div>
                                    <div className="rounded-md border border-glass-border bg-surface-alt p-3 text-sm">
                                        <div className="text-text-muted mb-1">到期月</div>
                                        <div className="font-semibold">{smirkData?.selected_expiry?.join(', ') || '-'}</div>
                                    </div>
                                    <div className="rounded-md border border-glass-border bg-surface-alt p-3 text-sm">
                                        <div className="text-text-muted mb-1">状态</div>
                                        <div className="font-semibold">{smirkData?.degraded ? '降级结果' : '正常结果'}</div>
                                    </div>
                                </div>

                                <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                                    <div className="rounded-md border border-glass-border bg-surface-alt p-3 text-sm">
                                        <div className="text-text-muted mb-1">当前选中 Strike</div>
                                        <div className="font-semibold">{selectedSmirkPoint ? fmtPrice(selectedSmirkPoint.strike, 3) : '等待选择'}</div>
                                    </div>
                                    <div className="rounded-md border border-glass-border bg-surface-alt p-3 text-sm">
                                        <div className="text-text-muted mb-1">对应均值 IV</div>
                                        <div className="font-semibold">
                                            {typeof selectedSmirkPoint?.avg_iv === 'number' ? `${(selectedSmirkPoint.avg_iv * 100).toFixed(2)}%` : '-'}
                                        </div>
                                    </div>
                                    <div className="rounded-md border border-glass-border bg-surface-alt p-3 text-sm">
                                        <div className="text-text-muted mb-1">对应 Skew</div>
                                        <div className="font-semibold">
                                            {typeof selectedSmirkPoint?.skew === 'number' ? selectedSmirkPoint.skew.toFixed(4) : '-'}
                                        </div>
                                    </div>
                                </div>

                                {smirkData?.message ? (
                                    <div className="rounded-md border border-warning/30 bg-warning/10 px-3 py-2 text-xs text-text-secondary">
                                        {smirkData.message}
                                    </div>
                                ) : null}

                                <div className="border border-glass-border rounded-md overflow-x-auto">
                                    <table className="w-full text-sm text-left">
                                        <thead className="bg-surface-alt text-xs text-text-muted">
                                            <tr>
                                                <th className="py-2 px-3">行权价</th>
                                                <th className="py-2 px-3">Moneyness</th>
                                                <th className="py-2 px-3">Call IV</th>
                                                <th className="py-2 px-3">Put IV</th>
                                                <th className="py-2 px-3">均值 IV</th>
                                                <th className="py-2 px-3">Skew</th>
                                            </tr>
                                        </thead>
                                        <tbody>
                                            {smirkRows.map((row, index) => {
                                                const selected = selectedSmirkPoint?.strike === row.strike;
                                                return (
                                                <tr key={`${row.strike ?? index}-${index}`} className={`border-b border-glass-border/50 ${selected ? 'bg-primary/5' : 'hover:bg-surface-alt'}`}>
                                                    <td className="py-2 px-3 font-mono">{fmtPrice(row.strike, 3)}</td>
                                                    <td className="py-2 px-3">{typeof row.moneyness === 'number' ? row.moneyness.toFixed(3) : '-'}</td>
                                                    <td className="py-2 px-3">{typeof row.call_iv === 'number' ? `${(row.call_iv * 100).toFixed(2)}%` : '-'}</td>
                                                    <td className="py-2 px-3">{typeof row.put_iv === 'number' ? `${(row.put_iv * 100).toFixed(2)}%` : '-'}</td>
                                                    <td className="py-2 px-3">{typeof row.avg_iv === 'number' ? `${(row.avg_iv * 100).toFixed(2)}%` : '-'}</td>
                                                    <td className={`py-2 px-3 ${typeof row.skew === 'number' && row.skew > 0 ? 'text-warning' : 'text-text-primary'}`}>
                                                        {typeof row.skew === 'number' ? row.skew.toFixed(4) : '-'}
                                                    </td>
                                                </tr>
                                            )})}
                                        </tbody>
                                    </table>
                                </div>
                            </div>
                        ) : showSmirkEmpty ? (
                            <EmptyState
                                text="当前暂无隐含波动率偏斜数据"
                                hint="如果期权链返回正常但 smirk 为空，通常是当前月份样本不足或部分合约价格无法反推出稳定 IV。"
                                action={
                                    <>
                                        <button type="button" onClick={() => void refetchSmirk()} className="px-3 py-1.5 rounded border border-primary text-primary text-sm cursor-pointer hover:bg-primary/5">
                                            重新加载
                                        </button>
                                        <button
                                            type="button"
                                            onClick={() => {
                                                setSymbol('510050');
                                                setQuerySymbol('510050');
                                            }}
                                            className="px-3 py-1.5 rounded border border-border text-sm cursor-pointer hover:bg-surface-alt"
                                        >
                                            用 510050 重试
                                        </button>
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
