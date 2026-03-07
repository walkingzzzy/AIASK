'use client';

import { useCallback, useEffect, useState } from 'react';
import { useAlertSubscription } from '@/lib/ws';

/* ── Toast 类型 ── */

export type ToastItem = {
    id: string;
    message: string;
    level: 'info' | 'warn' | 'error';
    ts: string;
};

/* ── AlertToastProvider: 全局告警 Toast 弹窗组件 ── */

const TOAST_MAX = 5;
const TOAST_TTL = 8000; // auto-dismiss after 8 seconds

export function AlertToastProvider({ userId }: { userId?: string }) {
    const [toasts, setToasts] = useState<ToastItem[]>([]);

    const addToast = useCallback((item: Omit<ToastItem, 'id'>) => {
        const id = `${Date.now()}-${Math.random().toString(36).slice(2, 6)}`;
        setToasts((prev) => [{ ...item, id }, ...prev].slice(0, TOAST_MAX));
        // Auto-dismiss
        setTimeout(() => {
            setToasts((prev) => prev.filter((t) => t.id !== id));
        }, TOAST_TTL);
    }, []);

    const dismiss = useCallback((id: string) => {
        setToasts((prev) => prev.filter((t) => t.id !== id));
    }, []);

    // Subscribe to WS alert channel
    useAlertSubscription({
        userId,
        onAlert: (data) => {
            addToast({
                message: data.message || `告警触发: ${data.code || ''} ${data.indicator || ''}`,
                level: data.level || 'warn',
                ts: data.ts || new Date().toISOString(),
            });
        },
        onWarn: (data) => {
            addToast({
                message: data.message || '系统警告',
                level: data.level || 'warn',
                ts: data.ts || new Date().toISOString(),
            });
        },
    });

    if (toasts.length === 0) return null;

    return (
        <div className="fixed top-14 right-4 z-50 flex flex-col gap-2 max-w-sm" role="alert" aria-live="polite">
            {toasts.map((t) => (
                <div
                    key={t.id}
                    className={`flex items-start gap-2 px-4 py-3 rounded-lg shadow-lg border backdrop-blur-sm animate-slide-in ${t.level === 'error'
                            ? 'bg-red-500/15 border-red-500/30 text-red-400'
                            : t.level === 'warn'
                                ? 'bg-amber-500/15 border-amber-500/30 text-amber-400'
                                : 'bg-blue-500/15 border-blue-500/30 text-blue-400'
                        }`}
                >
                    <span className="text-lg mt-0.5">
                        {t.level === 'error' ? '🔴' : t.level === 'warn' ? '⚠️' : 'ℹ️'}
                    </span>
                    <div className="flex-1 min-w-0">
                        <p className="text-sm font-medium break-words">{t.message}</p>
                        <p className="text-xs opacity-60 mt-0.5">{new Date(t.ts).toLocaleTimeString()}</p>
                    </div>
                    <button
                        onClick={() => dismiss(t.id)}
                        className="text-xs opacity-50 hover:opacity-100 cursor-pointer shrink-0"
                        aria-label="关闭"
                    >
                        ✕
                    </button>
                </div>
            ))}
        </div>
    );
}
