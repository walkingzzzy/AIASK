'use client';

import { AskAiButton } from '@/components/ask-ai-button';
import { Badge } from '@/components/ui';
import { useMobile } from '@/hooks/use-mobile';
import { fmtNum, fmtPct } from '@/lib/data-utils';
import { RESPONSIVE_BREAKPOINTS } from '@/lib/responsive-layout';
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
  workspace: 'market' | 'favorites' | 'mine' | 'factory';
  capabilityBadges: CapabilityBadgeItem[];
  strategyCount: number;
  enabledCapabilityCount: number;
  bestAnnualReturn: number | null;
  bestSharpe: number | null;
  runFactoryPending: boolean;
  runFactoryError: string | null;
  aiGeneratePending: boolean;
  aiGenerateError: string | null;
  aiGenerateSummary: string | null;
  cartItemsCount: number;
  showFactoryDetails: boolean;
  canRunFactory: boolean;
  canAiGenerate: boolean;
  canCreatePersonalStrategy: boolean;
  onRunFactory: () => void;
  onAiGenerate?: () => void;
  onToggleCart: () => void;
  onToggleFactoryDetails: () => void;
  onCreatePersonalStrategy?: () => void;
};

export function StrategyMarketHeroSection({
  from,
  task,
  workspace,
  capabilityBadges,
  strategyCount,
  enabledCapabilityCount,
  bestAnnualReturn,
  bestSharpe,
  runFactoryPending,
  runFactoryError,
  aiGeneratePending,
  aiGenerateError,
  aiGenerateSummary,
  cartItemsCount,
  showFactoryDetails,
  canRunFactory,
  canAiGenerate,
  canCreatePersonalStrategy,
  onRunFactory,
  onAiGenerate,
  onToggleCart,
  onToggleFactoryDetails,
  onCreatePersonalStrategy,
}: StrategyMarketHeroSectionProps) {
  const compactLayout = useMobile(RESPONSIVE_BREAKPOINTS.splitCollapse);
  const showAiGenerateAction = workspace === 'factory' && canAiGenerate && typeof onAiGenerate === 'function';
  const workspaceLabel = workspace === 'favorites'
    ? '我的收藏'
    : workspace === 'mine'
      ? '我的策略'
      : workspace === 'factory'
        ? '工厂运行态'
        : '市场策略';
  const workspaceTitle = workspace === 'favorites'
    ? '先看你已收藏的策略，再决定是否转成个人版本或加入组合。'
    : workspace === 'mine'
      ? '这里是你的个人策略工作区，可继续编辑、AI 优化和发起个人模拟盘测试。'
      : workspace === 'factory'
        ? '工厂运行态单独下沉到独立工作区，避免和选策略任务抢注意力。'
        : '先看筛选结果，再决定收藏、组合和工厂动作。';
  const workspaceLead = workspace === 'favorites'
    ? '收藏视图只保留你已经标记过的策略，方便继续比较、复制为个人策略或加入组合购物车。'
    : workspace === 'mine'
      ? '个人策略视图只展示你拥有的草稿和个人版本。这里优先关注编辑、模拟盘测试和 AI 优化，而不是工厂运维信号。'
      : workspace === 'factory'
        ? '工厂运行态集中展示调度、快照、可观测性和最近 run，面向运营与治理，不再和市场榜单混排。'
        : '市场策略视图只保留榜单和目录，工厂运行态默认下沉到单独工作区，不再和选策略任务抢注意力。';

  return (
    <section className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_clamp(280px,25vw,380px)]">
      <div className="page-hero p-6 sm:p-7">
        <div className="eyebrow">Strategy Workspace</div>
        <h1 className="mt-3">{workspaceTitle}</h1>
        <p className="page-lead mb-0 mt-3">
          {workspaceLead}
        </p>
        {from || task ? (
          <div className="mt-4 text-xs text-text-secondary">
            上下文跳转{from ? ` · 来源: ${from}` : ''}
            {task ? ` · 任务: ${task}` : ''}
          </div>
        ) : null}
        <div className="mt-5 flex flex-wrap gap-2">
          {capabilityBadges.slice(0, compactLayout ? 4 : 8).map((item) => (
            <Badge key={item.key} variant={item.enabled ? 'info' : 'neutral'}>
              {item.label}
            </Badge>
          ))}
        </div>
        {compactLayout ? (
          <details className="mt-3 rounded-[18px] border border-white/45 bg-white/24 px-3 py-3">
            <summary className="cursor-pointer list-none text-sm font-medium text-text-primary">展开更多工厂能力</summary>
            <div className="mt-3 flex flex-wrap gap-2">
              {capabilityBadges.slice(4, 10).map((item) => (
                <Badge key={item.key} variant={item.enabled ? 'info' : 'neutral'}>
                  {item.label}
                </Badge>
              ))}
            </div>
          </details>
        ) : null}
      </div>

      <section className="page-hero p-5">
        <div className="eyebrow">目录摘要</div>
        <h2 className="mt-2">{workspaceLabel}</h2>
        <div className={`mt-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-2 ${compactLayout ? 'grid-cols-2' : ''}`}>
          <div className="metric-tile px-4 py-3">
            <div className="metric-label">目录策略数</div>
            <div className="mt-2 text-2xl font-semibold text-text-primary">{strategyCount}</div>
          </div>
          <div className="metric-tile px-4 py-3">
            <div className="metric-label">已启用能力</div>
            <div className="mt-2 text-2xl font-semibold text-text-primary">{enabledCapabilityCount}</div>
          </div>
          {!compactLayout ? (
            <>
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
            </>
          ) : null}
        </div>
        <div className="mt-4 flex flex-wrap gap-2">
          <AskAiButton
            prompt={`当前${workspaceLabel}共 ${strategyCount} 个策略，请推荐几个值得重点关注的，并说明理由`}
            label={canAiGenerate && workspace === 'factory' ? 'AI 推荐工厂动作' : 'AI 推荐策略'}
          />
          {showAiGenerateAction ? (
            <button
              type="button"
              onClick={onAiGenerate}
              disabled={aiGeneratePending}
              className={primaryRoundButtonCls}
            >
              {aiGeneratePending ? 'AI 生成中...' : 'AI 生成策略'}
            </button>
          ) : null}
          {workspace === 'factory' && canRunFactory ? (
            <button
              type="button"
              onClick={onRunFactory}
              disabled={runFactoryPending}
              className={primaryRoundButtonCls}
            >
              {runFactoryPending ? '工厂运行中...' : '立即运行一轮工厂'}
            </button>
          ) : null}
          {workspace === 'mine' && canCreatePersonalStrategy && onCreatePersonalStrategy ? (
            <button type="button" onClick={onCreatePersonalStrategy} className={primaryRoundButtonCls}>
              新建个人策略
            </button>
          ) : null}
          <button type="button" onClick={onToggleCart} className={`relative ${secondaryRoundButtonCls}`}>
            组合购物车
            {cartItemsCount > 0 ? (
              <span className="absolute -right-1.5 -top-1.5 flex h-5 min-w-5 items-center justify-center rounded-full bg-primary px-1.5 text-[10px] text-white">
                {cartItemsCount}
              </span>
            ) : null}
          </button>
          {workspace === 'factory' ? (
            <button
              type="button"
              onClick={onToggleFactoryDetails}
              className={secondaryRoundButtonCls}
              aria-expanded={showFactoryDetails}
            >
              {showFactoryDetails ? '收起工厂运行态' : '展开工厂运行态'}
            </button>
          ) : null}
        </div>
        <div className="mt-3 text-xs leading-6 text-text-secondary">
          {workspace === 'factory'
            ? 'AI 中心负责给出判断和跳转；真正的工厂生成、收藏、个人策略编辑与模拟盘动作，仍由当前页面和 Copilot 页面动作执行。'
            : '列表页当前只负责筛选、比较和加入组合；收藏策略、复制个人版本与创建模拟盘测试请进入策略详情页执行。'}
        </div>
        {showAiGenerateAction && (aiGenerateSummary || aiGenerateError) ? (
          <div className="mt-3 rounded-[18px] border border-white/45 bg-white/28 px-3 py-3 text-xs text-text-secondary">
            <div className="font-medium text-text-primary">AI 生成反馈</div>
            <div className="mt-2">{aiGenerateSummary || aiGenerateError}</div>
          </div>
        ) : null}
        {workspace === 'factory' && canRunFactory && runFactoryError ? <p className="mb-0 mt-3 text-sm text-danger">{runFactoryError}</p> : null}
      </section>
    </section>
  );
}
