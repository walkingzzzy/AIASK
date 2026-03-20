'use client';

import { useState, useMemo } from 'react';
import { PageContainer, SectionCard, KpiGrid, KpiCard } from '@/components/ui';
import { ConfirmDialog } from '@/components/ui/confirm-dialog';
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
    const [confirmTarget, setConfirmTarget] = useState<{ prefix?: string; label: string } | null>(null);
    const [dangerAck, setDangerAck] = useState(false);

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

    const prefixStats = useMemo(
        () => [...stats.prefixes].sort((a, b) => {
            const hitRateDiff = a.hitRate - b.hitRate;
            if (hitRateDiff !== 0) return hitRateDiff;
            return b.count - a.count;
        }),
        [stats.prefixes],
    );

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

    const confirmClear = async () => {
        if (!confirmTarget) return;
        const prefix = confirmTarget.prefix;
        setConfirmTarget(null);
        setDangerAck(false);
        await handleClear(prefix);
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

            <SectionCard className="mb-4 p-4">
                <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
                    <div>
                        <h2 className="mt-0 mb-1 text-base font-semibold">操作建议</h2>
                        <p className="m-0 text-sm text-text-secondary">
                            优先清理单个前缀缓存，只有在大面积缓存异常或结构升级后，才建议执行“清除全部缓存”。
                        </p>
                    </div>
                    <div className="rounded-xl border border-warning/20 bg-warning/5 px-3 py-2 text-xs leading-5 text-text-secondary">
                        全量清理会放大瞬时回源压力，并可能让用户短时间内看到更多加载态。
                    </div>
                </div>
            </SectionCard>

            <KpiGrid cols={4}>
                <KpiCard title="命中率" value={`${(stats.hitRate * 100).toFixed(1)}%`} />
                <KpiCard title="总键数" value={stats.totalKeys.toLocaleString()} />
                <KpiCard title="内存占用" value={stats.memoryUsed} />
                <KpiCard title="命中/未命中" value={`${stats.hits}/${stats.misses}`} />
            </KpiGrid>

            <div className="flex gap-2 mt-4 mb-4">
                <button
                    onClick={() => setConfirmTarget({ label: '全部缓存' })}
                    disabled={clearing}
                    className="text-xs px-3 py-1.5 bg-danger/20 text-danger rounded-lg cursor-pointer border border-danger/30 hover:bg-danger/30"
                >
                    {clearing ? '清除中...' : '🗑 清除全部缓存'}
                </button>
            </div>

            {prefixStats.length > 0 && (
                <SectionCard className="p-3">
                    <div className="flex items-center justify-between gap-3 mb-3 flex-wrap">
                        <div>
                            <h3 className="mt-0 mb-1 text-sm font-semibold">按前缀统计</h3>
                            <p className="m-0 text-xs text-text-secondary">低命中率前缀会优先显示，便于先做局部清理，而不是直接全量清空。</p>
                        </div>
                    </div>
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
                                {prefixStats.map((p) => (
                                    <tr key={p.prefix} className="border-b border-glass-border/50 hover:bg-white/5">
                                        <td className="py-2 px-2 font-mono text-xs">{p.prefix}</td>
                                        <td className="py-2 px-2 text-right">{p.count}</td>
                                        <td className="py-2 px-2 text-right">{(p.hitRate * 100).toFixed(1)}%</td>
                                        <td className="py-2 px-2 text-center">
                                            <button
                                                onClick={() => setConfirmTarget({ prefix: p.prefix, label: p.prefix })}
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

            <ConfirmDialog
                open={confirmTarget != null}
                title="确认清理缓存"
                danger
                confirmDisabled={confirmTarget?.prefix == null && !dangerAck}
                confirmText={clearing ? '清理中...' : '确认清理'}
                cancelText="取消"
                onConfirm={() => void confirmClear()}
                onCancel={() => {
                    setConfirmTarget(null);
                    setDangerAck(false);
                }}
            >
                {confirmTarget ? (
                    <div className="space-y-2 text-sm">
                        <p className="m-0">即将清理：<span className="font-medium">{confirmTarget.label}</span></p>
                        <p className="m-0 text-text-secondary">该操作会立即删除对应缓存键，后续请求需要重新回源加载数据。</p>
                        {confirmTarget.prefix == null ? (
                            <>
                                <p className="m-0 text-warning text-xs">这是全量危险操作。建议确认当前确实存在大面积缓存污染、版本切换或命中率异常，再继续。</p>
                                <label className="flex items-start gap-2 rounded-lg border border-warning/20 bg-warning/5 px-3 py-2 text-xs text-text-secondary">
                                    <input
                                        type="checkbox"
                                        checked={dangerAck}
                                        onChange={(e) => setDangerAck(e.target.checked)}
                                        className="mt-0.5 rounded border-border accent-primary"
                                    />
                                    <span>我已知晓全量清理会让所有缓存回源重建，并可能导致短时加载变慢。</span>
                                </label>
                            </>
                        ) : null}
                    </div>
                ) : null}
            </ConfirmDialog>
        </PageContainer>
    );
}
