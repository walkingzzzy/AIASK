'use client';

import { useState, useMemo } from 'react';
import Link from 'next/link';
import { PageContainer, SectionCard, Badge } from '@/components/ui';
import { useApiQuery } from '@/hooks/use-api-query';
import { useApiMutation } from '@/hooks/use-api-mutation';
import { apiKeys } from '@/lib/query-keys';

type NotificationType = 'alert' | 'signal' | 'trade' | 'system' | 'news';

type NotificationItem = {
    id: string;
    type: NotificationType;
    level: 'info' | 'warn' | 'error';
    title: string;
    body: string;
    read: boolean;
    createdAt: string;
};

const TYPE_ICONS: Record<string, string> = {
    alert: '⚠️', signal: '📊', trade: '💹', system: '⚙️', news: '📰',
};

const TYPE_LABELS: Record<string, string> = {
    alert: '告警', signal: '信号', trade: '交易', system: '系统', news: '资讯', all: '全部',
};

const TEMPLATE_CARDS = [
    {
        key: 'alert',
        title: '价格/指标提醒',
        description: '当价格突破、均线拐头或指标触发时，优先把通知回流到通知中心。',
        href: '/alerts',
        cta: '去配置告警',
    },
    {
        key: 'signal',
        title: '策略信号通知',
        description: '把策略超市中关注的策略运行结果沉淀成固定消息入口，便于后续批量处理。',
        href: '/strategy-market',
        cta: '去策略超市',
    },
    {
        key: 'trade',
        title: '成交/回执提醒',
        description: '模拟交易的下单、成交和撤单结果适合作为交易类通知模板。',
        href: '/paper-trading',
        cta: '去模拟交易',
    },
    {
        key: 'system',
        title: '系统维护消息',
        description: '把维护、同步和异常告警集中到系统类通知，减少用户漏看。',
        href: '/settings',
        cta: '检查设置',
    },
] as const;

