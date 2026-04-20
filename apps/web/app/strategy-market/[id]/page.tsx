'use client';

import { useEffect, useMemo } from 'react';
import { useParams, useRouter } from 'next/navigation';
import WorkspaceSplitLayout from '@/components/workspace-split-layout';
import WorkspaceToolbar from '@/components/workspace-toolbar';
import { PageContainer, TabBar } from '@/components/ui';
import { useMobile } from '@/hooks/use-mobile';
import { usePageActions } from '@/hooks/use-page-actions';
import { usePageContext } from '@/hooks/use-page-context';
import {
  DETAIL_TABS,
  FACTORY_SECTIONS,
  firstFiniteNumber,
  formatMultipleTestingMode,
} from '@/app/strategy-market/lib/strategy-detail-view';
import { useAuthStore } from '@/store/auth-store';
import { useCartStore } from '@/store/cart-store';
import { useWorkbenchStore } from '@/store/workbench-store';
import { FactoryReviewPanel } from '../components/FactoryReviewPanel';
import { LiveTrackingPanel } from '../components/LiveTrackingPanel';
import { StrategyDetailHeroSection, StrategyDetailSidebar } from '../components/StrategyDetailShell';
import { StrategyDetailOverviewTab } from '../components/StrategyDetailOverviewTab';
import {
  StrategyDetailErrorState,
  StrategyDetailEmptyState,
  StrategyDetailLoadingState,
} from '../components/StrategyDetailStatusState';
import { useStrategyDetailPage, type StrategyDetailTab } from '../hooks/use-strategy-detail-page';
import type { FactoryReviewSection } from '../types';
import { isSurfacePlaceholderId } from '@/lib/surface-contracts';
import { RESPONSIVE_BREAKPOINTS } from '@/lib/responsive-layout';

