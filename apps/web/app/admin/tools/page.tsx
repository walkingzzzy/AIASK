'use client';

import { useMemo } from 'react';
import { PageContainer, SectionCard, KpiGrid, KpiCard, Badge } from '@/components/ui';
import { BarChart } from '@/components/charts';
import { useApiQuery } from '@/hooks/use-api-query';
import { ErrorState } from '@/components/status-state';

/**
 * T-049: MCP Tools Dashboard
 * Shows tool call frequency, latency, error rate, and health status.
 */
export default function ToolsDashboardPage() {
    const statsQ = useApiQuery<unknown>('/admin/mcp-stats', {
        refetchInterval: 15000,
        parse: (raw) => raw,
    });

    const data = useMemo(() => {
        const raw = (statsQ.data ?? {}) as Record<string, unknown>;
        const tools = Array.isArray(raw.tools) ? raw.tools : [];
        return {
            totalCalls: Number(raw.totalCalls ?? 0),
            avgLatency: Number(raw.avgLatency ?? 0),
            p99Latency: Number(raw.p99Latency ?? 0),
            errorRate: Number(raw.errorRate ?? 0),
            tools: tools.slice(0, 20).map((t: Record<string, unknown>) => ({
                name: String(t.name ?? ''),
                calls: Number(t.calls ?? 0),
                avgMs: Number(t.avgMs ?? 0),
                errors: Number(t.errors ?? 0),
                status: String(t.status ?? 'healthy'),
            })),
        };
    }, [statsQ.data]);

    const barData = data.tools.map((t) => ({
        label: t.name.replace(/^(get_|create_|update_|delete_)/, ''),
        value: t.calls,
    }));
    const abnormalTools = useMemo(() => data.tools.filter((tool) => tool.status !== 'healthy' || tool.errors > 0).slice(0, 6), [data.tools]);
    const sortedTools = useMemo(() => [...data.tools].sort((a, b) => {
        const aRisk = a.status !== 'healthy' || a.errors > 0 ? 1 : 0;
        const bRisk = b.status !== 'healthy' || b.errors > 0 ? 1 : 0;
        if (aRisk !== bRisk) return bRisk - aRisk;
        return b.calls - a.calls;
    }), [data.tools]);

    const STATUS_COLORS: Record<string, 'success' | 'warning' | 'danger'> = {
        healthy: 'success', degraded: 'warning', down: 'danger',
    };

    if (statsQ.error) {
        return (
            <PageContainer>
                <h1 className="text-lg font-semibold mb-4">🔧 MCP 工具仪表盘</h1>
                <ErrorState text={statsQ.error} hint="当前页面需要管理员权限；请求失败时不再伪装成空数据。" onRetry={() => statsQ.refetch()} />
            </PageContainer>
        );
    }

    return (
        <PageContainer>
            <h1 className="text-lg font-semibold mb-4">🔧 MCP 工具仪表盘</h1>

            <KpiGrid cols={4}>
                <KpiCard title="总调用次数" value={data.totalCalls.toLocaleString()} />
                <KpiCard title="平均延迟" value={`${data.avgLatency.toFixed(0)}ms`} />
                <KpiCard title="P99 延迟" value={`${data.p99Latency.toFixed(0)}ms`} />
                <KpiCard title="错误率" value={`${(data.errorRate * 100).toFixed(2)}%`} />
            </KpiGrid>

            {abnormalTools.length > 0 && (
                <SectionCard className="mt-4 p-4">
                    <h3 className="mt-0 text-sm font-semibold">优先关注工具</h3>
                    <p className="mt-1 text-xs text-text-secondary">以下工具当前存在降级、不可用或错误次数偏高的情况，已前置到首屏方便管理员优先处理。</p>
                    <div className="mt-3 flex flex-wrap gap-2">
                        {abnormalTools.map((tool) => (
                            <div key={tool.name} className="rounded-full border border-glass-border px-3 py-1 text-xs text-text-secondary">
                                <span className="font-medium text-text-primary">{tool.name}</span>
                                {' · '}
                                {tool.status !== 'healthy' ? `状态 ${tool.status}` : `错误 ${tool.errors} 次`}
                            </div>
                        ))}
                    </div>
                </SectionCard>
            )}

            {barData.length > 0 && (
                <SectionCard className="mt-4 p-3">
                    <h3 className="mt-0 text-sm font-semibold">调用频次 Top 20</h3>
                    <BarChart items={barData} height={280} />
                </SectionCard>
            )}

            {data.tools.length > 0 && (
                <SectionCard className="mt-4 p-3">
                    <h3 className="mt-0 text-sm font-semibold">工具健康度矩阵</h3>
                    <div className="overflow-x-auto">
                        <table className="w-full text-sm">
                            <thead>
                                <tr className="border-b border-glass-border text-text-secondary text-xs">
                                    <th className="text-left py-2 px-2">工具名</th>
                                    <th className="text-right py-2 px-2">调用数</th>
                                    <th className="text-right py-2 px-2">平均延迟</th>
                                    <th className="text-right py-2 px-2">错误数</th>
                                    <th className="text-center py-2 px-2">状态</th>
                                </tr>
                            </thead>
                            <tbody>
                                {sortedTools.map((t) => (
                                    <tr key={t.name} className="border-b border-glass-border/50 hover:bg-white/5">
                                        <td className="py-2 px-2 font-mono text-xs">{t.name}</td>
                                        <td className="py-2 px-2 text-right">{t.calls}</td>
                                        <td className="py-2 px-2 text-right">{t.avgMs.toFixed(0)}ms</td>
                                        <td className={`py-2 px-2 text-right ${t.errors > 0 ? 'text-danger' : ''}`}>{t.errors}</td>
                                        <td className="py-2 px-2 text-center">
                                            <Badge variant={STATUS_COLORS[t.status] ?? 'info'}>
                                                {t.status === 'healthy' ? '🟢' : t.status === 'degraded' ? '🟡' : '🔴'}
                                            </Badge>
                                        </td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                </SectionCard>
            )}

            {!statsQ.data && (
                <SectionCard className="mt-4">
                    <p className="text-text-secondary text-sm text-center py-8">
                        {statsQ.isFetching ? '加载工具统计...' : '暂无统计数据'}
                    </p>
                </SectionCard>
            )}
        </PageContainer>
    );
}
