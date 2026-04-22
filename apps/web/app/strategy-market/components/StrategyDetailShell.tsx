'use client';

import Link from 'next/link';
import { Badge } from '@/components/ui';
import { useMobile } from '@/hooks/use-mobile';
import { fmtNum } from '@/lib/data-utils';
import { formatMultipleTestingMode } from '@/app/strategy-market/lib/strategy-detail-view';
import { RESPONSIVE_BREAKPOINTS } from '@/lib/responsive-layout';
import type { FactoryReviewSection, StrategyCore } from '../types';
import {
  chipButtonCls,
  heroPrimaryButtonCls,
  heroSecondaryButtonCls,
  sideMetricCls,
  sidePanelCls,
} from './strategy-detail-panel-styles';

type BadgeVariant = 'success' | 'danger' | 'warning' | 'info' | 'neutral';
type StatusBadge = { label: string; variant: BadgeVariant };

type StrategyDetailHeroSectionProps = {
  strategy: StrategyCore;
  displayStatus: StatusBadge;
  marketStatus: StatusBadge;
  incubationStage: StatusBadge;
  showIncubationStage: boolean;
  promotionReady: boolean;
  strategySummary: string;
  activeTab: 'overview' | 'tracking' | 'factory';
  activeTabLabel: string;
  activeFactorySection: FactoryReviewSection;
  sampleStart: string | null;
  sampleWindow: string;
  openRiskEventsCount: number;
  vectorProfilesCount: number;
  latestQualityGrade: string | null | undefined;
  latestIncubationDecision: string;
  executionAuditGate: string;
  blockerCount: number;
  riskCount: number;
  multipleTestingMode: string | null;
  isSubscribed: boolean;
  subscribePending: boolean;
  userId: string | null;
  onAddToCart: () => void;
  onSubscribe: () => void;
  onOpenPortfolio: () => void;
  onOpenPaperSession: () => void;
};