export default function StrategyDetailPage() {
  const compactLayout = useMobile(RESPONSIVE_BREAKPOINTS.splitCollapse);
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const addToCart = useCartStore((state) => state.addStrategy);
  const updateWorkbenchContext = useWorkbenchStore((state) => state.updateContext);
  const addWorkbenchTask = useWorkbenchStore((state) => state.addTask);
  const user = useAuthStore((state) => state.user);
  const userId = user?.id ?? user?.username ?? null;
  const strategyId = params?.id ?? null;
  const emptyDetailContract = isSurfacePlaceholderId(strategyId);

  const {
    detailLoading,
    detailError,
    strategy,
    statusVariant,
    activeTab,
    setActiveTab,
    overview,
    trackingPanelProps,
    factoryPanelProps,
  } = useStrategyDetailPage(emptyDetailContract ? null : strategyId, userId);

  const {
    metrics,
    allMetrics,
    reviews,
    navSeries,
    navCategories,
    factorBars,
    incubationOverview,
    latestQualityReport,
    incubationAccount,
    latestIncubationMetric,
    paperAccount,
    latestPaperNav,
    paperNavRows,
    openRiskEvents,
    vectorProfiles,
    highConfidenceQualityUiEnabled,
    promotionReady,
    rating,
    setRating,
    comment,
    setComment,
    isSubscribed,
    subscribePending,
    reviewPending,
    handleSubscribe,
    handleReview,
  } = overview;

  const pageKey = 'strategy-detail';
  const activeTabLabel = DETAIL_TABS.find((item) => item.key === activeTab)?.label ?? '策略概览';
  const strategySummary =
    strategy?.description ||
    '先确认策略合同、质量门状态和当前孵化决策，再决定是加入组合、继续订阅，还是转到工厂审查继续追踪。';
  const portfolioHref = strategy?.id
    ? `/portfolio?from=strategy-detail&strategy_id=${encodeURIComponent(String(strategy.id))}`
    : '/portfolio';
  const paperHref = strategy?.id
    ? `/paper-trading?from=strategy-detail&strategy_id=${encodeURIComponent(String(strategy.id))}`
    : '/paper-trading';

  const currentView = useMemo(
    () => ({
      strategyId: strategy?.id ?? strategyId ?? null,
      activeTab,
      factorySection: factoryPanelProps.activeSection,
      subscribed: isSubscribed,
    }),
    [activeTab, factoryPanelProps.activeSection, isSubscribed, strategy?.id, strategyId],
  );

  useEffect(() => {
    if (!strategy) return;
    updateWorkbenchContext({
      strategyId: String(strategy.id),
      strategyName: strategy.name,
    });
  }, [strategy, updateWorkbenchContext]);

  usePageContext({
    pageKey,
    title: emptyDetailContract
      ? '策略详情空态'
      : strategy?.name ? `策略详情 · ${strategy.name}` : '策略详情',
    summary: emptyDetailContract
      ? '当前环境还没有可进入的策略详情数据，页面按空态契约渲染。'
      : strategy
      ? `${strategy.name} 当前处于 ${strategy.status ?? '未知状态'}，当前工作流为 ${activeTabLabel}。订阅数 ${strategy.subscriber_count ?? 0}，风险事件 ${openRiskEvents.length}，向量画像 ${vectorProfiles.length}。`
      : detailLoading
        ? '策略详情加载中。'
        : detailError
          ? '策略详情暂时无法加载。'
          : '策略详情待初始化。',
    tags: [
      emptyDetailContract ? '空态契约' : null,
      strategy?.status ? String(strategy.status) : null,
      activeTabLabel,
      strategy?.author_id ? `作者 ${strategy.author_id}` : null,
      strategy?.subscriber_count != null ? `${strategy.subscriber_count} 订阅` : null,
      latestQualityReport?.summary?.validation_grade ? `评级 ${latestQualityReport.summary.validation_grade}` : null,
    ].filter((item): item is string => Boolean(item)),
    suggestions: emptyDetailContract
      ? ['返回策略超市', '运行工厂生成策略', '稍后重新加载详情页']
      : strategy
      ? [
          activeTab === 'overview' ? '切到实盘跟踪看信号与命中率' : '回概览确认样本期和质量门',
          activeTab === 'factory' ? '继续切换工厂审查分区' : '打开工厂审查看运行风控与实验事件',
          isSubscribed ? '取消订阅策略并返回列表继续筛选' : '订阅该策略并纳入后续跟踪',
        ]
      : ['返回策略超市', '重新加载策略详情'],
    raw: {
      strategyId: emptyDetailContract ? null : strategy?.id ?? strategyId ?? null,
      emptyDetailContract,
      activeTab,
      factorySection: factoryPanelProps.activeSection,
      subscribed: isSubscribed,
      riskEvents: openRiskEvents.length,
      vectorProfiles: vectorProfiles.length,
      promotionReady,
    },
  });

  function addStrategyToCart() {
    if (!strategy) return;
    addToCart({ strategyId: strategy.id, name: strategy.name, weight: 0 });
    updateWorkbenchContext({
      strategyId: String(strategy.id),
      strategyName: strategy.name,
    });
  }

  const pageActions = useMemo(
    () => emptyDetailContract
      ? [
          {
            id: 'strategy-detail.empty.open-market',
            label: '返回策略超市',
            description: '回到策略列表继续筛选和比较',
            keywords: ['策略超市', '返回列表'],
            scope: 'page' as const,
            pageKey,
            run: () => {
              router.push('/strategy-market');
              return { message: '已返回策略超市' };
            },
          },
          {
            id: 'strategy-detail.empty.reload',
            label: '重新加载策略详情',
            description: '重新尝试加载当前空态详情页',
            keywords: ['刷新', '重试'],
            scope: 'page' as const,
            pageKey,
            run: () => {
              window.location.reload();
              return { message: '已重新加载策略详情' };
            },
          },
        ]
      : [
      {
        id: 'strategy-detail.open-market',
        label: '返回策略超市',
        description: '回到策略列表继续筛选和比较',
        keywords: ['策略超市', '返回列表'],
        scope: 'page' as const,
        pageKey,
        run: () => {
          router.push('/strategy-market');
          return { message: '已返回策略超市' };
        },
      },
      {
        id: 'strategy-detail.switch.overview',
        label: '切到策略概览',
        description: '查看样本期、质量门、净值轨迹和用户评价',
        keywords: ['概览', '质量门'],
        scope: 'page' as const,
        pageKey,
        run: () => {
          setActiveTab('overview');
          return { message: '已切到策略概览' };
        },
      },
      {
        id: 'strategy-detail.switch.tracking',
        label: '切到实盘跟踪',
        description: '查看信号统计、前向验证与历史信号',
        keywords: ['实盘跟踪', '信号'],
        scope: 'page' as const,
        pageKey,
        run: () => {
          setActiveTab('tracking');
          return { message: '已切到实盘跟踪' };
        },
      },
      {
        id: 'strategy-detail.switch.factory',
        label: '切到工厂审查',
        description: '查看工厂摘要、孵化闭环、运行风控和实验事件',
        keywords: ['工厂审查', '风控'],
        scope: 'page' as const,
        pageKey,
        run: () => {
          setActiveTab('factory');
          return { message: '已切到工厂审查' };
        },
      },
      {
        id: 'strategy-detail.subscribe',
        label: isSubscribed ? '取消订阅策略' : '订阅策略',
        description: '切换当前策略的订阅状态',
        keywords: ['订阅', '策略'],
        scope: 'page' as const,
        pageKey,
        run: async () => {
          if (!strategy) throw new Error('当前策略尚未加载完成');
          await handleSubscribe();
          return { message: isSubscribed ? `已取消订阅 ${strategy.name}` : `已订阅 ${strategy.name}` };
        },
      },
      {
        id: 'strategy-detail.add-to-portfolio',
        label: '加入组合并打开组合页',
        description: '将当前策略加入组合购物车并跳转到组合页继续配置',
        keywords: ['加入组合', '组合页'],
        scope: 'page' as const,
        pageKey,
        run: () => {
          if (!strategy) throw new Error('当前策略尚未加载完成');
          addToCart({ strategyId: strategy.id, name: strategy.name, weight: 0 });
          updateWorkbenchContext({
            strategyId: String(strategy.id),
            strategyName: strategy.name,
          });
          addWorkbenchTask({
            pageKey,
            title: `配置策略 ${strategy.name} 的组合权重`,
            href: portfolioHref,
            kind: 'portfolio-review',
            payload: { strategyId: strategy.id, strategyName: strategy.name },
          });
          router.push(portfolioHref);
          return { message: `已把 ${strategy.name} 加入组合并打开组合页` };
        },
      },
      {
        id: 'strategy-detail.open-paper',
        label: '打开模拟交易页',
        description: '切到模拟交易页查看该策略的交易联动',
        keywords: ['模拟交易', 'paper'],
        scope: 'page' as const,
        pageKey,
        run: () => {
          router.push(paperHref);
          return { message: '已打开模拟交易页' };
        },
      },
    ],
    [
      addToCart,
      addWorkbenchTask,
      emptyDetailContract,
      handleSubscribe,
      isSubscribed,
      pageKey,
      paperHref,
      portfolioHref,
      router,
      setActiveTab,
      strategy,
      updateWorkbenchContext,
    ],
  );

  usePageActions(pageActions);

  if (emptyDetailContract) {
    return <StrategyDetailEmptyState strategyId={strategyId} />;
  }

  if (detailLoading) {
    return <StrategyDetailLoadingState />;
  }

  const missingStrategy = !strategy;
  if (detailError || missingStrategy) {
    return <StrategyDetailErrorState strategyId={strategyId} detailError={detailError} />;
  }

  const sampleStart = strategy.sample_start_date ?? paperNavRows[0]?.nav_date ?? null;
  const sampleEnd = strategy.sample_end_date ?? paperNavRows[paperNavRows.length - 1]?.nav_date ?? null;
  const sampleWindow = sampleStart && sampleEnd ? `${sampleStart} - ${sampleEnd}` : (sampleStart ?? sampleEnd ?? '-');
  const turnoverRate = latestIncubationMetric?.turnover_rate ?? null;
  const capacityValue = strategy.capacity ?? paperAccount?.total_value ?? latestPaperNav?.total_value ?? null;
  const capacityLabel = strategy.capacity_label ?? '当前模拟容量';
  const qualityGate = latestQualityReport?.quality_gate;
  const runCorrection = latestQualityReport?.run_correction;
  const multipleTestingMode = runCorrection?.multiple_testing_mode ?? qualityGate?.multiple_testing_mode ?? null;
  const deflatedSharpeRatio = firstFiniteNumber(
    runCorrection?.deflated_sharpe_ratio,
    qualityGate?.deflated_sharpe_ratio,
    runCorrection?.deflated_sharpe_proxy,
    qualityGate?.deflated_sharpe_proxy,
  );
  const pboValue = firstFiniteNumber(
    runCorrection?.pbo,
    qualityGate?.pbo,
    runCorrection?.pbo_proxy,
    qualityGate?.pbo_proxy,
  );
  const hansenSpaPvalue = firstFiniteNumber(
    runCorrection?.hansen_spa_pvalue,
    qualityGate?.hansen_spa_pvalue,
    runCorrection?.spa_pvalue_proxy,
    qualityGate?.spa_pvalue_proxy,
  );
  const whiteRealityCheckPvalue = firstFiniteNumber(
    runCorrection?.white_reality_check_pvalue,
    qualityGate?.white_reality_check_pvalue,
    runCorrection?.reality_check_pvalue_proxy,
    qualityGate?.reality_check_pvalue_proxy,
  );

  function applyView(snapshot: Record<string, unknown>) {
    if (typeof snapshot.activeTab === 'string' && DETAIL_TABS.some((item) => item.key === snapshot.activeTab)) {
      setActiveTab(snapshot.activeTab as StrategyDetailTab);
    }
    if (
      typeof snapshot.factorySection === 'string' &&
      FACTORY_SECTIONS.includes(snapshot.factorySection as FactoryReviewSection)
    ) {
      factoryPanelProps.onSectionChange(snapshot.factorySection as FactoryReviewSection);
      setActiveTab('factory');
    }
  }

  const primaryContent = (
    <div className="space-y-4 xl:h-full xl:overflow-y-auto xl:pr-1">
      {activeTab === 'overview' ? (
        <StrategyDetailOverviewTab
          allMetrics={allMetrics}
          metrics={metrics}
          reviews={reviews}
          navSeries={navSeries}
          navCategories={navCategories}
          factorBars={factorBars}
          incubationOverview={incubationOverview}
          latestQualityReport={latestQualityReport}
          incubationAccount={incubationAccount}
          latestIncubationMetric={latestIncubationMetric}
          openRiskEventsCount={openRiskEvents.length}
          vectorProfilesCount={vectorProfiles.length}
          highConfidenceQualityUiEnabled={highConfidenceQualityUiEnabled}
          promotionReady={promotionReady}
          strategyAvgRating={strategy.avg_rating}
          sampleWindow={sampleWindow}
          turnoverRate={turnoverRate}
          capacityLabel={capacityLabel}
          capacityValue={capacityValue}
          multipleTestingMode={multipleTestingMode}
          deflatedSharpeRatio={deflatedSharpeRatio}
          pboValue={pboValue}
          hansenSpaPvalue={hansenSpaPvalue}
          whiteRealityCheckPvalue={whiteRealityCheckPvalue}
          rating={rating}
          setRating={setRating}
          comment={comment}
          setComment={setComment}
          reviewPending={reviewPending}
          userId={userId}
          onReview={handleReview}
        />
      ) : null}
      {activeTab === 'tracking' ? <LiveTrackingPanel {...trackingPanelProps} /> : null}
      {activeTab === 'factory' ? <FactoryReviewPanel {...factoryPanelProps} /> : null}
    </div>
  );

  const secondaryContent = (
    <StrategyDetailSidebar
      strategyName={strategy.name}
      statusVariant={statusVariant}
      strategyStatus={strategy.status}
      promotionReady={promotionReady}
      sampleWindow={sampleWindow}
      subscriberCount={strategy.subscriber_count ?? 0}
      openRiskEventsCount={openRiskEvents.length}
      vectorProfilesCount={vectorProfiles.length}
      activeTab={activeTab}
      activeTabLabel={activeTabLabel}
      latestQualityGrade={latestQualityReport?.summary?.validation_grade}
      latestIncubationDecision={latestIncubationMetric?.decision ?? null}
      multipleTestingMode={multipleTestingMode}
      trackingTotalSignals={trackingPanelProps.stats?.total_signals ?? 0}
      trackingRealtime={trackingPanelProps.signals?.subscriber !== false}
      factoryActiveSection={factoryPanelProps.activeSection}
      factoryRuntimeAlertsCount={factoryPanelProps.runtimeAlerts.length}
      factoryTaskRunsCount={factoryPanelProps.taskRuns.length}
      deflatedSharpeRatio={deflatedSharpeRatio}
      pboValue={pboValue}
      hansenSpaPvalue={hansenSpaPvalue}
      whiteRealityCheckPvalue={whiteRealityCheckPvalue}
      capacityLabel={capacityLabel}
      capacityValue={capacityValue}
      onBackToMarket={() => router.push('/strategy-market')}
      onOpenPortfolio={() => router.push(portfolioHref)}
      onOpenPaper={() => router.push(paperHref)}
    />
  );

  return (
    <PageContainer className="space-y-4">
      <StrategyDetailHeroSection
        strategy={strategy}
        statusVariant={statusVariant}
        promotionReady={promotionReady}
        strategySummary={strategySummary}
        activeTab={activeTab}
        activeTabLabel={activeTabLabel}
        activeFactorySection={factoryPanelProps.activeSection}
        sampleStart={sampleStart}
        sampleWindow={sampleWindow}
        openRiskEventsCount={openRiskEvents.length}
        vectorProfilesCount={vectorProfiles.length}
        latestQualityGrade={latestQualityReport?.summary?.validation_grade}
        latestIncubationDecision={latestIncubationMetric?.decision ?? null}
        multipleTestingMode={multipleTestingMode}
        isSubscribed={isSubscribed}
        subscribePending={subscribePending}
        userId={userId}
        onAddToCart={addStrategyToCart}
        onSubscribe={handleSubscribe}
        onOpenPortfolio={() => router.push(portfolioHref)}
      />

      {!compactLayout ? (
        <WorkspaceToolbar pageKey={pageKey} currentView={currentView} onApplyView={applyView} supportsPagePanels />
      ) : null}
      <TabBar tabs={DETAIL_TABS} active={activeTab} onChange={setActiveTab} />
      <WorkspaceSplitLayout pageKey={pageKey} primary={primaryContent} secondary={secondaryContent} />
    </PageContainer>
  );
}
