'use client';

import Link from 'next/link';
import { useCallback, useState, useMemo } from 'react';
import ResultWorkbench from '@/components/result-workbench';
import { PageContainer, SectionCard, Badge, DataTable, ConfirmDialog } from '@/components/ui';
import { useApiQuery } from '@/hooks/use-api-query';
import { useApiMutation } from '@/hooks/use-api-mutation';
import { useMobile } from '@/hooks/use-mobile';
import { usePageActions } from '@/hooks/use-page-actions';
import { usePageContext } from '@/hooks/use-page-context';
import { EmptyState, ErrorState, LoadingState } from '@/components/status-state';
import { isPermissionDeniedErrorMessage } from '@/lib/api';
import { apiKeys } from '@/lib/query-keys';
import { RESPONSIVE_BREAKPOINTS } from '@/lib/responsive-layout';
import { buildLocalResultContract, defaultWorkbenchTask, evidenceToSummary } from '@/lib/result-workbench';

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

function readRecord(value: unknown): Record<string, unknown> {
    if (!value || typeof value !== 'object' || Array.isArray(value)) {
        return {};
    }
    return value as Record<string, unknown>;
}

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
    const [confirmClearOpen, setConfirmClearOpen] = useState(false);
    const compactLayout = useMobile(RESPONSIVE_BREAKPOINTS.splitCollapse);

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
        const raw = readRecord(dlQ.data);
        const data = readRecord(raw.data);
        const items = Array.isArray(dlQ.data) ? dlQ.data : Array.isArray(raw.items) ? raw.items : Array.isArray(data.items) ? data.items : raw.data ?? [];
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
    const refreshDeadLetters = useCallback(async () => {
        await dlQ.refetch();
    }, [dlQ]);
    const deadLettersActions = useMemo(
        () => [
            {
                id: 'admin-dead-letters.refresh',
                label: '刷新死信队列',
                description: '重新拉取待处理死信及其优先级',
                keywords: ['死信', '刷新'],
                scope: 'page' as const,
                pageKey: 'admin-dead-letters',
                run: async () => {
                    await refreshDeadLetters();
                    return { message: '已刷新死信队列' };
                },
            },
            {
                id: 'admin-dead-letters.confirm-clear',
                label: '准备清空队列',
                description: '打开死信清空确认框',
                keywords: ['死信', '清空', '危险操作'],
                scope: 'page' as const,
                pageKey: 'admin-dead-letters',
                run: () => {
                    setConfirmClearOpen(true);
                    return { message: '已打开清空确认' };
                },
            },
        ],
        [refreshDeadLetters],
    );
    usePageActions(deadLettersActions);
    const deadLettersSummary = summary.total > 0
        ? `当前待处理死信 ${summary.total} 条，其中 ${summary.urgent} 条需要人工处理，最近 24 小时新增 ${summary.recent} 条。`
        : '当前没有待处理死信，后台任务队列处于空闲或已完成清理状态。';
    const deadLettersResult = buildLocalResultContract({
        summary: deadLettersSummary,
        availableViews: sortedLetters.length > 1 ? ['compare'] : [],
        pageActions: deadLettersActions,
        preferredActionIds: ['admin-dead-letters.refresh', 'admin-dead-letters.confirm-clear'],
        recommendedLinks: [
            { id: 'dead-letters-link-tools', label: '检查工具健康', href: '/admin/tools' },
            { id: 'dead-letters-link-cache', label: '查看缓存状态', href: '/admin/cache' },
            { id: 'dead-letters-link-audit', label: '审计日志', href: '/settings/audit-log' },
        ],
        evidence: [
            { label: '待处理死信', value: String(summary.total) },
            { label: '人工处理', value: String(summary.urgent), tone: summary.urgent > 0 ? 'warning' : 'neutral' },
            { label: '反复失败', value: String(summary.repeated) },
            { label: '24 小时新增', value: String(summary.recent) },
        ],
        riskNotes: [
            ...(actionError ? [actionError] : []),
            ...(summary.urgent > 0 ? [`当前有 ${summary.urgent} 条死信已经连续失败多次。`] : []),
            ...(summary.total === 0 ? ['当前死信队列为空。'] : []),
        ],
        freshness: dlQ.dataUpdatedAt ? { updatedAt: new Date(dlQ.dataUpdatedAt).toISOString(), label: '死信快照' } : null,
        platformMeta: {
            sourceTool: 'admin/dead-letters',
            sourceChain: ['admin', 'dead-letters'],
            degraded: Boolean(actionError || dlQ.error),
            fallbackReason: [actionError, dlQ.error].filter((item): item is string => Boolean(item)),
        },
        workbenchTask: defaultWorkbenchTask('admin-dead-letters', '复查死信队列', '/admin/dead-letters', 'dead-letter-review', {
            total: summary.total,
            urgent: summary.urgent,
            repeated: summary.repeated,
        }),
    });
    usePageContext({
        pageKey: 'admin-dead-letters',
        title: '死信队列',
        summary: deadLettersSummary,
        objectType: 'dead-letter-queue',
        objectId: 'admin-dead-letters',
        resultType: 'dead-letter-panel',
        tags: [`${summary.total} 条待处理`, `${summary.urgent} 条人工处理`, `${summary.recent} 条新增`],
        suggestions: [
            '总结当前死信队列风险和优先处理项',
            '判断应先检查工具健康、缓存还是上游依赖',
            '解释为什么不应直接盲目清空队列',
        ],
        recommendedActions: deadLettersResult.recommendedActions ?? [],
        recommendedLinks: deadLettersResult.recommendedLinks ?? [],
        evidenceSummary: evidenceToSummary(deadLettersResult.evidence),
        riskNotes: deadLettersResult.riskNotes ?? [],
        freshness: deadLettersResult.freshness ?? null,
        raw: {
            total: summary.total,
            urgent: summary.urgent,
            repeated: summary.repeated,
            recent: summary.recent,
        },
    });

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
        const permissionDenied = isPermissionDeniedErrorMessage(dlQ.error);
        return (
            <PageContainer>
                <div className="flex items-center justify-between mb-4">
                    <h1 className="text-lg font-semibold">📭 死信队列</h1>
                </div>
                {permissionDenied ? (
                    <SectionCard className="p-4">
                        <EmptyState
                            variant="full"
                            text="当前账号无权查看死信队列"
                            hint="如果这是预期的权限拒绝，请保留该状态并避免继续重试写操作；如果当前账号应该拥有管理员权限，请先核对登录身份与角色。"
                            action={
                                <>
                                    <Link href="/admin" className="rounded-full border border-glass-border px-3 py-1 text-xs text-text-secondary no-underline">返回管理后台</Link>
                                    <Link href="/admin/tools" className="rounded-full border border-glass-border px-3 py-1 text-xs text-text-secondary no-underline">检查工具健康</Link>
                                </>
                            }
                        />
                    </SectionCard>
                ) : (
                    <ErrorState text={dlQ.error} hint="当前页面需要管理员权限；请求失败时会显示真实错误，而不是“无死信消息”。" onRetry={() => dlQ.refetch()} />
                )}
            </PageContainer>
        );
    }

    return (
        <PageContainer>
            <div className="mb-4">
                <h1 className="text-lg font-semibold">📭 死信队列</h1>
                <p className="mt-1 text-sm text-text-secondary">先查看待处理概览和主表；排障说明与高风险动作可按需展开。</p>
            </div>
            {actionError ? <ErrorState text={actionError} /> : null}

            <ResultWorkbench pageKey="admin-dead-letters" title="死信结果工作台" result={deadLettersResult} />

            {letters.length > 0 ? (
                <SectionCard className="mb-4 p-4">
                    <div className="flex flex-col gap-4 xl:flex-row xl:items-start xl:justify-between">
                        <div className="min-w-0 flex-1">
                            <div className="text-sm font-medium text-text-primary">当前待处理概览</div>
                            <div className="mt-1 text-sm text-text-secondary">
                                待处理 {summary.total} 条 ｜ 需人工处理 {summary.urgent} 条 ｜ 最近 24 小时新增 {summary.recent} 条
                            </div>
                            <div className="mt-3 grid gap-2 sm:grid-cols-2 xl:grid-cols-4">
                                <div className="rounded-2xl border border-border bg-surface px-3 py-3">
                                    <div className="text-[11px] uppercase tracking-[0.14em] text-text-muted">待处理死信</div>
                                    <div className="mt-2 text-xl font-semibold text-text-primary">{summary.total}</div>
                                </div>
                                <div className="rounded-2xl border border-border bg-surface px-3 py-3">
                                    <div className="text-[11px] uppercase tracking-[0.14em] text-text-muted">24 小时新增</div>
                                    <div className="mt-2 text-xl font-semibold text-text-primary">{summary.recent}</div>
                                </div>
                                <div className="rounded-2xl border border-border bg-surface px-3 py-3">
                                    <div className="text-[11px] uppercase tracking-[0.14em] text-text-muted">反复失败</div>
                                    <div className="mt-2 text-xl font-semibold text-text-primary">{summary.repeated}</div>
                                </div>
                                <div className="rounded-2xl border border-border bg-surface px-3 py-3">
                                    <div className="text-[11px] uppercase tracking-[0.14em] text-text-muted">需要人工处理</div>
                                    <div className="mt-2 text-xl font-semibold text-text-primary">{summary.urgent}</div>
                                </div>
                            </div>
                            {summary.urgent > 0 ? (
                                <div className="mt-3 rounded-2xl border border-danger/20 bg-danger/5 px-3 py-3 text-sm text-text-secondary">
                                    有 {summary.urgent} 条死信已经连续失败多次。建议先检查工具健康、缓存状态或上游依赖，再决定是否继续重试。
                                </div>
                            ) : null}
                        </div>
                        <details className="w-full rounded-2xl border border-danger/20 bg-danger/5 px-3 py-3 xl:max-w-[320px]" open={!compactLayout && summary.urgent > 0}>
                            <summary className="cursor-pointer text-sm font-medium text-danger">危险操作与排障入口</summary>
                            <div className="mt-3 space-y-3 text-xs text-text-secondary">
                                <div>“清除全部”会直接清空待处理队列，仅在确认当前队列已经无保留价值时执行。</div>
                                <div className="flex flex-wrap gap-2">
                                    <Link href="/admin/tools" className="rounded-full border border-danger/30 px-3 py-1 text-xs text-danger no-underline">检查工具健康</Link>
                                    <Link href="/admin/cache" className="rounded-full border border-glass-border px-3 py-1 text-xs text-text-secondary no-underline">查看缓存状态</Link>
                                </div>
                                <button
                                    type="button"
                                    onClick={() => setConfirmClearOpen(true)}
                                    disabled={clearApi.isPending}
                                    data-testid="dead-letters-clear-all-action"
                                    className="w-full rounded-lg border border-danger/30 bg-danger/20 px-3 py-2 text-xs text-danger disabled:cursor-not-allowed disabled:opacity-50"
                                >
                                    {clearApi.isPending ? '清除中...' : '清除全部'}
                                </button>
                            </div>
                        </details>
                    </div>
                </SectionCard>
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
                <SectionCard className="p-3">
                    <div className="mb-3 flex flex-wrap items-start justify-between gap-3">
                        <div>
                            <div className="text-sm font-medium text-text-primary">死信主表</div>
                            <div className="mt-1 text-sm text-text-secondary">
                                默认只展示状态、时间和错误摘要；载荷与排障建议进入详情态。
                            </div>
                        </div>
                        <div className="text-xs text-text-secondary">
                            当前记录 {sortedLetters.length} 条 ｜ 首先处理“需要人工处理”与“反复失败”
                        </div>
                    </div>
                    <DataTable
                        rows={sortedLetters as unknown as Record<string, unknown>[]}
                        pageSize={8}
                        maxHeight={560}
                        rowKey="id"
                        columns={[
                            {
                                key: 'tool',
                                label: '来源',
                                render: (value) => <Badge variant="danger">{String(value || '未知工具')}</Badge>,
                            },
                            {
                                key: 'priority',
                                label: '状态',
                                render: (_value, row) => {
                                    const item = row as unknown as DeadLetterItem;
                                    const priority = getPriorityMeta(item);
                                    return (
                                        <div className="space-y-1">
                                            <Badge variant={priority.variant}>{priority.label}</Badge>
                                            <div className="text-[11px] text-text-secondary">重试 {item.retries} 次</div>
                                        </div>
                                    );
                                },
                            },
                            {
                                key: 'error',
                                label: '错误摘要',
                                render: (value, row) => {
                                    const item = row as unknown as DeadLetterItem;
                                    const priority = getPriorityMeta(item);
                                    return (
                                        <div className="space-y-1">
                                            <div className="text-sm text-danger">{String(value || '未提供错误信息')}</div>
                                            <div className="text-xs text-text-secondary">{priority.hint}</div>
                                        </div>
                                    );
                                },
                            },
                            {
                                key: 'timestamp',
                                label: '最近失败',
                                render: (_value, row) => {
                                    const item = row as unknown as DeadLetterItem;
                                    return item.timestampMs != null
                                        ? new Date(item.timestampMs).toLocaleString('zh-CN')
                                        : item.timestamp;
                                },
                            },
                            {
                                key: 'detail',
                                label: '详情与操作',
                                sortable: false,
                                render: (_value, row) => {
                                    const item = row as unknown as DeadLetterItem;
                                    return (
                                        <div className="space-y-2">
                                            <button
                                                type="button"
                                                onClick={() => handleRetry(item.id)}
                                                disabled={retrying === item.id}
                                                data-testid={`dead-letter-retry-${item.id}`}
                                                className="rounded-lg border border-primary/30 bg-primary/20 px-3 py-1.5 text-xs text-primary disabled:cursor-not-allowed disabled:opacity-50"
                                            >
                                                {retrying === item.id ? '重试中...' : '🔄 重试'}
                                            </button>
                                            <details className="rounded-lg border border-glass-border bg-white/35 px-3 py-2">
                                                <summary className="cursor-pointer text-xs text-text-secondary">查看载荷与排障建议</summary>
                                                <div className="mt-2 space-y-2 text-xs text-text-secondary">
                                                    <div>{getPriorityMeta(item).hint}</div>
                                                    {item.priority === 'urgent' ? (
                                                        <div className="flex flex-wrap gap-2">
                                                            <Link href="/admin/tools" className="text-danger underline">先排查工具</Link>
                                                            <Link href="/admin/cache" className="text-text-secondary underline">查看缓存状态</Link>
                                                        </div>
                                                    ) : null}
                                                    {item.payload ? (
                                                        <pre className="whitespace-pre-wrap break-all rounded-lg border border-glass-border bg-black/10 p-2 text-[10px] text-text-muted">{item.payload}</pre>
                                                    ) : null}
                                                </div>
                                            </details>
                                        </div>
                                    );
                                },
                            },
                        ]}
                        mobileCardRender={(row) => {
                            const item = row as unknown as DeadLetterItem;
                            const priority = getPriorityMeta(item);
                            return (
                                <div className="space-y-3">
                                    <div className="flex items-start justify-between gap-3">
                                        <div className="space-y-1">
                                            <Badge variant="danger">{item.tool}</Badge>
                                            <div className="text-xs text-text-secondary">
                                                {item.timestampMs != null ? new Date(item.timestampMs).toLocaleString('zh-CN') : item.timestamp}
                                            </div>
                                        </div>
                                        <Badge variant={priority.variant}>{priority.label}</Badge>
                                    </div>
                                    <div className="text-sm text-danger">{item.error}</div>
                                    <div className="text-xs text-text-secondary">{priority.hint}</div>
                                    <div className="flex items-center justify-between gap-3">
                                        <div className="text-xs text-text-secondary">重试 {item.retries} 次</div>
                                        <button
                                            type="button"
                                            onClick={() => handleRetry(item.id)}
                                            disabled={retrying === item.id}
                                            data-testid={`dead-letter-retry-${item.id}`}
                                            className="rounded-lg border border-primary/30 bg-primary/20 px-3 py-1.5 text-xs text-primary disabled:cursor-not-allowed disabled:opacity-50"
                                        >
                                            {retrying === item.id ? '重试中...' : '🔄 重试'}
                                        </button>
                                    </div>
                                    <details className="rounded-lg border border-glass-border bg-white/35 px-3 py-2">
                                        <summary className="cursor-pointer text-xs text-text-secondary">查看载荷与排障建议</summary>
                                        <div className="mt-2 space-y-2 text-xs text-text-secondary">
                                            {item.priority === 'urgent' ? (
                                                <div className="flex flex-wrap gap-2">
                                                    <Link href="/admin/tools" className="text-danger underline">先排查工具</Link>
                                                    <Link href="/admin/cache" className="text-text-secondary underline">查看缓存状态</Link>
                                                </div>
                                            ) : null}
                                            {item.payload ? (
                                                <pre className="whitespace-pre-wrap break-all rounded-lg border border-glass-border bg-black/10 p-2 text-[10px] text-text-muted">{item.payload}</pre>
                                            ) : null}
                                        </div>
                                    </details>
                                </div>
                            );
                        }}
                    />
                </SectionCard>
            )}
            <ConfirmDialog
                open={confirmClearOpen}
                title="确认清空死信队列"
                confirmText={clearApi.isPending ? '清除中...' : '确认清除'}
                danger
                confirmDisabled={clearApi.isPending}
                onCancel={() => setConfirmClearOpen(false)}
                onConfirm={() => {
                    void handleClearAll();
                    setConfirmClearOpen(false);
                }}
            >
                <div className="space-y-2">
                    <div>这会清空当前待处理死信，不适合在仍需排障取证时执行。</div>
                    <div className="text-xs text-text-secondary">
                        当前队列：{summary.total} 条 ｜ 其中需人工处理 {summary.urgent} 条
                    </div>
                </div>
            </ConfirmDialog>
        </PageContainer>
    );
}
