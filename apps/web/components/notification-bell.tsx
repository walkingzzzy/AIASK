'use client';

import { useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import { useApiQuery } from '@/hooks/use-api-query';
import { useApiMutation } from '@/hooks/use-api-mutation';
import { useBffAvailability } from '@/lib/bff-availability';
import { hasLoggedInHint } from '@/lib/auth';
import { apiKeys } from '@/lib/query-keys';
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

function readRecord(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    return {};
  }
  return value as Record<string, unknown>;
}

export function NotificationBell() {
  const [open, setOpen] = useState(false);
  const [pendingUnreadEvents, setPendingUnreadEvents] = useState<number[]>([]);
  const [markAllReadAt, setMarkAllReadAt] = useState<number | null>(null);
  const [pageVisible, setPageVisible] = useState(() =>
    typeof document === 'undefined' ? true : document.visibilityState === 'visible',
  );
  const notificationsEnabled = hasLoggedInHint();
  const bffAvailability = useBffAvailability();

  useEffect(() => {
    if (typeof document === 'undefined') return;

    const handleVisibilityChange = () => {
      setPageVisible(document.visibilityState === 'visible');
    };

    document.addEventListener('visibilitychange', handleVisibilityChange);
    return () => document.removeEventListener('visibilitychange', handleVisibilityChange);
  }, []);

  const pollingEnabled = notificationsEnabled && pageVisible && bffAvailability.reachable;

  // Fetch unread count
  const unreadQ = useApiQuery<{ count?: number }>(pollingEnabled ? '/notifications/unread-count' : null, {
    enabled: pollingEnabled,
    refetchInterval: pollingEnabled ? 30000 : false,
    staleTime: 30000,
    redirectOnUnauthorized: false,
    nonFatal: true,
    fallbackData: { count: 0 },
  });
  const recentQ = useApiQuery<unknown>(
    notificationsEnabled && open && pageVisible && bffAvailability.reachable ? '/notifications/list?limit=10' : null,
    {
      enabled: notificationsEnabled && open && pageVisible && bffAvailability.reachable,
      refetchInterval: open && pageVisible ? 30000 : false,
      staleTime: 30000,
      redirectOnUnauthorized: false,
      nonFatal: true,
      fallbackData: { items: [] },
    },
  );
  const markAllReadApi = useApiMutation<{ markedCount?: number }>({
    invalidates: [[...apiKeys.notifications()]],
    successToast: false,
  });

  const unreadRoot = readRecord(unreadQ.data);
  const unreadData = readRecord(unreadRoot.data);
  const serverUnread = Number(unreadRoot.count ?? unreadData.count ?? 0);
  const snapshotAt = unreadQ.dataUpdatedAt ?? 0;
  const unreadSinceSnapshot = pendingUnreadEvents.filter(
    (ts) => ts > snapshotAt && (!markAllReadAt || ts > markAllReadAt),
  ).length;
  const unread = markAllReadAt && markAllReadAt > snapshotAt ? unreadSinceSnapshot : serverUnread + unreadSinceSnapshot;

  // Increment unread on WS alert only when notification panel is open,
  // so pages that don't need realtime updates won't always establish a WS connection.
  useAlertSubscription({
    enabled: notificationsEnabled && open && pageVisible && bffAvailability.reachable,
    onAlert: () => setPendingUnreadEvents((prev) => [...prev, Date.now()]),
    onWarn: () => setPendingUnreadEvents((prev) => [...prev, Date.now()]),
  });

  const items = useMemo(() => {
    const root = readRecord(recentQ.data);
    const dataRecord = readRecord(root.data);
    const data = Array.isArray(root.items) ? root.items : Array.isArray(dataRecord.items) ? dataRecord.items : [];
    if (!Array.isArray(data)) return [] as NotificationItem[];
    return data.map((item) => {
      const record = readRecord(item);
      const normalized: NotificationItem = {
        id: String(record.id ?? ''),
        type: ['alert', 'signal', 'trade', 'system', 'news'].includes(String(record.type))
          ? (String(record.type) as NotificationItem['type'])
          : 'system',
        level: ['info', 'warn', 'error'].includes(String(record.level))
          ? (String(record.level) as NotificationItem['level'])
          : 'info',
        title: String(record.title ?? ''),
        body: String(record.body ?? ''),
        read: record.read === true,
        createdAt: String(record.createdAt ?? ''),
      };
      if (!markAllReadAt) return normalized;
      const createdAt = Date.parse(String(normalized.createdAt ?? ''));
      if (Number.isNaN(createdAt) || createdAt <= markAllReadAt) {
        return { ...normalized, read: true };
      }
      return normalized;
    });
  }, [markAllReadAt, recentQ.data]);

  const handleOpen = () => {
    setOpen(!open);
  };

  const handleMarkAllRead = async () => {
    try {
      await markAllReadApi.triggerAsync('/notifications/mark-all-read', { method: 'POST' });
      setMarkAllReadAt(Date.now());
    } catch {
      /* ignore */
    }
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
          <span className="absolute -top-1 -right-1 min-w-4 h-4 flex items-center justify-center bg-danger text-white text-[10px] font-bold rounded-full px-1">
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
                    disabled={markAllReadApi.isPending}
                    className="text-xs text-primary cursor-pointer hover:underline"
                  >
                    {markAllReadApi.isPending ? '处理中...' : '全部已读'}
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
              <div className="px-4 py-8 text-center text-text-secondary text-sm">暂无通知</div>
            ) : (
              <div>
                {items.map((item) => (
                  <div
                    key={item.id}
                    className={`px-3 py-2 border-b border-glass-border/50 hover:bg-white/5 ${
                      !item.read ? 'bg-primary/5' : ''
                    }`}
                  >
                    <div className="flex items-start gap-2">
                      <span className="text-sm mt-0.5">{TYPE_ICONS[item.type] || '📌'}</span>
                      <div className="flex-1 min-w-0">
                        <p
                          className={`text-sm font-medium truncate ${!item.read ? 'text-text-primary' : 'text-text-secondary'}`}
                        >
                          {item.title}
                        </p>
                        <p className="text-xs text-text-secondary truncate">{item.body}</p>
                        <p className="text-[10px] text-text-secondary/60 mt-0.5">
                          {new Date(item.createdAt).toLocaleString('zh-CN', {
                            month: 'numeric',
                            day: 'numeric',
                            hour: '2-digit',
                            minute: '2-digit',
                          })}
                        </p>
                      </div>
                      {!item.read && <span className="w-2 h-2 rounded-full bg-primary mt-1.5 shrink-0" />}
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
