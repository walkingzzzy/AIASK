'use client';

import { useState } from 'react';
import { createPortal } from 'react-dom';
import { useAuthStore } from '@/store/auth-store';
import { useHydrated } from '@/hooks/use-hydrated';

const KEY = 'onboarding-done';

const CHECKLIST = [
  { id: 'market', title: '查看行情', description: '打开行情页，选定标的，看 K 线和盘口。', href: '/market' },
  { id: 'strategy', title: '浏览策略', description: '策略超市里筛选、对比、加入组合。', href: '/strategy-market' },
  { id: 'watchlist', title: '建立自选', description: '把关心的股票加入自选，持续跟踪。', href: '/watchlist' },
  { id: 'llm', title: '配置 LLM Key', description: '在设置中心完成 AI 接口配置，解锁 AI 功能。', href: '/settings' },
];

export function Onboarding() {
  const user = useAuthStore((s) => s.user);
  const hydrated = useHydrated();
  const [dismissed, setDismissed] = useState(false);
  const [minimized, setMinimized] = useState(false);
  const completed = hydrated ? window.localStorage.getItem(KEY) === '1' : true;
  const open = hydrated && Boolean(user) && !dismissed && !completed;

  if (!open) return null;

  const close = () => {
    window.localStorage.setItem(KEY, '1');
    setDismissed(true);
  };

  return createPortal(
    <div className="pointer-events-auto fixed bottom-[calc(var(--mobile-bottom-nav-height)+12px)] right-4 z-60 sm:bottom-6 sm:right-6">
      {minimized ? (
        <button
          type="button"
          onClick={() => setMinimized(false)}
          className="rounded-full border border-border bg-surface px-4 py-2.5 text-sm font-medium text-text-primary shadow-lg"
        >
          快速上手 ↑
        </button>
      ) : (
        <div className="w-[320px] rounded-[22px] border border-border bg-surface p-4 shadow-xl sm:w-[360px]">
          <div className="mb-3 flex items-center justify-between">
            <div className="eyebrow">快速上手</div>
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={() => setMinimized(true)}
                className="rounded-full border border-border px-2.5 py-1 text-xs text-text-secondary"
              >
                收起
              </button>
              <button
                type="button"
                onClick={close}
                className="rounded-full border border-border px-2.5 py-1 text-xs text-text-secondary"
              >
                完成
              </button>
            </div>
          </div>
          <p className="mb-3 text-xs leading-5 text-text-secondary">按需完成以下步骤，随时可以关闭。</p>
          <div className="grid gap-2">
            {CHECKLIST.map((item) => (
              <a
                key={item.id}
                href={item.href}
                className="flex gap-3 rounded-[16px] border border-border bg-surface-alt/60 px-3 py-2.5 no-underline transition hover:border-primary/20 hover:bg-primary/5"
              >
                <span className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full border border-border bg-surface text-[10px] font-bold text-text-muted">
                  →
                </span>
                <div>
                  <div className="text-sm font-medium text-text-primary">{item.title}</div>
                  <div className="mt-0.5 text-xs leading-4 text-text-secondary">{item.description}</div>
                </div>
              </a>
            ))}
          </div>
        </div>
      )}
    </div>,
    document.body,
  );
}
