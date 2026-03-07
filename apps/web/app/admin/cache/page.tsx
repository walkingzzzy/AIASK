'use client';

import { useState, useMemo } from 'react';
import { PageContainer, SectionCard, KpiGrid, KpiCard, Badge } from '@/components/ui';
import { PieChart } from '@/components/charts';
import { useApiQuery } from '@/hooks/use-api-query';
import { BFF_BASE } from '@/lib/api';

/**
 * T-050: Cache Management Panel
 */
export default function CachePage() {
    const [clearing, setClearing] = useState(false);

    const cacheQ = useApiQuery<unknown>('/admin/cache-stats', {
        refetchInterval: 10000,
        parse: (raw) => raw,
    });

    const stats = useMemo(() => {
        const raw = (cacheQ.data ?? {}) as Record<string, unknown>;
        const prefixes = Array.isArray(raw.prefixes) ? raw.prefixes : [];
        return {
            hitRate: Number(raw.hitRate ?? 0),
            totalKeys: Number(raw.totalKeys ?? 0),
            memoryUsed: String(raw.memoryUsed ?? '0 MB'),
            hits: Number(raw.hits ?? 0),
            misses: Number(raw.misses ?? 0),
            prefixes: prefixes.map((p: Record<string, unknown>) => ({
                prefix: String(p.prefix ?? ''),
                count: Number(p.count ?? 0),
                hitRate: Number(p.hitRate ?? 0),
            })),
        };
    }, [cacheQ.data]);

    const handleClear = async (prefix?: string) => {
        setClearing(true);
        try {
            await fetch(`${BFF_BASE}/admin/cache/clear`, {
                method: 'POST',
                credentials: 'include',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ prefix }),
            });
            cacheQ.refetch();
        } finally {
            setClearing(false);
        }
    };

    return (
        <PageContainer>
            <h2 className="text-lg font-semibold mb-4">💾 缓存管理</h2>

            <KpiGrid cols={4}>
                <KpiCard title="命中率" value={`${(stats.hitRate * 100).toFixed(1)}%`} />
                <KpiCard title="总键数" value={stats.totalKeys.toLocaleString()} />
                <KpiCard title="内存占用" value={stats.memoryUsed} />
                <KpiCard title="命中/未命中" value={`${stats.hits}/${stats.misses}`} />
            </KpiGrid>

            <div className="flex gap-2 mt-4 mb-4">
                <button
                    onClick={() => handleClear()}
                    disabled={clearing}
                    className="text-xs px-3 py-1.5 bg-danger/20 text-danger rounded-lg cursor-pointer border border-danger/30 hover:bg-danger/30"
                >
                    {clearing ? '清除中...' : '🗑 清除全部缓存'}
                </button>
            </div>

            {stats.prefixes.length > 0 && (
                <SectionCard className="p-3">
                    <h3 className="mt-0 text-sm font-semibold">按前缀统计</h3>
                    <div className="overflow-x-auto">
                        <table className="w-full text-sm">
                            <thead>
                                <tr className="border-b border-glass-border text-text-secondary text-xs">
                                    <th className="text-left py-2 px-2">前缀</th>
                                    <th className="text-right py-2 px-2">键数</th>
                                    <th className="text-right py-2 px-2">命中率</th>
                                    <th className="text-center py-2 px-2">操作</th>
                                </tr>
                            </thead>
                            <tbody>
                                {stats.prefixes.map((p) => (
                                    <tr key={p.prefix} className="border-b border-glass-border/50 hover:bg-white/5">
                                        <td className="py-2 px-2 font-mono text-xs">{p.prefix}</td>
                                        <td className="py-2 px-2 text-right">{p.count}</td>
                                        <td className="py-2 px-2 text-right">{(p.hitRate * 100).toFixed(1)}%</td>
                                        <td className="py-2 px-2 text-center">
                                            <button
                                                onClick={() => handleClear(p.prefix)}
                                                disabled={clearing}
                                                className="text-[11px] text-danger cursor-pointer hover:underline"
                                            >
                                                清除
                                            </button>
                                        </td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                </SectionCard>
            )}
        </PageContainer>
    );
}
