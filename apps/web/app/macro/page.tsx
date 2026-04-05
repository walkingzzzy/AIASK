'use client';

import { useMemo, useState } from 'react';
import Link from 'next/link';
import { PageContainer, SectionCard, DataTable, Badge, KpiCard, KpiGrid } from '@/components/ui';
import { EmptyState, ErrorState, LoadingState } from '@/components/status-state';
import { LineChart } from '@/components/charts';
import { useApiQuery } from '@/hooks/use-api-query';
import { extractObject } from '@/lib/data-utils';

type MacroRecord = {
    date?: string;
    period?: string;
    quarter?: string;
    value?: number;
    yoy?: number;
    yoyChange?: number;
    momChange?: number;
};

type MacroResponse = {
    indicator?: string;
    records?: MacroRecord[];
};

function isRecord(value: unknown): value is Record<string, unknown> {
    return !!value && typeof value === 'object' && !Array.isArray(value);
}

export default function MacroPage() {
    const [indicator, setIndicator] = useState('gdp');

    const indicators = [
        { value: 'gdp', label: '国内生产总值 (GDP)' },
        { value: 'cpi', label: '居民消费价格指数 (CPI)' },
        { value: 'pmi', label: '采购经理人指数 (PMI)' },
        { value: 'ppi', label: '工业生产者出厂价格指数 (PPI)' },
        { value: 'm2', label: '货币供应量 (M2)' }
    ];

    const { data: macroData, isPending: isLoading, error, refetch } = useApiQuery<MacroResponse | MacroRecord[]>(
        `/v1/macro/indicator/${indicator}`,
        { staleTime: 5 * 60 * 1000 },
    );

    const macroEnvelope = useMemo(
        () => (isRecord(macroData) ? (macroData as Record<string, unknown>) : null),
        [macroData],
    );
    const macroPayload = useMemo(
        () => extractObject(macroData) as MacroResponse,
        [macroData],
    );
    const toolMeta = useMemo(() => {
        const payload = macroEnvelope?.data;
        if (!isRecord(payload)) return null;
        const meta = payload.meta;
        return isRecord(meta) ? meta : null;
    }, [macroEnvelope]);
    const cacheMeta = useMemo(() => {
        const meta = macroEnvelope?.meta;
        return isRecord(meta) ? meta : null;
    }, [macroEnvelope]);

    const macroRows = useMemo(() => {
        if (!Array.isArray(macroData) && Array.isArray(macroPayload.records)) {
            return macroPayload.records;
        }
        return Array.isArray(macroData) ? macroData : [];
    }, [macroData, macroPayload]);

    const qualityMeta = isRecord(toolMeta?.quality) ? (toolMeta.quality as Record<string, unknown>) : null;
    const cacheInfo = isRecord(cacheMeta?.cache) ? (cacheMeta.cache as Record<string, unknown>) : null;
    const sourceChain = Array.isArray(toolMeta?.source_chain)
        ? toolMeta.source_chain.map((item) => String(item))
        : [];
    const qualityStatus = String(qualityMeta?.status ?? (macroRows.length ? 'available' : 'empty'));
    const backendUsed = String(qualityMeta?.backend_used ?? sourceChain[sourceChain.length - 1] ?? '-');
    const cacheHit = Boolean(cacheInfo?.hit);
    const degraded = Boolean(toolMeta?.degraded);

    const chartData = useMemo(() => {
        if (!macroRows.length) return null;
        const ordered = [...macroRows].reverse();
        return {
            categories: ordered.map((row) => String(row.date || row.period || row.quarter || '-')),
            values: ordered.map((row) => Number(row.value ?? 0)),
            change: ordered.map((row) => Number(row.yoy ?? row.yoyChange ?? row.momChange ?? 0)),
        };
    }, [macroRows]);

    return (
        <PageContainer>
            <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4 mb-6">
                <div>
                    <h1 className="text-3xl font-bold tracking-tight flex items-center gap-2">
                        <span>🌍</span>
                        宏观经济数据分析 (Macro Economics)
                    </h1>
                    <p className="text-muted-foreground mt-1 text-sm text-text-muted">全面追踪中国核心宏观经济指标及其长期趋势</p>
                    <div className="mt-3 flex flex-wrap gap-2">
                        <Badge variant="info">{qualityStatus}</Badge>
                        <Badge variant={degraded ? 'warning' : 'success'}>{degraded ? '存在降级链路' : '链路正常'}</Badge>
                        <Badge variant={cacheHit ? 'success' : 'neutral'}>{cacheHit ? '缓存命中' : '实时拉取'}</Badge>
                    </div>
                </div>

                <div className="flex gap-2 w-full md:w-auto">
                    <label htmlFor="macro-indicator-select" className="grid gap-1 text-xs text-text-secondary w-full md:w-auto">
                        <span>宏观指标</span>
                        <select
                            id="macro-indicator-select"
                            value={indicator}
                            onChange={(e) => setIndicator(e.target.value)}
                            className="w-full md:w-[250px] bg-surface border border-glass-border px-3 py-2 rounded-md"
                        >
                            {indicators.map((ind) => (
                                <option key={ind.value} value={ind.value}>{ind.label}</option>
                            ))}
                        </select>
                    </label>
                </div>
            </div>

            <SectionCard className="mb-6 p-4">
                <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
                    <div>
                        <h2 className="mt-0 mb-1 text-base font-semibold">常用宏观入口</h2>
                        <p className="m-0 text-sm text-text-secondary">当某个指标暂时为空时，先切到 CPI、PMI 或 M2 确认是不是单一数据缺口，再决定是否去数据中心排查。</p>
                    </div>
                    <div className="flex flex-wrap gap-2">
                        {['gdp', 'cpi', 'pmi', 'm2'].map((value) => (
                            <button
                                key={value}
                                type="button"
                                onClick={() => setIndicator(value)}
                                className={`px-3 py-1.5 rounded-full border text-sm cursor-pointer ${indicator === value ? 'border-primary text-primary' : 'border-border text-text-secondary hover:bg-surface'}`}
                            >
                                {value.toUpperCase()}
                            </button>
                        ))}
                        <Link href="/data" className="px-3 py-1.5 rounded-full border border-border text-sm no-underline text-inherit hover:bg-surface">去数据中心</Link>
                    </div>
                </div>
            </SectionCard>

            <SectionCard className="mb-6 p-4">
                <KpiGrid cols={4}>
                    <KpiCard title="记录条数" value={String(macroRows.length)} />
                    <KpiCard title="后端来源" value={backendUsed} />
                    <KpiCard title="缓存状态" value={cacheHit ? '命中' : '未命中'} />
                    <KpiCard title="链路节点" value={String(sourceChain.length)} />
                </KpiGrid>
                {sourceChain.length ? (
                    <div className="mt-4 rounded-[20px] border border-border bg-surface-alt/60 p-3 text-xs leading-6 text-text-secondary">
                        来源链路：{sourceChain.join(' -> ')}
                    </div>
                ) : null}
            </SectionCard>

            {error ? (
                <ErrorState text="数据获取失败" hint={error || '未知错误'} />
            ) : (
                <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                    <SectionCard className="col-span-1 md:col-span-2">
                        <div className="flex flex-row items-center justify-between mb-4">
                            <h3 className="text-lg font-bold">
                                {indicators.find(i => i.value === indicator)?.label} - 历史趋势
                            </h3>
                            <span>📊</span>
                        </div>
                        <div>
                            {isLoading ? (
                                <LoadingState text="加载宏观图表中..." />
                            ) : chartData ? (
                                <LineChart
                                    categories={chartData.categories}
                                    series={[
                                        { name: '指标值', data: chartData.values, color: '#1a73e8' },
                                        { name: '变动', data: chartData.change, color: '#10b981' },
                                    ]}
                                    height={260}
                                    yAxisName="数值"
                                />
                            ) : (
                                <EmptyState
                                    className="h-64 border border-glass-border rounded-md bg-surface-alt"
                                    text="当前指标暂无可用历史数据"
                                    hint="可以先切换到其他指标确认是否为单一数据源缺口，也可以去数据中心查看其他结构化数据。"
                                    action={
                                        <>
                                            {['cpi', 'pmi', 'm2'].map((value) => (
                                                <button
                                                    key={value}
                                                    type="button"
                                                    onClick={() => setIndicator(value)}
                                                    className="px-3 py-1.5 rounded border border-border text-sm cursor-pointer hover:bg-surface"
                                                >
                                                    切换到 {value.toUpperCase()}
                                                </button>
                                            ))}
                                            <button type="button" onClick={() => void refetch()} className="px-3 py-1.5 rounded border border-border text-sm cursor-pointer hover:bg-surface">重新加载</button>
                                            <Link href="/data" className="px-3 py-1.5 rounded border border-border text-sm no-underline text-inherit hover:bg-surface">去数据中心</Link>
                                        </>
                                    }
                                />
                            )}
                        </div>
                    </SectionCard>

                    <SectionCard className="col-span-1 md:col-span-2">
                        <h3 className="flex items-center gap-2 text-md font-bold mb-4">
                            <span>📈</span>
                            历史数据流水表
                        </h3>
                        <div>
                            {isLoading ? (
                                <LoadingState text="数据提取中..." />
                            ) : macroRows.length > 0 ? (
                                <DataTable
                                    columns={[
                                        { key: 'date', label: '报告期 (Period)', render: (v, r) => String(r.date || r.period || r.quarter || '-') },
                                        { key: 'value', label: '指标数值' },
                                        { key: 'yoy', label: '同比 / 环比增速', render: (v, r) => {
                                            const delta = r.yoy ?? r.yoyChange ?? r.momChange;
                                            return delta !== undefined && delta !== null ? `${delta}%` : '-';
                                        } }
                                    ]}
                                    rows={macroRows.slice(0, 50)}
                                    maxHeight={500}
                                />
                            ) : (
                                <EmptyState
                                    text="当前指标没有可展示的历史记录"
                                    hint="如果图表和表格都为空，通常意味着这个指标最近还没有同步到前端接口。先切换到其他高频指标确认范围，再决定是否去数据中心排查。"
                                    action={
                                        <>
                                            {['cpi', 'pmi', 'm2'].filter((value) => value !== indicator).map((value) => (
                                                <button
                                                    key={`table-${value}`}
                                                    type="button"
                                                    onClick={() => setIndicator(value)}
                                                    className="px-3 py-1.5 rounded border border-border text-sm cursor-pointer hover:bg-surface"
                                                >
                                                    改看 {value.toUpperCase()}
                                                </button>
                                            ))}
                                            <button type="button" onClick={() => void refetch()} className="px-3 py-1.5 rounded border border-border text-sm cursor-pointer hover:bg-surface">重新加载</button>
                                            <Link href="/research" className="px-3 py-1.5 rounded border border-border text-sm no-underline text-inherit hover:bg-surface">去研究页补充背景</Link>
                                        </>
                                    }
                                />
                            )}
                        </div>
                    </SectionCard>
                </div>
            )}
        </PageContainer>
    );
}
