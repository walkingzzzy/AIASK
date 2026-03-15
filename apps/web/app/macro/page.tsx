'use client';

import { useMemo, useState } from 'react';
import { PageContainer, SectionCard, DataTable } from '@/components/ui';
import { ErrorState, LoadingState } from '@/components/status-state';
import { LineChart } from '@/components/charts';
import { useApiQuery } from '@/hooks/use-api-query';

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

export default function MacroPage() {
    const [indicator, setIndicator] = useState('gdp');

    const indicators = [
        { value: 'gdp', label: '国内生产总值 (GDP)' },
        { value: 'cpi', label: '居民消费价格指数 (CPI)' },
        { value: 'pmi', label: '采购经理人指数 (PMI)' },
        { value: 'ppi', label: '工业生产者出厂价格指数 (PPI)' },
        { value: 'm2', label: '货币供应量 (M2)' }
    ];

    const { data: macroData, isPending: isLoading, error } = useApiQuery<MacroResponse | MacroRecord[]>(
        `/v1/macro/indicator/${indicator}`,
        { staleTime: 5 * 60 * 1000 },
    );

    const macroRows = useMemo(() => {
        if (macroData && !Array.isArray(macroData) && Array.isArray(macroData.records)) {
            return macroData.records;
        }
        return Array.isArray(macroData) ? macroData : [];
    }, [macroData]);

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
                </div>

                <div className="flex gap-2 w-full md:w-auto">
                    <select
                        value={indicator}
                        onChange={(e) => setIndicator(e.target.value)}
                        className="w-full md:w-[250px] bg-surface border border-glass-border px-3 py-2 rounded-md"
                    >
                        {indicators.map((ind) => (
                            <option key={ind.value} value={ind.value}>{ind.label}</option>
                        ))}
                    </select>
                </div>
            </div>

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
                                <div className="h-64 flex items-center justify-center border border-glass-border rounded-md bg-surface-alt">
                                    <p className="text-sm text-text-muted">暂无可用历史数据</p>
                                </div>
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
                                <div className="h-32 flex items-center justify-center text-text-muted">
                                    暂无可用历史数据
                                </div>
                            )}
                        </div>
                    </SectionCard>
                </div>
            )}
        </PageContainer>
    );
}
