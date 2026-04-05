'use client';

import Link from 'next/link';
import { AskAiButton } from '@/components/ask-ai-button';
import { Badge } from '@/components/ui';
import { fmtNum, fmtPct } from '@/lib/data-utils';
import {
  primaryRoundButtonCls,
  secondaryRoundButtonCls,
} from './strategy-market-panel-styles';

type CapabilityBadgeItem = {
  key: string;
  label: string;
  enabled: boolean;
};

type StrategyMarketHeroSectionProps = {
  from: string | null;
  task: string | null;
  capabilityBadges: CapabilityBadgeItem[];
  strategyCount: number;
  enabledCapabilityCount: number;
  bestAnnualReturn: number | null;
  bestSharpe: number | null;
  runFactoryPending: boolean;
  runFactoryError: string | null;
  cartItemsCount: number;
  showFactoryDetails: boolean;
  onRunFactory: () => void;
  onToggleCart: () => void;
  onToggleFactoryDetails: () => void;
};

export function StrategyMarketHeroSection({
  from,
  task,
  capabilityBadges,
  strategyCount,
  enabledCapabilityCount,
  bestAnnualReturn,
  bestSharpe,
  runFactoryPending,
  runFactoryError,
  cartItemsCount,
  showFactoryDetails,
  onRunFactory,
  onToggleCart,
  onToggleFactoryDetails,
}: StrategyMarketHeroSectionProps) {
  return (
    <section className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_clamp(280px,25vw,380px)]">
      <div className="page-hero p-6 sm:p-7">
        <div className="eyebrow">Strategy Workspace</div>
        <h1 className="mt-3">先看筛选结果，再决定订阅、组合和工厂动作。</h1>
        <p className="page-lead mb-0 mt-3">
          策略页首屏改成两层结构：上层只保留工厂摘要与精选候选，下层用表格完成对比和筛选。工厂运行态默认下沉，不再和选策略任务抢注意力。
        </p>
        {from || task ? (
          <div className="mt-4 text-xs text-text-secondary">
            上下文跳转{from ? ` · 来源: ${from}` : ''}
            {task ? ` · 任务: ${task}` : ''}
          </div>
        ) : null}
        <div className="mt-5 flex flex-wrap gap-2">
          {capabilityBadges.slice(0, 8).map((item) => (
            <Badge key={item.key} variant={item.enabled ? 'info' : 'neutral'}>
              {item.label}
            </Badge>
          ))}
        </div>
      </div>

      <section className="page-hero p-5">
        <div className="eyebrow">目录摘要</div>
        <h2 className="mt-2">当前目录</h2>
        <div className="mt-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-2">
          <div className="metric-tile px-4 py-3">
            <div className="metric-label">目录策略数</div>
            <div className="mt-2 text-2xl font-semibold text-text-primary">{strategyCount}</div>
          </div>
          <div className="metric-tile px-4 py-3">
            <div className="metric-label">已启用能力</div>
            <div className="mt-2 text-2xl font-semibold text-text-primary">{enabledCapabilityCount}</div>
          </div>
          <div className="metric-tile px-4 py-3">
            <div className="metric-label">最佳年化</div>
            <div className={`mt-2 text-lg font-semibold ${(bestAnnualReturn ?? 0) >= 0 ? 'text-success' : 'text-danger'}`}>
              {bestAnnualReturn == null || !Number.isFinite(bestAnnualReturn) ? '-' : fmtPct(bestAnnualReturn)}
            </div>
          </div>
          <div className="metric-tile px-4 py-3">
            <div className="metric-label">最佳 Sharpe</div>
            <div className="mt-2 text-lg font-semibold text-text-primary">
              {bestSharpe == null || !Number.isFinite(bestSharpe) ? '-' : fmtNum(bestSharpe, 2)}
            </div>
          </div>
        </div>
        <div className="mt-4 flex flex-wrap gap-2">
          <AskAiButton
            prompt={`当前策略目录共 ${strategyCount} 个策略，请推荐几个值得重点关注的，并说明理由`}
            label="AI 推荐策略"
          />
          <button
            type="button"
            onClick={onRunFactory}
            disabled={runFactoryPending}
            className={primaryRoundButtonCls}
          >
            {runFactoryPending ? '工厂运行中...' : '立即运行一轮工厂'}
          </button>
          <button type="button" onClick={onToggleCart} className={`relative ${secondaryRoundButtonCls}`}>
            组合购物车
            {cartItemsCount > 0 ? (
              <span className="absolute -right-1.5 -top-1.5 flex h-5 min-w-5 items-center justify-center rounded-full bg-primary px-1.5 text-[10px] text-white">
                {cartItemsCount}
              </span>
            ) : null}
          </button>
          <button
            type="button"
            onClick={onToggleFactoryDetails}
            className={secondaryRoundButtonCls}
            aria-expanded={showFactoryDetails}
          >
            {showFactoryDetails ? '收起工厂运行态' : '展开工厂运行态'}
          </button>
        </div>
        {runFactoryError ? <p className="mb-0 mt-3 text-sm text-danger">{runFactoryError}</p> : null}
      </section>
    </section>
  );
}
