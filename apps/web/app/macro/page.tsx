'use client';

import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { PageContainer, SectionCard, DataTable } from '@/components/ui';
import { ErrorState, LoadingState } from '@/components/status-state';
import { BFF_BASE } from '@/lib/api';

export default function MacroPage() {
    const [indicator, setIndicator] = useState('gdp');

    const indicators = [
        { value: 'gdp', label: '国内生产总值 (GDP)' },
        { value: 'cpi', label: '居民消费价格指数 (CPI)' },
        { value: 'pmi', label: '采购经理人指数 (PMI)' },
        { value: 'ppi', label: '工业生产者出厂价格指数 (PPI)' },
        { value: 'm2', label: '货币供应量 (M2)' }
    ];

    const { data: macroData, isLoading, error } = useQuery({
        queryKey: ['macro:indicator', indicator],
        queryFn: async () => {
            const res = await fetch(`${BFF_BASE}/v1/macro/indicator/${indicator}`, { credentials: 'include' });
            if (!res.ok) throw new Error('宏观数据获取失败');
            const payload = await res.json();
            return payload.data?.data || payload.data || [];
        },
        staleTime: 5 * 60 * 1000,
    });

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
                <ErrorState text="数据获取失败" hint={error instanceof Error ? error.message : '未知错误'} />
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
                            ) : (
                                <div className="h-64 flex items-center justify-center border border-glass-border rounded-md bg-surface-alt">
                                    <p className="text-sm text-text-muted">图表渲染区：{indicator.toUpperCase()} 时序曲线</p>
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
                            ) : macroData && Array.isArray(macroData) && macroData.length > 0 ? (
                                <DataTable
                                    columns={[
                                        { key: 'date', label: '报告期 (Period)', render: (v, r) => String(r.date || r.period || r.quarter || '-') },
                                        { key: 'value', label: '指标数值' },
                                        { key: 'yoy', label: '同比 / 环比增速', render: (v) => v !== undefined ? `${v}%` : '-' }
                                    ]}
                                    rows={macroData.slice(0, 50)}
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
