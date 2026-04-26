'use client';

import { AskAiButton } from '@/components/ask-ai-button';
import LightOverviewHero from '@/components/light-overview-hero';
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

type SummaryMetricItem = {
  key: string;
  label: string;
  value: string;
  tone?: 'default' | 'success' | 'danger';
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
  summaryMetrics?: SummaryMetricItem[];
  observabilitySummary?: SummaryMetricItem[];
  aiRecommendationPrompt?: string;
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
  summaryMetrics,
  observabilitySummary,
  aiRecommendationPrompt,
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
  const compactWorkspaceTitle = workspace === 'favorites'
    ? '继续比较你已收藏的策略。'
    : workspace === 'mine'
      ? '继续编辑、优化和测试你的个人策略。'
      : workspace === 'factory'
        ? '工厂运行态单独处理，不再和选策略混排。'
        : '先筛选结果，再决定收藏、组合和工厂动作。';
  const workspaceLead = workspace === 'favorites'
    ? '收藏视图只保留你已经标记过的策略，方便继续比较、复制为个人策略或加入组合购物车。'
    : workspace === 'mine'
      ? '个人策略视图只展示你拥有的草稿和个人版本。这里优先关注编辑、模拟盘测试和 AI 优化，而不是工厂运维信号。'
      : workspace === 'factory'
        ? '工厂运行态集中展示调度、快照、可观测性和最近 run，面向运营与治理，不再和市场榜单混排。'
        : '市场策略视图只保留榜单和目录，工厂运行态默认下沉到单独工作区，不再和选策略任务抢注意力。';
  const compactWorkspaceLead = workspace === 'favorites'
    ? '收藏视图只保留你已经标记过的策略，便于继续比较。'
    : workspace === 'mine'
      ? '这里优先做个人策略编辑、AI 优化和模拟盘测试。'
      : workspace === 'factory'
        ? '这里只看调度、快照和可观测性，面向运营与治理。'
        : '列表页当前只负责筛选、比较和加入组合，深度动作留到详情页。';
  const fallbackSummaryMetrics: SummaryMetricItem[] = [
    { key: 'strategy-count', label: '目录策略数', value: String(strategyCount) },
    { key: 'capability-count', label: '已启用能力', value: String(enabledCapabilityCount) },
    {
      key: 'best-annual-return',
      label: '最佳年化',
      value: bestAnnualReturn == null || !Number.isFinite(bestAnnualReturn) ? '-' : fmtPct(bestAnnualReturn),
      tone: (bestAnnualReturn ?? 0) >= 0 ? 'success' : 'danger',
    },
    {
      key: 'best-sharpe',
      label: '最佳 Sharpe',
      value: bestSharpe == null || !Number.isFinite(bestSharpe) ? '-' : fmtNum(bestSharpe, 2),
    },
  ];
  const visibleSummaryMetrics = (summaryMetrics && summaryMetrics.length > 0 ? summaryMetrics : fallbackSummaryMetrics)
    .slice(0, compactLayout ? 2 : 4);
  const askAiPromptText = aiRecommendationPrompt
    ?? `当前${workspaceLabel}共 ${strategyCount} 个策略，请推荐几个值得重点关注的，并说明理由`;
  const resolveMetricTone = (item: SummaryMetricItem) => {
    if (item.tone === 'success') return 'text-success';
    if (item.tone === 'danger') return 'text-danger';
    return 'text-text-primary';
  };

  const cartButton = (
    <button type="button" onClick={onToggleCart} className={`relative ${secondaryRoundButtonCls}`}>
      组合购物车
      {cartItemsCount > 0 ? (
        <span className="absolute -right-1.5 -top-1.5 flex h-5 min-w-5 items-center justify-center rounded-full bg-primary px-1.5 text-[10px] text-white">
          {cartItemsCount}
        </span>
      ) : null}
    </button>
  );
  const factoryToggleButton = workspace === 'factory' ? (
    <button
      type="button"
      onClick={onToggleFactoryDetails}
      className={secondaryRoundButtonCls}
      aria-expanded={showFactoryDetails}
    >
      {showFactoryDetails ? '收起工厂运行态' : '展开工厂运行态'}
    </button>
  ) : null;
  const askAiButton = (
    <AskAiButton
      prompt={askAiPromptText}
      label={workspace === 'factory' ? 'AI 推荐工厂动作' : 'AI 推荐策略'}
    />
  );

  if (compactLayout) {
    return (
      <LightOverviewHero
        eyebrow="Strategy Workspace"
        title={compactWorkspaceTitle}
        summary={compactWorkspaceLead}
        badges={(
          <>
            <Badge variant="info">{workspaceLabel}</Badge>
            <Badge variant="neutral">启用能力 {enabledCapabilityCount}</Badge>
            {workspace === 'factory' ? (
              <Badge variant={showFactoryDetails ? 'warning' : 'neutral'}>
                {showFactoryDetails ? '工厂明细展开' : '工厂明细收起'}
              </Badge>
            ) : null}
          </>
        )}
        actions={(
          <>
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
                {runFactoryPending ? '工厂运行中...' : '运行工厂'}
              </button>
            ) : null}
            {workspace === 'mine' && canCreatePersonalStrategy && onCreatePersonalStrategy ? (
              <button type="button" onClick={onCreatePersonalStrategy} className={primaryRoundButtonCls}>
                新建个人策略
              </button>
            ) : null}
            {cartButton}
          </>
        )}
        status={(
          <div
            data-testid="page-primary-status"
            className="rounded-[20px] border border-white/50 bg-white/28 px-4 py-3 text-sm shadow-[inset_0_1px_0_rgba(255,255,255,0.68)]"
          >
            <div className="font-medium text-text-primary">
              当前工作区 {workspaceLabel} ｜ 策略 {strategyCount} 条 ｜ 购物车 {cartItemsCount} 项
            </div>
            <p className="mb-0 mt-1 text-xs leading-6 text-text-secondary">
              {workspace === 'factory'
                ? '首屏只保留概况与动作，联动观测和工厂明细按需展开。'
                : '首屏只保留筛选、比较和下一步动作，深度动作进入详情页。'}
            </p>
          </div>
        )}
        metrics={visibleSummaryMetrics.map((item) => ({
          key: item.key,
          label: item.label,
          value: item.value,
          tone: item.tone,
        }))}
        compact
        testId="strategy-market-factory-overview"
        detailsTitle={workspace === 'factory' ? '展开工厂能力与联动观测' : '展开能力与下一步'}
        detailsContent={(
          <div className="space-y-3">
            {from || task ? (
              <div className="rounded-[18px] border border-white/45 bg-white/24 px-3 py-3 text-xs leading-6 text-text-secondary">
                上下文跳转{from ? ` · 来源: ${from}` : ''}
                {task ? ` · 任务: ${task}` : ''}
              </div>
            ) : null}
            <div className="flex flex-wrap gap-2">
              {capabilityBadges.slice(0, 10).map((item) => (
                <Badge key={item.key} variant={item.enabled ? 'info' : 'neutral'}>
                  {item.label}
                </Badge>
              ))}
            </div>
            {observabilitySummary && observabilitySummary.length > 0 ? (
              <div
                className="rounded-[18px] border border-white/45 bg-white/24 px-3 py-3"
                data-testid="strategy-market-observability"
              >
                <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">联动观测</div>
                <div className="mt-3 grid gap-2 sm:grid-cols-2">
                  {observabilitySummary.slice(0, 3).map((item) => (
                    <div key={item.key} className="rounded-[16px] border border-white/45 bg-white/24 px-3 py-2.5">
                      <div className="text-[11px] font-semibold uppercase tracking-[0.16em] text-text-muted">
                        {item.label}
                      </div>
                      <div className={`mt-1.5 text-sm font-medium ${resolveMetricTone(item)}`}>{item.value}</div>
                    </div>
                  ))}
                </div>
              </div>
            ) : null}
            <div className="flex flex-wrap gap-2">
              {askAiButton}
              {factoryToggleButton}
            </div>
            <div className="text-xs leading-6 text-text-secondary">
              {workspace === 'factory'
                ? '工厂动作由本页和 Copilot 联动执行，慢接口区域默认收起。'
                : '先筛选，再进详情执行收藏、组合或模拟。'}
            </div>
            {showAiGenerateAction && (aiGenerateSummary || aiGenerateError) ? (
              <div className="rounded-[18px] border border-white/45 bg-white/28 px-3 py-3 text-xs text-text-secondary">
                <div className="font-medium text-text-primary">AI 生成反馈</div>
                <div className="mt-2">{aiGenerateSummary || aiGenerateError}</div>
              </div>
            ) : null}
            {workspace === 'factory' && canRunFactory && runFactoryError ? (
              <p className="mb-0 text-sm text-danger">{runFactoryError}</p>
            ) : null}
          </div>
        )}
      />
    );
  }

  return (
    <section className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_clamp(280px,25vw,380px)]">
      <div className="page-hero p-6 sm:p-7">
        <div className="eyebrow">Strategy Workspace</div>
        <h1 className="mt-3">{compactLayout ? compactWorkspaceTitle : workspaceTitle}</h1>
        <p className="page-lead mb-0 mt-3">
          {compactLayout ? compactWorkspaceLead : workspaceLead}
        </p>
        {from || task ? (
          <div className="mt-4 text-xs text-text-secondary">
            上下文跳转{from ? ` · 来源: ${from}` : ''}
            {task ? ` · 任务: ${task}` : ''}
          </div>
        ) : null}
        <div className="mt-5 flex flex-wrap gap-2">
          {capabilityBadges.slice(0, compactLayout ? 2 : 8).map((item) => (
            <Badge key={item.key} variant={item.enabled ? 'info' : 'neutral'}>
              {item.label}
            </Badge>
          ))}
        </div>
        {compactLayout ? (
          <details className="mt-3 rounded-[18px] border border-white/45 bg-white/24 px-3 py-3">
            <summary className="cursor-pointer list-none text-sm font-medium text-text-primary">
              展开更多工厂能力 · 已启用 {enabledCapabilityCount}
            </summary>
            <div className="mt-3 flex flex-wrap gap-2">
              {capabilityBadges.slice(2, 10).map((item) => (
                <Badge key={item.key} variant={item.enabled ? 'info' : 'neutral'}>
                  {item.label}
                </Badge>
              ))}
            </div>
          </details>
        ) : null}
      </div>

      <section className="page-hero p-5" data-testid="strategy-market-factory-overview">
        <div className="eyebrow">{workspace === 'factory' ? '工厂概况' : '目录与工厂摘要'}</div>
        <h2 className="mt-2">{workspaceLabel}</h2>
        <div className={`mt-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-2 ${compactLayout ? 'grid-cols-2' : ''}`}>
          {visibleSummaryMetrics.map((item) => (
            <div key={item.key} className="metric-tile px-4 py-3">
              <div className="metric-label">{item.label}</div>
              <div className={`mt-2 text-lg font-semibold ${resolveMetricTone(item)}`}>
                {item.value}
              </div>
            </div>
          ))}
        </div>
        <div className="mt-4 flex flex-wrap gap-2">
          {askAiButton}
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
          {cartButton}
          {factoryToggleButton}
        </div>
        <div className="mt-3 text-xs leading-6 text-text-secondary">
          {compactLayout
            ? workspace === 'factory'
              ? '工厂动作由本页和 Copilot 联动执行。'
              : '先筛选，再进详情执行收藏、组合或模拟。'
            : workspace === 'factory'
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
        {observabilitySummary && observabilitySummary.length > 0 ? (
          <div className="mt-4 rounded-[18px] border border-white/45 bg-white/24 px-3 py-3" data-testid="strategy-market-observability">
            <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">联动观测</div>
            <div className="mt-3 grid gap-2 sm:grid-cols-3">
              {observabilitySummary.slice(0, compactLayout ? 1 : 3).map((item) => (
                <div key={item.key} className="rounded-[16px] border border-white/45 bg-white/24 px-3 py-2.5">
                  <div className="text-[11px] font-semibold uppercase tracking-[0.16em] text-text-muted">{item.label}</div>
                  <div className={`mt-1.5 text-sm font-medium ${resolveMetricTone(item)}`}>{item.value}</div>
                </div>
              ))}
            </div>
          </div>
        ) : null}
      </section>
    </section>
  );
}