export function StrategyDetailHeroSection({
  strategy,
  displayStatus,
  marketStatus,
  incubationStage,
  showIncubationStage,
  promotionReady,
  strategySummary,
  activeTab,
  activeTabLabel,
  activeFactorySection,
  sampleStart,
  sampleWindow,
  openRiskEventsCount,
  vectorProfilesCount,
  latestQualityGrade,
  latestIncubationDecision,
  executionAuditGate,
  blockerCount,
  riskCount,
  multipleTestingMode,
  isSubscribed,
  subscribePending,
  userId,
  onAddToCart,
  onSubscribe,
  onOpenPortfolio,
  onOpenPaperSession,
}: StrategyDetailHeroSectionProps) {
  const compactLayout = useMobile(RESPONSIVE_BREAKPOINTS.splitCollapse);

  return (
    <section className="page-hero p-5 sm:p-6">
      <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_clamp(280px,25vw,380px)]">
        <div>
          <Link href="/strategy-market" className="text-xs text-text-secondary no-underline hover:text-primary">
            &larr; 返回策略超市
          </Link>
          <div className="mt-4 flex flex-wrap items-center gap-2">
            <Badge variant="info">Strategy Workspace</Badge>
            <Badge variant={displayStatus.variant}>{displayStatus.label}</Badge>
            {displayStatus.label !== marketStatus.label ? (
              <Badge variant={marketStatus.variant}>市场状态 · {marketStatus.label}</Badge>
            ) : null}
            {showIncubationStage ? <Badge variant={incubationStage.variant}>{incubationStage.label}</Badge> : null}
            <Badge variant={promotionReady ? 'success' : 'warning'}>
              {promotionReady ? '可推进晋级' : '继续孵化观察'}
            </Badge>
          </div>
          <h1 className="mb-0 mt-4 text-[2rem] font-semibold tracking-[-0.03em] text-text-primary sm:text-[2.4rem]">
            {strategy.name}
          </h1>
          <p className="mb-0 mt-3 max-w-3xl text-sm leading-7 text-text-secondary sm:text-[15px]">{strategySummary}</p>
          <div className="mt-5 flex flex-wrap gap-2">
            <button onClick={onAddToCart} data-testid="page-primary-action" className={heroPrimaryButtonCls}>
              加入组合
            </button>
            <button
              onClick={onSubscribe}
              disabled={subscribePending || !userId}
              data-testid="strategy-subscribe-action"
              aria-label={
                subscribePending
                  ? '策略头图收藏操作处理中'
                  : !userId
                    ? '策略头图登录后收藏'
                    : isSubscribed
                      ? '策略头图取消收藏'
                      : '策略头图收藏策略'
              }
              className={`${heroSecondaryButtonCls} ${isSubscribed ? 'border-primary/35 bg-primary/12 text-primary' : ''}`}
            >
              {subscribePending ? '处理中...' : !userId ? '登录后收藏' : isSubscribed ? '取消收藏' : '收藏策略'}
            </button>
            <button type="button" onClick={onOpenPortfolio} className={heroSecondaryButtonCls}>
              去组合页配置
            </button>
            <button type="button" onClick={onOpenPaperSession} className={heroSecondaryButtonCls}>
              打开我的模拟盘测试
            </button>
          </div>
          <div
            data-testid="page-primary-status"
            className="mt-4 rounded-[22px] border border-white/50 bg-white/28 px-4 py-3 text-sm shadow-[inset_0_1px_0_rgba(255,255,255,0.68)]"
          >
            <div className="font-medium text-text-primary">
              当前处于 {activeTabLabel}，当前状态 {displayStatus.label}
              {showIncubationStage ? `，孵化阶段 ${incubationStage.label}` : '，尚未进入真实孵化链路'}
              ，收藏 {strategy.subscriber_count ?? 0}
            </div>
            <p className="mt-1 mb-0 text-xs leading-6 text-text-secondary">
              质量评级 {latestQualityGrade ?? '-'} ｜ 最新决策 {latestIncubationDecision} ｜ 执行审计 {executionAuditGate}
              {' '}｜ 阻塞 {blockerCount} ｜ 风险 {riskCount}
            </p>
          </div>

          <div className={`mt-5 grid gap-3 ${compactLayout ? 'grid-cols-2' : 'sm:grid-cols-4'}`}>
            <div className="rounded-[24px] border border-white/45 bg-white/38 p-4 shadow-[inset_0_1px_0_rgba(255,255,255,0.55)]">
              <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">当前工作流</div>
              <div className="mt-3 text-2xl font-semibold text-text-primary">{activeTabLabel}</div>
              <div className="mt-1 text-xs text-text-secondary">
                {activeTab === 'factory' ? `分区 ${activeFactorySection}` : '可在下方继续切换视图'}
              </div>
            </div>
            <div className="rounded-[24px] border border-white/45 bg-white/30 p-4 shadow-[inset_0_1px_0_rgba(255,255,255,0.48)]">
              <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">样本期</div>
              <div className="mt-3 text-2xl font-semibold text-text-primary">{sampleStart || '-'}</div>
              <div className="mt-1 text-xs text-text-secondary">{sampleWindow}</div>
            </div>
            {!compactLayout ? (
              <>
                <div className="rounded-[24px] border border-white/45 bg-white/26 p-4 shadow-[inset_0_1px_0_rgba(255,255,255,0.42)]">
                  <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">风险 / 向量</div>
                  <div className="mt-3 text-2xl font-semibold text-text-primary">
                    {openRiskEventsCount} / {vectorProfilesCount}
                  </div>
                  <div className="mt-1 text-xs text-text-secondary">开放风险事件 / 向量画像</div>
                </div>
                <div className="rounded-[24px] border border-white/45 bg-white/24 p-4 shadow-[inset_0_1px_0_rgba(255,255,255,0.38)]">
                  <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">收藏与评分</div>
                  <div className="mt-3 text-2xl font-semibold text-text-primary">{strategy.subscriber_count ?? 0}</div>
                  <div className="mt-1 text-xs text-text-secondary">
                    {strategy.avg_rating != null ? `平均评分 ${strategy.avg_rating.toFixed(1)}` : '暂无公开评分'}
                  </div>
                </div>
              </>
            ) : null}
          </div>
        </div>

        <div className="grid gap-3">
          {compactLayout ? (
            <details className={sidePanelCls}>
              <summary className="cursor-pointer list-none text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">
                展开当前策略与下一步建议
              </summary>
              <div className="mt-4 grid gap-3">
                <div className="text-base font-semibold text-text-primary">{strategy.name}</div>
                <div className={sideMetricCls}>
                  <div className="text-[11px] font-semibold uppercase tracking-[0.16em] text-text-muted">作者与评级</div>
                  <div className="mt-2 space-y-2 text-xs leading-6 text-text-secondary">
                    <div>
                      作者：<span className="font-medium text-text-primary">{strategy.author_id ?? '-'}</span>
                    </div>
                    <div>
                      质量评级：<span className="font-medium text-text-primary">{latestQualityGrade ?? '-'}</span>
                    </div>
                  </div>
                </div>
                <div className={sideMetricCls}>
                  <div className="text-[11px] font-semibold uppercase tracking-[0.16em] text-text-muted">当前决策</div>
                  <div className="mt-2 space-y-2 text-xs leading-6 text-text-secondary">
                  <div>
                    最新孵化决策：
                      <span className="font-medium text-text-primary">{latestIncubationDecision}</span>
                    </div>
                    <div>
                      多重检验：
                      <span className="font-medium text-text-primary">
                        {formatMultipleTestingMode(multipleTestingMode)}
                      </span>
                    </div>
                  </div>
                </div>
                <div className={sideMetricCls}>
                  执行审计：<span className="font-medium text-text-primary">{executionAuditGate}</span>；
                  阻塞 / 风险：<span className="font-medium text-text-primary">{blockerCount} / {riskCount}</span>
                </div>
                <div className={sideMetricCls}>
                  {activeTab === 'overview'
                    ? '先确认质量门、DSR、PBO，再决定是否值得继续跟踪。'
                    : activeTab === 'tracking'
                      ? '先看命中率和前向 Sharpe，再决定是否需要回工厂审查。'
                      : '先排运行告警，再检查实验与向量分区是否存在偏差。'}
                </div>
                <div className={sideMetricCls}>
                  {promotionReady
                    ? '当前策略已接近上架条件，适合继续联动组合页做配置模拟。'
                    : '当前策略仍处孵化观察阶段，建议不要直接跳到配置，先补完工厂审查。'}
                </div>
                <div className="flex flex-wrap gap-2">
                  <button type="button" onClick={onSubscribe} disabled={subscribePending || !userId} className={chipButtonCls}>
                    {isSubscribed ? '取消收藏' : '立即收藏'}
                  </button>
                  <button type="button" onClick={onOpenPaperSession} className={chipButtonCls}>
                    打开我的模拟盘测试
                  </button>
                </div>
              </div>
            </details>
          ) : (
            <>
          <div className={sidePanelCls}>
            <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">当前策略</div>
            <div className="mt-3 text-base font-semibold text-text-primary">{strategy.name}</div>
            <div className="mt-4 grid gap-3">
              <div className={sideMetricCls}>
                <div className="text-[11px] font-semibold uppercase tracking-[0.16em] text-text-muted">作者与评级</div>
                <div className="mt-2 space-y-2 text-xs leading-6 text-text-secondary">
                  <div>
                    作者：<span className="font-medium text-text-primary">{strategy.author_id ?? '-'}</span>
                  </div>
                  <div>
                    质量评级：<span className="font-medium text-text-primary">{latestQualityGrade ?? '-'}</span>
                  </div>
                </div>
              </div>
              <div className={sideMetricCls}>
                <div className="text-[11px] font-semibold uppercase tracking-[0.16em] text-text-muted">当前决策</div>
                <div className="mt-2 space-y-2 text-xs leading-6 text-text-secondary">
                  <div>
                  最新孵化决策：
                    <span className="font-medium text-text-primary">{latestIncubationDecision}</span>
                  </div>
                  <div>
                    多重检验：
                    <span className="font-medium text-text-primary">
                      {formatMultipleTestingMode(multipleTestingMode)}
                    </span>
                  </div>
                </div>
              </div>
            </div>
          </div>
          <div className={sidePanelCls}>
            <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">下一步建议</div>
            <div className="mt-4 space-y-3">
              <div className={sideMetricCls}>
                {activeTab === 'overview'
                  ? '先确认质量门、DSR、PBO，再决定是否值得继续跟踪。'
                  : activeTab === 'tracking'
                    ? '先看命中率和前向 Sharpe，再决定是否需要回工厂审查。'
                    : '先排运行告警，再检查实验与向量分区是否存在偏差。'}
              </div>
              <div className={sideMetricCls}>
                {promotionReady
                  ? '当前策略已接近上架条件，适合继续联动组合页做配置模拟。'
                  : '当前策略仍处孵化观察阶段，建议不要直接跳到配置，先补完工厂审查。'}
              </div>
              <div className={sideMetricCls}>
                {isSubscribed
                  ? '你已收藏该策略，可继续留在当前页做深度复盘。'
                  : '若准备持续跟踪，建议先收藏，再把它加入组合购物车。'}
              </div>
            </div>
            <div className="mt-4 flex flex-wrap gap-2">
              <button
                type="button"
                onClick={onSubscribe}
                disabled={subscribePending || !userId}
                data-testid="strategy-subscribe-secondary-action"
                aria-label={
                  subscribePending
                    ? '策略建议区收藏操作处理中'
                    : !userId
                      ? '策略建议区登录后收藏'
                      : isSubscribed
                        ? '策略建议区取消收藏'
                        : '策略建议区立即收藏'
                }
                className={chipButtonCls}
              >
                {isSubscribed ? '取消收藏' : '立即收藏'}
              </button>
              <button type="button" onClick={onOpenPaperSession} className={chipButtonCls}>
                打开我的模拟盘测试
              </button>
            </div>
          </div>
            </>
          )}
        </div>
      </div>
    </section>
  );
}

