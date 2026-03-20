'use client';

import Link from 'next/link';
import { useState, useMemo } from 'react';
import { PageContainer, SectionCard, Badge, KpiCard, KpiGrid } from '@/components/ui';
import { useApiQuery } from '@/hooks/use-api-query';
import { useApiMutation } from '@/hooks/use-api-mutation';
import { EmptyState, ErrorState, LoadingState } from '@/components/status-state';
import { apiKeys } from '@/lib/query-keys';

type DeadLetterItem = {
    id: string;
    tool: string;
    error: string;
    payload: string;
    timestamp: string;
    timestampMs: number | null;
    retries: number;
    priority: 'urgent' | 'warning' | 'info';
};

function getPriorityMeta(item: DeadLetterItem) {
    if (item.retries >= 3) {
        return {
            label: '需要人工处理',
            variant: 'danger' as const,
            hint: '这条死信已经多次失败，建议先检查工具健康、缓存或上游依赖，再决定是否继续重试。',
            score: 3,
        };
    }
    if (item.retries > 0) {
        return {
            label: '反复失败',
            variant: 'warning' as const,
            hint: '这条死信已经失败过，继续重试前最好先确认依赖是否恢复。',
            score: 2,
        };
    }
    return {
        label: '待首次重试',
        variant: 'info' as const,
        hint: '这条死信还没有人工干预，可以先执行一次重试确认是否为偶发异常。',
        score: 1,
    };
}

/**
 * T-051: Dead Letter Queue Panel
 */
