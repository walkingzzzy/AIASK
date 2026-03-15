'use client';

import { useState } from 'react';
import { createPortal } from 'react-dom';
import { useAuthStore } from '@/store/auth-store';
import { useHydrated } from '@/hooks/use-hydrated';

const KEY = 'onboarding-done';
const STEPS = [
  { target: '[data-tour="dashboard"]', title: '欢迎来到 AIASK', content: '这里是你的个人首页，优先展示资产、自选、告警和市场快讯。' },
  { target: '[data-tour="chat"]', title: 'AI 对话', content: '你可以在这里和 AI 连续对话，分析股票、板块和策略。' },
  { target: '[data-tour="watchlist"]', title: '自选股', content: '把你关心的股票加入自选，后续就能持续跟踪行情和异动。' },
  { target: '[data-tour="paper-trading"]', title: '模拟交易', content: '先用模拟盘练手，观察策略表现和持仓变化。' },
  { target: '[data-tour="settings"]', title: '设置中心', content: '如果还没配置 LLM Key，建议先到设置中心完成配置。' },
];

export function Onboarding() {
  const user = useAuthStore((s) => s.user);
  const hydrated = useHydrated();
  const [dismissed, setDismissed] = useState(false);
  const [step, setStep] = useState(0);
  const completed = hydrated ? window.localStorage.getItem(KEY) === '1' : true;
  const open = hydrated && Boolean(user) && !dismissed && !completed;

  if (!open) return null;

  const current = STEPS[step];
  const target = document.querySelector(current.target) as HTMLElement | null;
  const rect = target?.getBoundingClientRect();

  const close = () => {
    window.localStorage.setItem(KEY, '1');
    setDismissed(true);
  };
  const next = () => {
    if (step >= STEPS.length - 1) {
      close();
      return;
    }
    setStep((prev) => prev + 1);
  };

  return createPortal(
    <div className="fixed inset-0 z-[80]">
      <div className="absolute inset-0 bg-black/55" />
      {rect ? (
        <div
          className="absolute rounded-xl border-2 border-primary shadow-[0_0_0_9999px_rgba(0,0,0,0.35)] pointer-events-none"
          style={{ top: rect.top - 8, left: rect.left - 8, width: rect.width + 16, height: rect.height + 16 }}
        />
      ) : null}
      <div className="absolute inset-x-4 bottom-6 sm:inset-x-auto sm:right-6 sm:bottom-6 sm:w-[360px] rounded-2xl border border-glass-border bg-background/95 backdrop-blur p-4 shadow-2xl">
        <div className="text-xs text-text-secondary mb-2">引导 {step + 1} / {STEPS.length}</div>
        <div className="text-base font-semibold mb-2">{current.title}</div>
        <div className="text-sm text-text-secondary leading-6 mb-4">{current.content}</div>
        <div className="flex items-center justify-between gap-3">
          <button type="button" onClick={close} className="px-3 py-2 text-sm rounded border border-glass-border cursor-pointer">跳过</button>
          <button type="button" onClick={next} className="px-3 py-2 text-sm rounded bg-primary text-white cursor-pointer">{step === STEPS.length - 1 ? '完成' : '下一步'}</button>
        </div>
      </div>
    </div>,
    document.body,
  );
}
