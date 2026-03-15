'use client';

import { useState, useMemo } from 'react';
import { PageContainer, SectionCard, KpiGrid, KpiCard } from '@/components/ui';
import { useApiQuery } from '@/hooks/use-api-query';
import { useApiMutation } from '@/hooks/use-api-mutation';
import { ErrorState } from '@/components/status-state';
import { apiKeys } from '@/lib/query-keys';

/**
 * T-050: Cache Management Panel
 */
export default function CachePage() {
    const [clearing, setClearing] = useState(false);
    const [actionError, setActionError] = useState<string | null>(null);

    const cacheQ = useApiQuery<unknown>('/admin/cache-stats', {
        refetchInterval: 10000,
        parse: (raw) => raw,
    });
    const clearApi = useApiMutation<unknown>({
        invalidates: [[...apiKeys.admin()]],
        successToast: '缓存已清理',
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
        setActionError(null);
        try {
            await clearApi.triggerAsync('/admin/cache/clear', { method: 'POST' }, { prefix });
            cacheQ.refetch();
        } catch (error) {
            setActionError(error instanceof Error ? error.message : String(error));
        } finally {
            setClearing(false);
        }
    };

    if (cacheQ.error) {
        return (
            <PageContainer>
                <h1 className="text-lg font-semibold mb-4">💾 缓存管理</h1>
                <ErrorState text={cacheQ.error} hint="当前页面需要管理员权限；请求失败时不再显示 0 命中率。" onRetry={() => cacheQ.refetch()} />
            </PageContainer>
        );
    }

    return (
        <PageContainer>
            <h1 className="text-lg font-semibold mb-4">💾 缓存管理</h1>
            {actionError ? <ErrorState text={actionError} /> : null}

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
