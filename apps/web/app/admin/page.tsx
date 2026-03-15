'use client';

import { PageContainer, SectionCard, KpiGrid, KpiCard } from '@/components/ui';
import { useApiQuery } from '@/hooks/use-api-query';

/**
 * Admin Overview Page — summary of system health.
 */
export default function AdminPage() {
    const healthQ = useApiQuery<unknown>('/health', {
        refetchInterval: 15000,
        parse: (raw) => raw,
    });

    const data = (healthQ.data ?? {}) as Record<string, unknown>;

    return (
        <PageContainer>
            <h1 className="text-lg font-semibold mb-4">🏠 管理后台概览</h1>

            <KpiGrid cols={4}>
                <KpiCard title="系统状态" value={String(data.status ?? 'unknown')} />
                <KpiCard title="运行时间" value={String(data.uptime ?? '-')} />
                <KpiCard title="MCP 版本" value={String(data.mcpVersion ?? '-')} />
                <KpiCard title="BFF 版本" value={String(data.bffVersion ?? '-')} />
            </KpiGrid>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mt-4">
                <SectionCard className="p-4">
                    <h3 className="mt-0 text-sm font-semibold mb-2">📊 快速导航</h3>
                    <div className="space-y-2">
                        <a href="/admin/tools" className="block px-3 py-2 rounded-lg glass-hover text-sm">🔧 MCP 工具仪表盘</a>
                        <a href="/admin/cache" className="block px-3 py-2 rounded-lg glass-hover text-sm">💾 缓存管理</a>
                        <a href="/admin/dead-letters" className="block px-3 py-2 rounded-lg glass-hover text-sm">📭 死信队列</a>
                        <a href="/admin/users" className="block px-3 py-2 rounded-lg glass-hover text-sm">👥 用户管理</a>
                        <a href="/settings/audit-log" className="block px-3 py-2 rounded-lg glass-hover text-sm">📋 审计日志</a>
                    </div>
                </SectionCard>

                <SectionCard className="p-4">
                    <h3 className="mt-0 text-sm font-semibold mb-2">⚡ 系统信息</h3>
                    <div className="space-y-1 text-sm text-text-secondary">
                        <p>Node: {String(data.nodeVersion ?? '-')}</p>
                        <p>DB: {String(data.dbStatus ?? '-')}</p>
                        <p>Redis: {String(data.redisStatus ?? '-')}</p>
                        <p>MCP: {String(data.mcpStatus ?? '-')}</p>
                    </div>
                </SectionCard>
            </div>
        </PageContainer>
    );
}