export default function DeadLettersPage() {
    const [retrying, setRetrying] = useState<string | null>(null);
    const [actionError, setActionError] = useState<string | null>(null);

    const dlQ = useApiQuery<unknown>('/admin/dead-letters', {
        refetchInterval: 15000,
        parse: (raw) => raw,
    });
    const retryApi = useApiMutation<unknown>({
        invalidates: [[...apiKeys.admin()]],
        successToast: '死信已重试',
    });
    const clearApi = useApiMutation<unknown>({
        invalidates: [[...apiKeys.admin()]],
        successToast: '死信队列已清空',
    });

    const letters = useMemo<DeadLetterItem[]>(() => {
        const raw = dlQ.data as any;
        const items = Array.isArray(raw) ? raw : raw?.items ?? raw?.data ?? [];
        return Array.isArray(items) ? items.map((l: Record<string, unknown>, index: number) => {
            const timestamp = String(l.timestamp ?? l.createdAt ?? '');
            const timestampMs = timestamp ? Date.parse(timestamp) : Number.NaN;
            const retries = Number(l.retries ?? 0);
            return {
                id: String(l.id ?? `${String(l.tool ?? l.toolName ?? 'dead-letter')}-${timestamp || index}`),
                tool: String(l.tool ?? l.toolName ?? '未知工具'),
                error: String(l.error ?? l.message ?? '未提供错误信息'),
                payload: l.payload ? JSON.stringify(l.payload, null, 2) : '',
                timestamp,
                timestampMs: Number.isFinite(timestampMs) ? timestampMs : null,
                retries,
                priority: retries >= 3 ? 'urgent' : retries > 0 ? 'warning' : 'info',
            };
        }) : [];
    }, [dlQ.data]);

    const sortedLetters = useMemo(
        () => [...letters].sort((a, b) => {
            const priorityDiff = getPriorityMeta(b).score - getPriorityMeta(a).score;
            if (priorityDiff !== 0) return priorityDiff;
            return (b.timestampMs ?? 0) - (a.timestampMs ?? 0);
        }),
        [letters],
    );

    const summary = useMemo(() => {
        const urgent = letters.filter((item) => item.priority === 'urgent').length;
        const repeated = letters.filter((item) => item.retries > 0).length;
        const recent = letters.filter((item) => item.timestampMs != null && Date.now() - item.timestampMs < 24 * 60 * 60 * 1000).length;
        return {
            total: letters.length,
            urgent,
            repeated,
            recent,
        };
    }, [letters]);

    const handleRetry = async (id: string) => {
        setRetrying(id);
        setActionError(null);
        try {
            await retryApi.triggerAsync(`/admin/dead-letters/${id}/retry`, { method: 'POST' });
            dlQ.refetch();
        } catch (error) {
            setActionError(error instanceof Error ? error.message : String(error));
        } finally {
            setRetrying(null);
        }
    };

    const handleClearAll = async () => {
        setActionError(null);
        try {
            await clearApi.triggerAsync('/admin/dead-letters/clear', { method: 'POST' });
            dlQ.refetch();
        } catch (error) {
            setActionError(error instanceof Error ? error.message : String(error));
        }
    };

    if (dlQ.error) {
        return (
            <PageContainer>
                <div className="flex items-center justify-between mb-4">
                    <h1 className="text-lg font-semibold">📭 死信队列</h1>
                </div>
                <ErrorState text={dlQ.error} hint="当前页面需要管理员权限；请求失败时不再显示“无死信消息”。" onRetry={() => dlQ.refetch()} />
            </PageContainer>
        );
    }

    return (
        <PageContainer>
            <div className="flex items-center justify-between mb-4">
                <div>
                    <h1 className="text-lg font-semibold">📭 死信队列</h1>
                    <p className="mt-1 text-sm text-text-secondary">优先处理反复失败的任务，避免后台异常持续堆积并反复影响用户操作。</p>
                </div>
                {letters.length > 0 ? (
                    <button
                        type="button"
                        onClick={handleClearAll}
                        disabled={clearApi.isPending}
                        className="text-xs px-3 py-1.5 bg-danger/20 text-danger rounded-lg cursor-pointer border border-danger/30 disabled:opacity-50 disabled:cursor-not-allowed"
                    >
                        {clearApi.isPending ? '清除中...' : '清除全部'}
                    </button>
                ) : null}
            </div>
            {actionError ? <ErrorState text={actionError} /> : null}

            {letters.length > 0 ? (
                <>
                    <KpiGrid cols={4} className="mb-4">
                        <KpiCard title="待处理死信" value={summary.total} />
                        <KpiCard title="24 小时新增" value={summary.recent} />
                        <KpiCard title="反复失败" value={summary.repeated} className={summary.repeated > 0 ? 'ring-1 ring-warning/30' : ''} />
                        <KpiCard title="需要人工处理" value={summary.urgent} className={summary.urgent > 0 ? 'ring-1 ring-danger/30' : ''} />
                    </KpiGrid>

                    {summary.urgent > 0 ? (
                        <SectionCard className="mb-4 border border-danger/20">
                            <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
                                <div>
                                    <div className="text-sm font-medium text-danger">有 {summary.urgent} 条死信已经连续失败多次</div>
                                    <p className="mb-0 mt-1 text-xs leading-5 text-text-secondary">
                                        这类任务通常不是简单重试就能恢复。建议先排查工具健康、缓存状态或上游依赖，再回到这里处理。
                                    </p>
                                </div>
                                <div className="flex flex-wrap gap-2">
                                    <Link href="/admin/tools" className="rounded-full border border-danger/30 px-3 py-1 text-xs text-danger no-underline">检查工具健康</Link>
                                    <Link href="/admin/cache" className="rounded-full border border-glass-border px-3 py-1 text-xs text-text-secondary no-underline">查看缓存状态</Link>
                                </div>
                            </div>
                        </SectionCard>
                    ) : null}
                </>
            ) : null}

            {letters.length === 0 ? (
                <SectionCard>
                    {dlQ.isFetching ? (
                        <LoadingState text="正在检查后台失败任务..." />
                    ) : (
                        <EmptyState
                            text="当前没有待处理死信"
                            hint="说明近期后台任务基本已正常消费。若用户仍反馈异常，可继续检查工具健康或缓存状态。"
                            action={
                                <>
                                    <Link href="/admin/tools" className="rounded-full border border-glass-border px-3 py-1 text-xs text-text-secondary no-underline">检查工具健康</Link>
                                    <Link href="/admin/cache" className="rounded-full border border-glass-border px-3 py-1 text-xs text-text-secondary no-underline">查看缓存</Link>
                                </>
                            }
                        />
                    )}
                </SectionCard>
            ) : (
                <div className="space-y-2">
                    {sortedLetters.map((l) => {
                        const priority = getPriorityMeta(l);
                        return (
                        <SectionCard key={l.id} className="p-3">
                            <div className="flex items-start justify-between gap-2">
                                <div className="flex-1 min-w-0">
                                    <div className="flex items-center gap-2 mb-1">
                                        <Badge variant="danger">{l.tool}</Badge>
                                        <Badge variant={priority.variant}>{priority.label}</Badge>
                                        <span className="text-[10px] text-text-secondary">
                                            {l.timestampMs != null ? new Date(l.timestampMs).toLocaleString('zh-CN') : l.timestamp}
                                        </span>
                                        {l.retries > 0 && <span className="text-[10px] text-text-secondary">重试 {l.retries} 次</span>}
                                    </div>
                                    <p className="text-xs text-danger mb-1">{l.error}</p>
                                    <p className="mb-0 text-[11px] leading-5 text-text-secondary">{priority.hint}</p>
                                    {l.payload ? (
                                        <details className="mt-2 rounded-lg border border-glass-border bg-black/10 px-3 py-2">
                                            <summary className="cursor-pointer text-[11px] text-text-secondary">查看请求载荷</summary>
                                            <pre className="mb-0 mt-2 whitespace-pre-wrap break-all text-[10px] text-text-muted">{l.payload}</pre>
                                        </details>
                                    ) : null}
                                </div>
                                <div className="flex flex-col items-end gap-2">
                                    <button
                                        type="button"
                                        onClick={() => handleRetry(l.id)}
                                        disabled={retrying === l.id}
                                        className="text-xs px-2 py-1 bg-primary/20 text-primary rounded cursor-pointer border border-primary/30 whitespace-nowrap disabled:opacity-50 disabled:cursor-not-allowed"
                                    >
                                        {retrying === l.id ? '重试中...' : '🔄 重试'}
                                    </button>
                                    {l.priority === 'urgent' ? (
                                        <Link href="/admin/tools" className="text-[11px] text-danger underline">
                                            先排查工具
                                        </Link>
                                    ) : null}
                                </div>
                            </div>
                        </SectionCard>
                        );
                    })}
                </div>
            )}
        </PageContainer>
    );
}