type StrategyDetailSidebarProps = {
  strategyName: string;
  displayStatus: StatusBadge;
  marketStatus: StatusBadge;
  incubationStage: StatusBadge;
  showIncubationStage: boolean;
  promotionReady: boolean;
  sampleWindow: string;
  subscriberCount: number;
  openRiskEventsCount: number;
  vectorProfilesCount: number;
  activeTab: 'overview' | 'tracking' | 'factory';
  activeTabLabel: string;
  latestQualityGrade: string | null | undefined;
  latestIncubationDecision: string;
  executionAuditGate: string;
  blockerCount: number;
  riskCount: number;
  multipleTestingMode: string | null;
  trackingTotalSignals: number;
  trackingRealtime: boolean;
  factoryActiveSection: FactoryReviewSection;
  factoryRuntimeAlertsCount: number;
  factoryTaskRunsCount: number;
  deflatedSharpeRatio: number | null;
  pboValue: number | null;
  hansenSpaPvalue: number | null;
  whiteRealityCheckPvalue: number | null;
  capacityLabel: string;
  capacityValue: number | null;
  onBackToMarket: () => void;
  onOpenPortfolio: () => void;
  onOpenPaper: () => void;
};

export function StrategyDetailSidebar({
  strategyName,
  displayStatus,
  marketStatus,
  incubationStage,
  showIncubationStage,
  promotionReady,
  sampleWindow,
  subscriberCount,
  openRiskEventsCount,
  vectorProfilesCount,
  activeTab,
  activeTabLabel,
  latestQualityGrade,
  latestIncubationDecision,
  executionAuditGate,
  blockerCount,
  riskCount,
  multipleTestingMode,
  trackingTotalSignals,
  trackingRealtime,
  factoryActiveSection,
  factoryRuntimeAlertsCount,
  factoryTaskRunsCount,
  deflatedSharpeRatio,
  pboValue,
  hansenSpaPvalue,
  whiteRealityCheckPvalue,
  capacityLabel,
  capacityValue,
  onBackToMarket,
  onOpenPortfolio,
  onOpenPaper,
}: StrategyDetailSidebarProps) {
  return (
    <div className="space-y-4 xl:h-full xl:overflow-y-auto xl:pl-1">
      <div className={sidePanelCls}>
        <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">当前策略</div>
        <div className="mt-3 text-base font-semibold text-text-primary">{strategyName}</div>
        <div className="mt-3 flex flex-wrap gap-2">
          <Badge variant={displayStatus.variant}>{displayStatus.label}</Badge>
          {displayStatus.label !== marketStatus.label ? (
            <Badge variant={marketStatus.variant}>市场状态 · {marketStatus.label}</Badge>
          ) : null}
          {showIncubationStage ? <Badge variant={incubationStage.variant}>{incubationStage.label}</Badge> : null}
          <Badge variant={promotionReady ? 'success' : 'warning'}>
            {promotionReady ? '可推进晋级' : '继续孵化观察'}
          </Badge>
        </div>
        <div className="mt-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-1">
          <div className={sideMetricCls}>
            <div className="text-[11px] font-semibold uppercase tracking-[0.16em] text-text-muted">样本期</div>
            <div className="mt-2 text-sm font-medium text-text-primary">{sampleWindow}</div>
          </div>
          <div className={sideMetricCls}>
            <div className="grid grid-cols-3 gap-3 text-center">
              <div>
                <div className="text-lg font-semibold text-text-primary">{subscriberCount}</div>
                <div className="mt-1 text-[11px] text-text-secondary">收藏</div>
              </div>
              <div>
                <div className="text-lg font-semibold text-text-primary">{openRiskEventsCount}</div>
                <div className="mt-1 text-[11px] text-text-secondary">风险</div>
              </div>
              <div>
                <div className="text-lg font-semibold text-text-primary">{vectorProfilesCount}</div>
                <div className="mt-1 text-[11px] text-text-secondary">画像</div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <div className={sidePanelCls}>
        <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">当前工作流</div>
        <div className="mt-3 text-base font-semibold text-text-primary">{activeTabLabel}</div>
        <div className="mt-4 space-y-3">
          {activeTab === 'overview' ? (
            <div className={sideMetricCls}>
              <div className="space-y-2 text-xs leading-6 text-text-secondary">
                <div>
                  质量评级：<span className="font-medium text-text-primary">{latestQualityGrade ?? '-'}</span>
                </div>
                <div>
                  最新孵化决策：
                  <span className="font-medium text-text-primary">{latestIncubationDecision}</span>
                </div>
                <div>
                  多重检验：
                  <span className="font-medium text-text-primary">
                    {formatMultipleTestingMode(multipleTestingMode)}
                  </span>
                </div>
                <div>
                  执行审计：<span className="font-medium text-text-primary">{executionAuditGate}</span>
                </div>
                <div>
                  阻塞 / 风险：<span className="font-medium text-text-primary">{blockerCount} / {riskCount}</span>
                </div>
              </div>
            </div>
          ) : null}
          {activeTab === 'tracking' ? (
            <div className={sideMetricCls}>
              <div className="space-y-2 text-xs leading-6 text-text-secondary">
                <div>
                  总信号数：<span className="font-medium text-text-primary">{trackingTotalSignals}</span>
                </div>
                <div>
                  信号订阅：
                  <span className="font-medium text-text-primary">{trackingRealtime ? '实时订阅' : '延迟模式'}</span>
                </div>
                <div>
                  当前建议：<span className="font-medium text-text-primary">先看命中率，再看前向 IC / Sharpe。</span>
                </div>
              </div>
            </div>
          ) : null}
          {activeTab === 'factory' ? (
            <div className={sideMetricCls}>
              <div className="space-y-2 text-xs leading-6 text-text-secondary">
                <div>
                  当前分区：<span className="font-medium text-text-primary">{factoryActiveSection}</span>
                </div>
                <div>
                  运行告警：
                  <span className="font-medium text-text-primary">{factoryRuntimeAlertsCount}</span>
                </div>
                <div>
                  实验任务：<span className="font-medium text-text-primary">{factoryTaskRunsCount}</span>
                </div>
              </div>
            </div>
          ) : null}
        </div>
        <div className="mt-4 flex flex-wrap gap-2">
          <button type="button" onClick={onBackToMarket} className={chipButtonCls}>
            回策略超市
          </button>
          <button type="button" onClick={onOpenPortfolio} className={chipButtonCls}>
            去组合页
          </button>
          <button type="button" onClick={onOpenPaper} className={chipButtonCls}>
            去模拟交易
          </button>
        </div>
      </div>

      <div className={sidePanelCls}>
        <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">可信指标</div>
        <div className="mt-4 grid gap-3">
          <div className={sideMetricCls}>
            <div className="grid grid-cols-2 gap-3 text-xs text-text-secondary">
              <div>
                <div className="text-[11px] uppercase tracking-[0.16em] text-text-muted">DSR</div>
                <div className="mt-1 text-sm font-medium text-text-primary">
                  {deflatedSharpeRatio == null ? '-' : fmtNum(deflatedSharpeRatio, 4)}
                </div>
              </div>
              <div>
                <div className="text-[11px] uppercase tracking-[0.16em] text-text-muted">PBO</div>
                <div className="mt-1 text-sm font-medium text-text-primary">
                  {pboValue == null ? '-' : fmtNum(pboValue, 4)}
                </div>
              </div>
              <div>
                <div className="text-[11px] uppercase tracking-[0.16em] text-text-muted">SPA p</div>
                <div className="mt-1 text-sm font-medium text-text-primary">
                  {hansenSpaPvalue == null ? '-' : fmtNum(hansenSpaPvalue, 4)}
                </div>
              </div>
              <div>
                <div className="text-[11px] uppercase tracking-[0.16em] text-text-muted">White RC</div>
                <div className="mt-1 text-sm font-medium text-text-primary">
                  {whiteRealityCheckPvalue == null ? '-' : fmtNum(whiteRealityCheckPvalue, 4)}
                </div>
              </div>
            </div>
          </div>
          <div className={sideMetricCls}>
            <div className="text-[11px] font-semibold uppercase tracking-[0.16em] text-text-muted">{capacityLabel}</div>
            <div className="mt-2 text-base font-semibold text-text-primary">
              {capacityValue == null ? '-' : fmtNum(capacityValue, 2)}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
