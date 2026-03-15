'use client';

import { useState, useMemo } from 'react';
import { PageContainer, SectionCard, Badge } from '@/components/ui';
import { useApiQuery } from '@/hooks/use-api-query';
import { useApiMutation } from '@/hooks/use-api-mutation';
import { ErrorState } from '@/components/status-state';
import { apiKeys } from '@/lib/query-keys';

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

    const letters = useMemo(() => {
        const raw = dlQ.data as any;
        const items = Array.isArray(raw) ? raw : raw?.items ?? raw?.data ?? [];
        return Array.isArray(items) ? items.map((l: Record<string, unknown>) => ({
            id: String(l.id ?? ''),
            tool: String(l.tool ?? l.toolName ?? ''),
            error: String(l.error ?? l.message ?? ''),
            payload: l.payload ? JSON.stringify(l.payload).slice(0, 200) : '',
            timestamp: String(l.timestamp ?? l.createdAt ?? ''),
            retries: Number(l.retries ?? 0),
        })) : [];
    }, [dlQ.data]);

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
                <h1 className="text-lg font-semibold">📭 死信队列</h1>
                {letters.length > 0 && (
                    <button onClick={handleClearAll} className="text-xs px-3 py-1.5 bg-danger/20 text-danger rounded-lg cursor-pointer border border-danger/30">
                        清除全部
                    </button>
                )}
            </div>
            {actionError ? <ErrorState text={actionError} /> : null}

            {letters.length === 0 ? (
                <SectionCard>
                    <p className="text-text-secondary text-sm text-center py-12">
                        {dlQ.isFetching ? '加载中...' : '🎉 无死信消息'}
                    </p>
                </SectionCard>
            ) : (
                <div className="space-y-2">
                    {letters.map((l) => (
                        <SectionCard key={l.id} className="p-3">
                            <div className="flex items-start justify-between gap-2">
                                <div className="flex-1 min-w-0">
                                    <div className="flex items-center gap-2 mb-1">
                                        <Badge variant="danger">{l.tool}</Badge>
                                        <span className="text-[10px] text-text-secondary">
                                            {l.timestamp ? new Date(l.timestamp).toLocaleString('zh-CN') : ''}
                                        </span>
                                        {l.retries > 0 && <span className="text-[10px] text-text-secondary">重试 {l.retries} 次</span>}
                                    </div>
                                    <p className="text-xs text-danger mb-1">{l.error}</p>
                                    {l.payload && <p className="text-[10px] text-text-secondary font-mono truncate">{l.payload}</p>}
                                </div>
                                <button
                                    onClick={() => handleRetry(l.id)}
                                    disabled={retrying === l.id}
                                    className="text-xs px-2 py-1 bg-primary/20 text-primary rounded cursor-pointer border border-primary/30 whitespace-nowrap"
                                >
                                    {retrying === l.id ? '重试中...' : '🔄 重试'}
                                </button>
                            </div>
                        </SectionCard>
                    ))}
                </div>
            )}
        </PageContainer>
    );
}