export default function NotificationsPage() {
    const [activeType, setActiveType] = useState<string>('all');
    const [selectedIds, setSelectedIds] = useState<string[]>([]);

    const listQ = useApiQuery<unknown>(`/notifications/list?limit=100`, {
        refetchInterval: 30000,
    });
    const markAllReadApi = useApiMutation<{ markedCount?: number }>({
        invalidates: [[...apiKeys.notifications()]],
        successToast: '通知已全部标记为已读',
    });
    const markReadApi = useApiMutation<{ markedCount?: number }>({
        invalidates: [[...apiKeys.notifications()]],
        successToast: false,
    });
    const deleteApi = useApiMutation<{ deletedCount?: number }>({
        invalidates: [[...apiKeys.notifications()]],
        successToast: '通知已删除',
    });

    const rawItems: NotificationItem[] = useMemo(() => {
        const data = listQ.data as any;
        return data?.items ?? data?.data?.items ?? [];
    }, [listQ.data]);

    const items = useMemo(() => {
        return activeType === 'all' ? rawItems : rawItems.filter((i) => i.type === activeType);
    }, [rawItems, activeType]);

    const unreadCount = rawItems.filter((i) => !i.read).length;
    const actionError = markAllReadApi.error || markReadApi.error || deleteApi.error;
    const selectableIds = items.map((item) => item.id);
    const selectedCount = selectedIds.filter((id) => selectableIds.includes(id)).length;
    const allVisibleSelected = selectableIds.length > 0 && selectableIds.every((id) => selectedIds.includes(id));

    const handleMarkAllRead = async () => {
        try {
            await markAllReadApi.triggerAsync('/notifications/mark-all-read', { method: 'POST' });
            listQ.refetch();
        } catch { /* ignore */ }
    };

    const handleMarkRead = async (ids: string[]) => {
        try {
            await markReadApi.triggerAsync('/notifications/mark-read', { method: 'POST' }, { ids });
            listQ.refetch();
        } catch { /* ignore */ }
    };

    const handleDelete = async (ids: string[]) => {
        try {
            await deleteApi.triggerAsync('/notifications/delete', { method: 'DELETE' }, { ids });
            listQ.refetch();
        } catch { /* ignore */ }
    };

    const toggleSelect = (id: string) => {
        setSelectedIds((prev) => prev.includes(id) ? prev.filter((itemId) => itemId !== id) : [...prev, id]);
    };

    const toggleSelectAllVisible = () => {
        setSelectedIds((prev) => {
            if (allVisibleSelected) return prev.filter((id) => !selectableIds.includes(id));
            return Array.from(new Set([...prev, ...selectableIds]));
        });
    };

    const handleBatchMarkRead = async () => {
        const targetIds = selectedIds.filter((id) => selectableIds.includes(id));
        if (targetIds.length === 0) return;
        await handleMarkRead(targetIds);
        setSelectedIds((prev) => prev.filter((id) => !targetIds.includes(id)));
    };

    const handleBatchDelete = async () => {
        const targetIds = selectedIds.filter((id) => selectableIds.includes(id));
        if (targetIds.length === 0) return;
        await handleDelete(targetIds);
        setSelectedIds((prev) => prev.filter((id) => !targetIds.includes(id)));
    };

    return (
        <PageContainer>
            <div className="flex items-center justify-between mb-4">
                <div>
                    <h1 className="text-lg font-semibold m-0">🔔 通知中心</h1>
                    <p className="mt-1 mb-0 text-xs text-text-secondary">统一查看告警、策略、交易和系统消息。</p>
                </div>
                <div className="flex items-center gap-2">
                    {unreadCount > 0 && (
                        <button
                            onClick={handleMarkAllRead}
                            disabled={markAllReadApi.isPending}
                            className="text-xs px-3 py-1 rounded border border-primary/50 text-primary cursor-pointer hover:bg-primary/10"
                        >
                            {markAllReadApi.isPending ? '处理中...' : `全部已读 (${unreadCount})`}
                        </button>
                    )}
                </div>
            </div>
            {actionError ? <p className="text-sm text-danger mb-3">{actionError}</p> : null}

            {/* Type Filter Tabs */}
            <div className="flex gap-2 mb-4 flex-wrap">
                {['all', 'alert', 'signal', 'trade', 'system', 'news'].map((t) => {
                    const count = t === 'all' ? rawItems.length : rawItems.filter((i) => i.type === t).length;
                    return (
                        <button
                            key={t}
                            onClick={() => {
                                setActiveType(t);
                                setSelectedIds([]);
                            }}
                            className={`px-3 py-1.5 rounded-full text-xs font-medium cursor-pointer transition-all ${activeType === t
                                    ? 'bg-primary/20 text-primary border border-primary/40'
                                    : 'bg-surface border border-glass-border text-text-secondary hover:bg-white/10'
                                }`}
                        >
                            {TYPE_ICONS[t] || '📋'} {TYPE_LABELS[t] || t} ({count})
                        </button>
                    );
                })}
            </div>

            <SectionCard className="mb-4">
                <div className="flex items-start justify-between gap-3 flex-wrap">
                    <div>
                        <div className="text-sm font-medium text-text-primary">通知模板与批量处理</div>
                        <p className="mt-1 mb-0 text-xs text-text-secondary">
                            先配置上游通知模板，再按分类或选中项做批量已读 / 删除，避免只剩单条处理路径。
                        </p>
                    </div>
                    {items.length > 0 ? (
                        <div className="flex items-center gap-2 flex-wrap text-xs">
                            <button
                                type="button"
                                onClick={toggleSelectAllVisible}
                                className="rounded-full border border-glass-border px-3 py-1 text-text-secondary"
                            >
                                {allVisibleSelected ? '取消全选当前筛选' : '选中当前筛选'}
                            </button>
                            <button
                                type="button"
                                disabled={selectedCount === 0 || markReadApi.isPending}
                                onClick={handleBatchMarkRead}
                                className="rounded-full border border-primary/50 px-3 py-1 text-primary disabled:opacity-50"
                            >
                                批量已读 ({selectedCount})
                            </button>
                            <button
                                type="button"
                                disabled={selectedCount === 0 || deleteApi.isPending}
                                onClick={handleBatchDelete}
                                className="rounded-full border border-danger/40 px-3 py-1 text-danger disabled:opacity-50"
                            >
                                批量删除 ({selectedCount})
                            </button>
                        </div>
                    ) : null}
                </div>
                <div className="mt-4 grid gap-3 md:grid-cols-2 xl:grid-cols-4">
                    {TEMPLATE_CARDS.map((card) => (
                        <div key={card.key} className="rounded-xl border border-glass-border bg-surface-alt/40 p-3">
                            <div className="text-sm font-medium text-text-primary">{card.title}</div>
                            <p className="mt-1 min-h-[54px] text-xs leading-5 text-text-secondary">{card.description}</p>
                            <Link href={card.href} className="text-xs text-primary no-underline hover:underline">
                                {card.cta} →
                            </Link>
                        </div>
                    ))}
                </div>
            </SectionCard>

            {/* Notification List */}
            {items.length === 0 ? (
                <SectionCard>
                    <div className="text-center py-12 text-text-secondary text-sm">
                        <p className="m-0">暂无{activeType === 'all' ? '' : TYPE_LABELS[activeType]}通知</p>
                        <p className="mt-2 mb-0 text-xs">可以先去告警中心、策略超市或模拟交易页面创建上游触发源。</p>
                        <div className="mt-3 flex items-center justify-center gap-2 flex-wrap">
                            <Link href="/alerts" className="rounded-full border border-glass-border px-3 py-1 text-xs text-text-secondary no-underline">去告警中心</Link>
                            <Link href="/strategy-market" className="rounded-full border border-glass-border px-3 py-1 text-xs text-text-secondary no-underline">去策略超市</Link>
                            <Link href="/paper-trading" className="rounded-full border border-glass-border px-3 py-1 text-xs text-text-secondary no-underline">去模拟交易</Link>
                        </div>
                        <div className="mt-3 text-[11px] text-text-secondary/70">
                            常见触发源：价格/技术指标告警、策略工厂运行、模拟交易成交、系统维护通知
                        </div>
                    </div>
                </SectionCard>
            ) : (
                <div className="space-y-2">
                    {items.map((item) => (
                        <SectionCard
                            key={item.id}
                            className={`hover:border-primary/30 transition-all ${selectedIds.includes(item.id) ? 'ring-1 ring-primary/40' : ''} ${!item.read ? 'border-l-2 border-l-primary' : ''}`}
                        >
                            <div className="flex items-start gap-3">
                                <label className="mt-0.5 flex items-center">
                                    <input
                                        type="checkbox"
                                        checked={selectedIds.includes(item.id)}
                                        onChange={() => toggleSelect(item.id)}
                                        aria-label={`选择通知 ${item.title}`}
                                    />
                                </label>
                                <span className="text-lg mt-0.5">{TYPE_ICONS[item.type] || '📌'}</span>
                                <div className="flex-1 min-w-0">
                                    <div className="flex items-center gap-2 mb-1">
                                        <span className={`font-medium text-sm ${!item.read ? '' : 'text-text-secondary'}`}>
                                            {item.title}
                                        </span>
                                        <Badge variant={item.level === 'error' ? 'danger' : item.level === 'warn' ? 'warning' : 'info'}>
                                            {item.level}
                                        </Badge>
                                        {!item.read && (
                                            <span className="w-2 h-2 rounded-full bg-primary shrink-0" />
                                        )}
                                    </div>
                                    <p className="text-sm text-text-secondary">{item.body}</p>
                                    <p className="text-xs text-text-secondary/60 mt-1">
                                        {new Date(item.createdAt).toLocaleString('zh-CN')}
                                    </p>
                                </div>
                                <div className="flex items-center gap-1 shrink-0">
                                    {!item.read && (
                                        <button
                                            onClick={() => handleMarkRead([item.id])}
                                            disabled={markReadApi.isPending}
                                            className="text-xs text-primary cursor-pointer hover:underline"
                                        >
                                            已读
                                        </button>
                                    )}
                                    <button
                                        onClick={() => handleDelete([item.id])}
                                        disabled={deleteApi.isPending}
                                        className="text-xs text-danger/70 cursor-pointer hover:text-danger"
                                    >
                                        删除
                                    </button>
                                </div>
                            </div>
                        </SectionCard>
                    ))}
                </div>
            )}
        </PageContainer>
    );
}
