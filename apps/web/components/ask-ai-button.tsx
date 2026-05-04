'use client';

import { type ButtonHTMLAttributes, type ReactNode } from 'react';
import { trackBehaviorEvent } from '@/lib/behavior-tracker';
import { useCopilotStore } from '@/store/copilot-store';

export type AskAiButtonProps = Omit<ButtonHTMLAttributes<HTMLButtonElement>, 'onClick'> & {
  /** 预填入 Copilot 的提问文本，不传则使用 "分析当前内容" */
  prompt?: string;
  /** 注入的股票代码（会拼入提示词） */
  stockCode?: string;
  /** 注入的数据摘要 */
  summary?: string;
  /** 额外 raw 上下文，JSON 序列化后附到提问末尾 */
  raw?: Record<string, unknown>;
  pageKey?: string;
  title?: string;
  objectType?: string;
  objectId?: string;
  resultType?: string;
  evidenceSummary?: string[];
  selectedCode?: string;
  accountId?: string;
  strategyId?: string;
  workspaceId?: string;
  /** 按钮文案 */
  label?: ReactNode;
  /** 是否仅展示图标（图标模式下不显示文字） */
  iconOnly?: boolean;
};

/**
 * AskAiButton
 *
 * 可放置在任意表格行、卡片、详情区，点击后：
 * 1. 打开右侧 CopilotDock
 * 2. 将局部对象（prompt + 上下文）注入 Dock 输入框
 *
 * 用法示例：
 * ```tsx
 * <AskAiButton stockCode="600519" summary="茅台，估值偏高" prompt="请分析这只股票的买入时机" />
 * ```
 */
export function AskAiButton({
  prompt,
  stockCode,
  summary,
  raw,
  pageKey,
  title,
  objectType,
  objectId,
  resultType,
  evidenceSummary,
  selectedCode,
  accountId,
  strategyId,
  workspaceId,
  label,
  iconOnly = false,
  className = '',
  ...rest
}: AskAiButtonProps) {
  const setDockOpen = useCopilotStore((s) => s.setDockOpen);
  const setPendingInject = useCopilotStore((s) => s.setPendingInject);
  const pageContext = useCopilotStore((s) => s.pageContext);

  const handleClick = () => {
    const currentPath = typeof window !== 'undefined' ? window.location.pathname : '/';
    const parts: string[] = [];
    if (prompt) {
      parts.push(prompt);
    } else if (stockCode) {
      parts.push(`请帮我分析 ${stockCode}`);
    } else {
      parts.push('请分析当前内容');
    }
    if (summary && !prompt) {
      parts.push(`（${summary}）`);
    }

    const resolvedRaw = {
      ...(pageContext?.raw ?? {}),
      ...(raw ?? {}),
      ...(selectedCode ? { selectedCode } : {}),
      ...(accountId ? { accountId } : {}),
      ...(strategyId ? { strategyId } : {}),
      ...(workspaceId ? { workspaceId } : {}),
      route: currentPath,
    };

    setPendingInject({
      prompt: parts.join(''),
      contextPatch: {
        pageKey: pageKey ?? pageContext?.pageKey ?? 'ask-ai-button',
        title: title ?? pageContext?.title ?? '局部对象分析',
        ...(stockCode ? { stockCode } : {}),
        ...(selectedCode ? { selectedCode } : stockCode ? { selectedCode: stockCode } : {}),
        ...(summary ? { summary } : {}),
        ...(objectType ? { objectType } : {}),
        ...(objectId ? { objectId } : {}),
        ...(resultType ? { resultType } : {}),
        ...(accountId ? { accountId } : {}),
        ...(strategyId ? { strategyId } : {}),
        ...(workspaceId ? { workspaceId } : {}),
        ...(evidenceSummary?.length ? { evidenceSummary } : pageContext?.evidenceSummary?.length ? { evidenceSummary: pageContext.evidenceSummary } : {}),
        raw: resolvedRaw,
      },
    });
    trackBehaviorEvent({
      pageKey: 'ask-ai-button',
      route: currentPath,
      eventType: 'ask_ai_inject',
      targetType: 'button',
      targetLabel: typeof label === 'string' ? label : stockCode ? `Ask AI ${stockCode}` : 'Ask AI',
      payload: {
        stockCode,
        summary,
        pageKey: pageKey ?? pageContext?.pageKey,
        objectType,
        objectId,
        selectedCode,
        accountId,
        strategyId,
        workspaceId,
      },
      source: 'ask-ai-button',
    });
    setDockOpen(true);
  };

  const defaultLabel = iconOnly ? '✦' : (label ?? 'Ask AI');
  const baseClass = [
    'inline-flex items-center gap-1 cursor-pointer transition-colors',
    'text-xs font-medium rounded-full border border-primary/40 px-2 py-0.5',
    'text-primary hover:bg-primary/10 hover:border-primary/70',
    className,
  ].join(' ');

  return (
    <button type="button" className={baseClass} onClick={handleClick} {...rest}>
      <span aria-hidden="true">✦</span>
      {!iconOnly ? <span>{defaultLabel === '✦' ? 'Ask AI' : defaultLabel}</span> : null}
    </button>
  );
}
