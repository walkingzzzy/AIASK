'use client';

import { useState, useMemo } from 'react';
import { PageContainer, SectionCard, Badge } from '@/components/ui';
import { useApiQuery } from '@/hooks/use-api-query';
import { BFF_BASE } from '@/lib/api';

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

export default function NotificationsPage() {
    const [activeType, setActiveType] = useState<string>('all');

    const listQ = useApiQuery<unknown>(`/notifications/list?limit=100`, {
        refetchInterval: 30000,
    });

    const rawItems: NotificationItem[] = useMemo(() => {
        const data = listQ.data as any;
        return data?.items ?? data?.data?.items ?? [];
    }, [listQ.data]);

    const items = useMemo(() => {
        return activeType === 'all' ? rawItems : rawItems.filter((i) => i.type === activeType);
    }, [rawItems, activeType]);

    const unreadCount = rawItems.filter((i) => !i.read).length;

    const handleMarkAllRead = async () => {
        try {
            await fetch(`${BFF_BASE}/notifications/mark-all-read`, {
                method: 'POST', credentials: 'include',
                headers: { 'Content-Type': 'application/json' },
            });
            listQ.refetch();
        } catch { /* ignore */ }
    };

    const handleMarkRead = async (ids: string[]) => {
        try {
            await fetch(`${BFF_BASE}/notifications/mark-read`, {
                method: 'POST', credentials: 'include',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ ids }),
            });
            listQ.refetch();
        } catch { /* ignore */ }
    };

    const handleDelete = async (ids: string[]) => {
        try {
            await fetch(`${BFF_BASE}/notifications/delete`, {
                method: 'DELETE', credentials: 'include',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ ids }),
            });
            listQ.refetch();
        } catch { /* ignore */ }
    };

    return (
        <PageContainer>
            <div className="flex items-center justify-between mb-4">
                <h2 className="text-lg font-semibold">🔔 通知中心</h2>
                <div className="flex items-center gap-2">
                    {unreadCount > 0 && (
                        <button
                            onClick={handleMarkAllRead}
                            className="text-xs px-3 py-1 rounded border border-primary/50 text-primary cursor-pointer hover:bg-primary/10"
                        >
                            全部已读 ({unreadCount})
                        </button>
                    )}
                </div>
            </div>

            {/* Type Filter Tabs */}
            <div className="flex gap-2 mb-4 flex-wrap">
                {['all', 'alert', 'signal', 'trade', 'system', 'news'].map((t) => {
                    const count = t === 'all' ? rawItems.length : rawItems.filter((i) => i.type === t).length;
                    return (
                        <button
                            key={t}
                            onClick={() => setActiveType(t)}
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

            {/* Notification List */}
            {items.length === 0 ? (
                <SectionCard>
                    <div className="text-center py-12 text-text-secondary text-sm">
                        暂无{activeType === 'all' ? '' : TYPE_LABELS[activeType]}通知
                    </div>
                </SectionCard>
            ) : (
                <div className="space-y-2">
                    {items.map((item) => (
                        <SectionCard
                            key={item.id}
                            className={`hover:border-primary/30 transition-all ${!item.read ? 'border-l-2 border-l-primary' : ''}`}
                        >
                            <div className="flex items-start gap-3">
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
                                            className="text-xs text-primary cursor-pointer hover:underline"
                                        >
                                            已读
                                        </button>
                                    )}
                                    <button
                                        onClick={() => handleDelete([item.id])}
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
