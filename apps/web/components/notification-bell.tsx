'use client';

import { useState, useEffect, useCallback } from 'react';
import Link from 'next/link';
import { useApiQuery } from '@/hooks/use-api-query';
import { BFF_BASE } from '@/lib/api';
import { useAlertSubscription } from '@/lib/ws';

type NotificationItem = {
    id: string;
    type: 'alert' | 'signal' | 'trade' | 'system' | 'news';
    level: 'info' | 'warn' | 'error';
    title: string;
    body: string;
    read: boolean;
    createdAt: string;
};

const TYPE_ICONS: Record<string, string> = {
    alert: '⚠️',
    signal: '📊',
    trade: '💹',
    system: '⚙️',
    news: '📰',
};

const LEVEL_COLORS: Record<string, string> = {
    error: 'text-red-400 bg-red-500/10 border-red-500/20',
    warn: 'text-amber-400 bg-amber-500/10 border-amber-500/20',
    info: 'text-blue-400 bg-blue-500/10 border-blue-500/20',
};

export function NotificationBell() {
    const [open, setOpen] = useState(false);
    const [items, setItems] = useState<NotificationItem[]>([]);
    const [unread, setUnread] = useState(0);

    // Fetch unread count
    const unreadQ = useApiQuery<{ count?: number }>('/notifications/unread-count', {
        refetchInterval: 30000,
    });

    useEffect(() => {
        const count = Number((unreadQ.data as any)?.count ?? (unreadQ.data as any)?.data?.count ?? 0);
        setUnread(count);
    }, [unreadQ.data]);

    // Increment unread on WS alert
    useAlertSubscription({
        onAlert: () => setUnread((n) => n + 1),
        onWarn: () => setUnread((n) => n + 1),
    });

    const fetchRecent = useCallback(async () => {
        try {
            const res = await fetch(`${BFF_BASE}/notifications/list?limit=10`, { credentials: 'include' });
            if (!res.ok) return;
            const json = await res.json();
            const data = json?.data?.items ?? json?.items ?? [];
            setItems(data);
        } catch { /* ignore */ }
    }, []);

    const handleOpen = () => {
        setOpen(!open);
        if (!open) fetchRecent();
    };

    const handleMarkAllRead = async () => {
        try {
            await fetch(`${BFF_BASE}/notifications/mark-all-read`, {
                method: 'POST',
                credentials: 'include',
                headers: { 'Content-Type': 'application/json' },
            });
            setUnread(0);
            setItems((prev) => prev.map((i) => ({ ...i, read: true })));
        } catch { /* ignore */ }
    };

    return (
        <div className="relative">
            <button
                onClick={handleOpen}
                className="relative text-lg cursor-pointer p-1 hover:bg-white/10 rounded"
                aria-label="通知"
            >
                🔔
                {unread > 0 && (
                    <span className="absolute -top-1 -right-1 min-w-[16px] h-4 flex items-center justify-center bg-danger text-white text-[10px] font-bold rounded-full px-1">
                        {unread > 99 ? '99+' : unread}
                    </span>
                )}
            </button>

            {open && (
                <>
                    <div className="fixed inset-0 z-40" onClick={() => setOpen(false)} />
                    <div className="absolute right-0 top-full mt-2 w-80 max-h-96 overflow-y-auto glass-strong rounded-lg border border-glass-border shadow-xl z-50">
                        <div className="flex items-center justify-between px-3 py-2 border-b border-glass-border">
                            <span className="font-semibold text-sm">通知中心</span>
                            <div className="flex items-center gap-2">
                                {unread > 0 && (
                                    <button
                                        onClick={handleMarkAllRead}
                                        className="text-xs text-primary cursor-pointer hover:underline"
                                    >
                                        全部已读
                                    </button>
                                )}
                                <Link
                                    href="/notifications"
                                    onClick={() => setOpen(false)}
                                    className="text-xs text-primary no-underline hover:underline"
                                >
                                    查看全部
                                </Link>
                            </div>
                        </div>

                        {items.length === 0 ? (
                            <div className="px-4 py-8 text-center text-text-secondary text-sm">
                                暂无通知
                            </div>
                        ) : (
                            <div>
                                {items.map((item) => (
                                    <div
                                        key={item.id}
                                        className={`px-3 py-2 border-b border-glass-border/50 hover:bg-white/5 ${!item.read ? 'bg-primary/5' : ''
                                            }`}
                                    >
                                        <div className="flex items-start gap-2">
                                            <span className="text-sm mt-0.5">{TYPE_ICONS[item.type] || '📌'}</span>
                                            <div className="flex-1 min-w-0">
                                                <p className={`text-sm font-medium truncate ${!item.read ? 'text-text-primary' : 'text-text-secondary'}`}>
                                                    {item.title}
                                                </p>
                                                <p className="text-xs text-text-secondary truncate">{item.body}</p>
                                                <p className="text-[10px] text-text-secondary/60 mt-0.5">
                                                    {new Date(item.createdAt).toLocaleString('zh-CN', { month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit' })}
                                                </p>
                                            </div>
                                            {!item.read && (
                                                <span className="w-2 h-2 rounded-full bg-primary mt-1.5 shrink-0" />
                                            )}
                                        </div>
                                    </div>
                                ))}
                            </div>
                        )}
                    </div>
                </>
            )}
        </div>
    );
}
