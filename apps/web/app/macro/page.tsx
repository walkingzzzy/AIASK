'use client';

import { useMemo, useState } from 'react';
import CollapsibleSectionCard from '@/components/collapsible-section-card';
import Link from 'next/link';
import LightOverviewHero from '@/components/light-overview-hero';
import ProgressiveWorkbenchSection from '@/components/progressive-workbench-section';
import { PageContainer, DataTable, Badge, KpiCard, KpiGrid } from '@/components/ui';
import { EmptyState, ErrorState, LoadingState } from '@/components/status-state';
import { LineChart } from '@/components/charts';
import { useApiQuery } from '@/hooks/use-api-query';
import { useMobile } from '@/hooks/use-mobile';
import { usePageActions } from '@/hooks/use-page-actions';
import { usePageContext } from '@/hooks/use-page-context';
import { extractObject } from '@/lib/data-utils';
import { RESPONSIVE_BREAKPOINTS } from '@/lib/responsive-layout';
import { buildLocalResultContract, defaultWorkbenchTask, evidenceToSummary } from '@/lib/result-workbench';

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
    const compactLayout = useMobile(RESPONSIVE_BREAKPOINTS.dockOverlay);
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
    const sourceChain = useMemo(
        () => (Array.isArray(toolMeta?.source_chain)
            ? toolMeta.source_chain.map((item) => String(item))
            : []),
        [toolMeta],
    );
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
    const indicatorLabel = indicators.find((item) => item.value === indicator)?.label ?? indicator.toUpperCase();
    const latestMacroRow = macroRows[0] ?? null;
    const pageActions = useMemo(
        () => [
            {
                id: 'macro.refresh-selected',
                label: `刷新 ${indicator.toUpperCase()}`,
                description: '重新拉取当前宏观指标的最新数据',
                keywords: ['宏观', '刷新', indicator],
                scope: 'page' as const,
                pageKey: 'macro',
                run: async () => {
                    await refetch();
                    return { message: `已刷新 ${indicatorLabel}` };
                },
            },
            {
                id: 'macro.switch-cpi',
                label: '切到 CPI',
                description: '快速切到消费价格指数',
                keywords: ['CPI', '物价'],
                scope: 'page' as const,
                pageKey: 'macro',
                run: () => {
                    setIndicator('cpi');
                    return { message: '已切到 CPI' };
                },
            },
            {
                id: 'macro.switch-pmi',
                label: '切到 PMI',
                description: '快速切到采购经理人指数',
                keywords: ['PMI', '景气度'],
                scope: 'page' as const,
                pageKey: 'macro',
                run: () => {
                    setIndicator('pmi');
                    return { message: '已切到 PMI' };
                },
            },
        ],
        [indicator, indicatorLabel, refetch],
    );
    usePageActions(pageActions);
    const macroSummary = macroRows.length
        ? `${indicatorLabel} 当前已返回 ${macroRows.length} 条记录，链路状态 ${qualityStatus}，后端来源 ${backendUsed}${typeof latestMacroRow?.value === 'number' ? `，最近值 ${latestMacroRow.value}` : ''}。`
        : `${indicatorLabel} 当前暂无可展示的结构化数据，建议先切到 CPI、PMI 或 M2 判断是单指标缺口还是链路整体异常。`;
    const macroResult = useMemo(
        () =>
            buildLocalResultContract({
                summary: macroSummary,
                availableViews: chartData ? ['visual'] : [],
                pageActions,
                preferredActionIds: ['macro.refresh-selected', 'macro.switch-cpi', 'macro.switch-pmi'],
                recommendedLinks: [
                    { id: 'macro-link-data', label: '去数据中心', href: '/data' },
                    { id: 'macro-link-research', label: '去研究页', href: '/research' },
                    { id: 'macro-link-assistant', label: '继续追问 Copilot', href: `/assistant?from=macro&indicator=${encodeURIComponent(indicator)}` },
                ],
                evidence: [
                    { label: '当前指标', value: indicatorLabel },
                    { label: '记录条数', value: String(macroRows.length) },
                    { label: '链路状态', value: qualityStatus, tone: degraded ? 'warning' : 'neutral' },
                    { label: '后端来源', value: backendUsed },
                    { label: '缓存状态', value: cacheHit ? '命中' : '实时拉取' },
                    { label: '链路节点', value: String(sourceChain.length) },
                ],
                riskNotes: [
                    ...(degraded ? ['当前宏观链路存在降级，结论需要结合数据中心或其他高频指标交叉确认。'] : []),
                    ...(macroRows.length === 0 ? [`${indicatorLabel} 当前没有返回结构化记录。`] : []),
                ],
                freshness: cacheMeta?.fetchedAt || cacheMeta?.updatedAt || cacheMeta?.asOf
                    ? {
                        updatedAt: String(cacheMeta?.updatedAt ?? cacheMeta?.fetchedAt ?? ''),
                        asOf: String(cacheMeta?.asOf ?? ''),
                        label: '宏观快照',
                    }
                    : null,
                platformMeta: {
                    sourceTool: `macro/${indicator}`,
                    sourceChain,
                    degraded,
                },
                workbenchTask: defaultWorkbenchTask('macro', `复查 ${indicatorLabel}`, '/macro', 'macro-review', {
                    indicator,
                    qualityStatus,
                    rowCount: macroRows.length,
                }),
            }),
        [backendUsed, cacheHit, cacheMeta?.asOf, cacheMeta?.fetchedAt, cacheMeta?.updatedAt, chartData, degraded, indicator, indicatorLabel, macroRows.length, macroSummary, pageActions, qualityStatus, sourceChain],
    );
    usePageContext({
        pageKey: 'macro',
        title: '宏观经济数据分析',
        summary: macroSummary,
        objectType: 'macro-indicator',
        objectId: indicator,
        resultType: 'macro-indicator-analysis',
        tags: [indicatorLabel, qualityStatus, backendUsed, cacheHit ? '缓存命中' : '实时拉取'],
        suggestions: [
            `总结 ${indicatorLabel} 当前趋势与异常点`,
            '判断当前是单指标缺口还是链路整体异常',
            '给出下一步适合联动的数据页或研究页',
        ],
        recommendedActions: macroResult.recommendedActions ?? [],
        recommendedLinks: macroResult.recommendedLinks ?? [],
        evidenceSummary: evidenceToSummary(macroResult.evidence),
        riskNotes: macroResult.riskNotes ?? [],
        freshness: macroResult.freshness ?? null,
        raw: {
            indicator,
            rowCount: macroRows.length,
            sourceChain,
            qualityStatus,
            backendUsed,
            degraded,
        },
    });

    return (
        <PageContainer>
            <LightOverviewHero
                eyebrow="Macro Economics"
                title="宏观经济数据分析"
                summary="全面追踪中国核心宏观经济指标及其长期趋势，默认先看当前指标摘要，再决定是否下钻到图表和数据流水表。"
                badges={(
                    <>
                        <Badge variant="info">{qualityStatus}</Badge>
                        <Badge variant={degraded ? 'warning' : 'success'}>{degraded ? '存在降级链路' : '链路正常'}</Badge>
                        <Badge variant={cacheHit ? 'success' : 'neutral'}>{cacheHit ? '缓存命中' : '实时拉取'}</Badge>
                    </>
                )}
                actions={(
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
                )}
                status={(
                    <div
                        data-testid="page-primary-status"
                        className="rounded-[20px] border border-white/50 bg-white/28 px-4 py-3 text-sm shadow-[inset_0_1px_0_rgba(255,255,255,0.68)]"
                    >
                        <div className="font-medium text-text-primary">
                            当前指标 {indicatorLabel} ｜ 记录 {macroRows.length} 条 ｜ 后端 {backendUsed}
                        </div>
                        <p className="mb-0 mt-1 text-xs leading-6 text-text-secondary">
                            {sourceChain.length ? `来源链路：${sourceChain.join(' -> ')}` : '当前还没有来源链路信息'}
                        </p>
                    </div>
                )}
                metrics={[
                    { key: 'macro-records', label: '记录条数', value: String(macroRows.length) },
                    { key: 'macro-backend', label: '后端来源', value: backendUsed },
                    { key: 'macro-cache', label: '缓存状态', value: cacheHit ? '命中' : '未命中' },
                    { key: 'macro-chain', label: '链路节点', value: String(sourceChain.length) },
                ]}
                compact
            />

            {!compactLayout ? (
                <ProgressiveWorkbenchSection pageKey="macro" title="宏观结果工作台" result={macroResult} summaryMode="strip" />
            ) : null}

            <CollapsibleSectionCard
                title="常用入口与链路摘要"
                summary="首屏只保留当前指标选择。高频切换入口、缓存状态和来源链路下沉到这一层，避免和主图表争抢首屏。"
                badge={<Badge variant="neutral">{macroRows.length} 条记录</Badge>}
            >
                <div className="space-y-4">
                    <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
                        <div>
                            <h3 className="mt-0 mb-1 text-base font-semibold">常用宏观入口</h3>
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

                    <div className="rounded-[20px] border border-border bg-white/55 p-4">
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
                    </div>
                </div>
            </CollapsibleSectionCard>

            {error ? (
                <ErrorState text="数据获取失败" hint={error || '未知错误'} />
            ) : (
                <div className="space-y-4">
                    <CollapsibleSectionCard
                        title={`${indicatorLabel} 历史趋势`}
                        summary="默认先看一块主图表，确认趋势和变动方向。明细流水表单独折叠，避免首屏同时出现图表和长表。"
                        defaultOpen
                        badge={<Badge variant="info">主结果</Badge>}
                    >
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
                    </CollapsibleSectionCard>

                    <CollapsibleSectionCard
                        title="历史数据流水表"
                        summary="长表只在需要核对结构化记录时再展开，不再默认和图表并排占满首屏。"
                        badge={<Badge variant="neutral">{macroRows.length} 条</Badge>}
                    >
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
                    </CollapsibleSectionCard>
                </div>
            )}
        </PageContainer>
    );
}
