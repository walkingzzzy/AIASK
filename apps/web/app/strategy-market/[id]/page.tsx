'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useParams, useRouter } from 'next/navigation';
import ResultWorkbench from '@/components/result-workbench';
import WorkspaceSplitLayout from '@/components/workspace-split-layout';
import WorkspaceToolbar from '@/components/workspace-toolbar';
import { PageContainer, TabBar } from '@/components/ui';
import { useMobile } from '@/hooks/use-mobile';
import { useApiMutation } from '@/hooks/use-api-mutation';
import { usePageActions } from '@/hooks/use-page-actions';
import { usePageContext } from '@/hooks/use-page-context';
import { apiKeys } from '@/lib/query-keys';
import { buildLocalResultContract, defaultWorkbenchTask, evidenceToSummary } from '@/lib/result-workbench';
import {
  DETAIL_TABS,
  FACTORY_SECTIONS,
  firstFiniteNumber,
} from '@/app/strategy-market/lib/strategy-detail-view';
import {
  resolveIncubationSurface,
  resolveMarketStatusMeta,
  resolveStrategyDisplayStatus,
} from '@/app/strategy-market/lib/incubation-surface';
import { useAuthStore } from '@/store/auth-store';
import { useCartStore } from '@/store/cart-store';
import { useWorkbenchStore } from '@/store/workbench-store';
import { CartDrawer } from '../components/CartDrawer';
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
  const user = useAuthStore((state) => state.user);
  const userId = user?.id ?? user?.username ?? null;
  const strategyId = params?.id ?? null;
  const emptyDetailContract = isSurfacePlaceholderId(strategyId);
  const [showCart, setShowCart] = useState(false);
  const editNameRef = useRef<HTMLInputElement | null>(null);
  const editDescriptionRef = useRef<HTMLTextAreaElement | null>(null);
  const editTagsRef = useRef<HTMLInputElement | null>(null);
  const editParamsTextRef = useRef<HTMLTextAreaElement | null>(null);
  const editFactorWeightsTextRef = useRef<HTMLTextAreaElement | null>(null);
  const updateStrategyApi = useApiMutation({ invalidates: [apiKeys.strategy()], successToast: '个人策略已更新' });
  const forkStrategyApi = useApiMutation({ invalidates: [apiKeys.strategy()], successToast: '已复制为我的策略' });
  const aiOptimizeApi = useApiMutation({ invalidates: [apiKeys.strategy()], successToast: 'AI 优化已完成' });
  const paperSessionApi = useApiMutation({ invalidates: [apiKeys.strategy()] });

  const {
    detailLoading,
    detailError,
    strategy,
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
    ownerState,
    paperSessionState,
    presentation,
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
  const latestIncubationPipelineSnapshot = factoryPanelProps.latestIncubationPipelineSnapshot;
  const displayStatus = resolveStrategyDisplayStatus({
    strategyStatus: strategy?.status,
    ownerState,
    paperSessionState,
  });
  const marketStatus = resolveMarketStatusMeta(strategy?.status);
  const incubationSurface = resolveIncubationSurface({
    strategyStatus: strategy?.status,
    incubationSurface: strategy?.incubation_surface,
    overview: incubationOverview,
    account: incubationAccount,
    latestMetric: latestIncubationMetric,
    latestPipelineSnapshot: latestIncubationPipelineSnapshot,
  });
  const showIncubationStage = !ownerState?.personal_strategy || incubationSurface.enteredIncubator;
  const strategySummary =
    presentation?.stage_summary ||
    strategy?.description ||
    '先确认策略合同、质量门状态和当前孵化决策，再决定是加入组合、继续收藏，还是转到工厂审查继续追踪。';
  const portfolioHref = '/portfolio?from=strategy-detail';

  const currentView = useMemo(
    () => ({
      strategyId: strategy?.id ?? strategyId ?? null,
      activeTab,
      factorySection: factoryPanelProps.activeSection,
      favorited: isSubscribed,
      ownerState: ownerState?.kind ?? null,
    }),
    [activeTab, factoryPanelProps.activeSection, isSubscribed, ownerState?.kind, strategy?.id, strategyId],
  );

  useEffect(() => {
    if (!strategy) return;
    updateWorkbenchContext({
      strategyId: String(strategy.id),
      strategyName: strategy.name,
    });
  }, [strategy, updateWorkbenchContext]);

  function addStrategyToCart() {
    if (!strategy) return;
    addToCart({ strategyId: strategy.id, name: strategy.name, weight: 0 });
    updateWorkbenchContext({
      strategyId: String(strategy.id),
      strategyName: strategy.name,
    });
    setShowCart(true);
  }

  const handleOpenPaperSession = useCallback(async () => {
    if (!strategy) return;
    const payload = await paperSessionApi.triggerAsync(
      `/strategy-market/${strategy.id}/paper-session`,
      { method: 'POST' },
      {},
    );
    const record = payload && typeof payload === 'object' ? payload as Record<string, unknown> : {};
    const session = record.session && typeof record.session === 'object' ? record.session as Record<string, unknown> : {};
    const account = record.account && typeof record.account === 'object' ? record.account as Record<string, unknown> : {};
    const accountId = String(account.id ?? session.account_id ?? '').trim();
    updateWorkbenchContext({
      strategyId: String(strategy.id),
      strategyName: strategy.name,
      linkedStrategyId: String(strategy.id),
      linkedStrategyName: strategy.name,
      accountId: accountId || null,
      mode: 'personal-strategy',
      strategyTestMode: 'personal-strategy',
    });
    const qs = new URLSearchParams({
      from: 'strategy-detail',
      strategy_id: String(strategy.id),
      mode: 'personal-strategy',
      ...(accountId ? { account_id: accountId } : {}),
    });
    router.push(`/paper-trading?${qs.toString()}`);
  }, [paperSessionApi, router, strategy, updateWorkbenchContext]);

  const handleForkToPersonal = useCallback(async () => {
    if (!strategy) return;
    const payload = await forkStrategyApi.triggerAsync(
      `/strategy-market/${strategy.id}/fork`,
      { method: 'POST' },
      {},
    );
    const nextId = String((payload as Record<string, unknown> | null)?.strategy_id ?? '').trim();
    if (nextId) {
      router.push(`/strategy-market/${encodeURIComponent(nextId)}`);
    }
  }, [forkStrategyApi, router, strategy]);

  const handleAiOptimizePersonalStrategy = useCallback(async () => {
    if (!strategy) return;
    await aiOptimizeApi.triggerAsync(`/strategy-market/${strategy.id}/ai-optimize`, { method: 'POST' }, {});
  }, [aiOptimizeApi, strategy]);

  const savePersonalStrategy = useCallback(async () => {
    if (!strategy) {
      throw new Error('当前策略尚未加载完成');
    }
    const params = JSON.parse(editParamsTextRef.current?.value || '{}') as Record<string, unknown>;
    const factor_weights = JSON.parse(editFactorWeightsTextRef.current?.value || '{}') as Record<string, number>;
    const tags = (editTagsRef.current?.value ?? '')
      .split(',')
      .map((item) => item.trim())
      .filter(Boolean);
    await updateStrategyApi.triggerAsync(
      `/strategy-market/${strategy.id}`,
      { method: 'PATCH' },
      {
        name: editNameRef.current?.value?.trim() || strategy.name,
        description: editDescriptionRef.current?.value?.trim() ?? '',
        params,
        factor_weights,
        tags,
      },
    );
  }, [strategy, updateStrategyApi]);

  async function handleSavePersonalStrategy() {
    try {
      await savePersonalStrategy();
    } catch (error) {
      window.alert(`个人策略保存失败：${String(error instanceof Error ? error.message : error)}`);
    }
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
        label: isSubscribed ? '取消收藏策略' : '收藏策略',
        description: '切换当前策略的收藏状态',
        keywords: ['收藏', '策略'],
        scope: 'page' as const,
        pageKey,
        run: async () => {
          if (!strategy) throw new Error('当前策略尚未加载完成');
          if (!userId) throw new Error('请先登录后再收藏策略');
          await handleSubscribe();
          return { message: isSubscribed ? `已取消收藏 ${strategy.name}` : `已收藏 ${strategy.name}` };
        },
      },
      {
        id: 'strategy-detail.add-to-portfolio',
        label: '加入组合购物车',
        description: '将当前策略加入组合购物车并打开购物车',
        keywords: ['加入组合', '购物车'],
        scope: 'page' as const,
        pageKey,
        run: () => {
          if (!strategy) throw new Error('当前策略尚未加载完成');
          addToCart({ strategyId: strategy.id, name: strategy.name, weight: 0 });
          updateWorkbenchContext({
            strategyId: String(strategy.id),
            strategyName: strategy.name,
          });
          setShowCart(true);
          return { message: `已把 ${strategy.name} 加入组合购物车` };
        },
      },
      {
        id: 'strategy-detail.open-paper',
        label: paperSessionState?.has_session ? '打开我的模拟盘测试' : '创建模拟盘测试',
        description: '为当前策略打开或创建个人模拟盘测试账户',
        keywords: ['模拟盘', 'paper'],
        scope: 'page' as const,
        pageKey,
        run: async () => {
          await handleOpenPaperSession();
          return { message: paperSessionState?.has_session ? '已打开个人模拟盘测试' : '已创建并打开个人模拟盘测试' };
        },
      },
      ...(userId && !ownerState?.editable
        ? [{
            id: 'strategy-detail.fork-personal',
            label: '复制为我的策略',
            description: '把当前市场策略复制成个人草稿',
            keywords: ['复制', '我的策略'],
            scope: 'page' as const,
            pageKey,
            run: async () => {
              await handleForkToPersonal();
              return { message: `已复制 ${strategy?.name ?? '当前策略'} 为个人策略` };
            },
          }]
        : []),
      ...(ownerState?.editable
        ? [{
            id: 'strategy-detail.save-personal',
            label: '保存我的策略',
            description: '保存当前个人策略草稿的名称、描述、参数与因子权重',
            keywords: ['保存', '个人策略', '草稿'],
            scope: 'page' as const,
            pageKey,
            run: async () => {
              await savePersonalStrategy();
              return { message: `已保存 ${strategy?.name ?? '当前策略'} 的个人草稿` };
            },
          },
          {
            id: 'strategy-detail.ai-optimize',
            label: 'AI 优化我的策略',
            description: '用现有 AI 实验链路优化当前个人策略',
            keywords: ['AI', '优化'],
            scope: 'page' as const,
            pageKey,
            run: async () => {
              await handleAiOptimizePersonalStrategy();
              return { message: `已触发 ${strategy?.name ?? '当前策略'} 的 AI 优化` };
            },
          }]
        : []),
    ],
    [
      addToCart,
      emptyDetailContract,
      handleAiOptimizePersonalStrategy,
      handleForkToPersonal,
      handleOpenPaperSession,
      handleSubscribe,
      isSubscribed,
      ownerState?.editable,
      pageKey,
      paperSessionState?.has_session,
      router,
      savePersonalStrategy,
      setActiveTab,
      strategy,
      updateWorkbenchContext,
      userId,
    ],
  );

  usePageActions(pageActions);

  const strategyDetailSummary = emptyDetailContract
      ? '当前环境还没有可进入的策略详情数据，页面按空态契约渲染。'
      : strategy
      ? `${strategy.name} 当前处于 ${displayStatus.label}，市场状态 ${marketStatus.label}，${showIncubationStage ? `孵化阶段 ${incubationSurface.stage.label}` : '暂未进入真实孵化链路'}，当前工作流为 ${activeTabLabel}。收藏数 ${strategy.subscriber_count ?? 0}，风险事件 ${openRiskEvents.length}，向量画像 ${vectorProfiles.length}。`
      : detailLoading
        ? '策略详情加载中。'
        : detailError
          ? '策略详情暂时无法加载。'
          : '策略详情待初始化。';
  const strategyDetailResult = useMemo(
    () =>
      buildLocalResultContract({
        summary: strategyDetailSummary,
        availableViews: activeTab === 'factory' ? ['visual'] : [],
        pageActions,
        preferredActionIds: emptyDetailContract
          ? ['strategy-detail.empty.open-market', 'strategy-detail.empty.reload']
          : ['strategy-detail.switch.overview', 'strategy-detail.switch.factory', 'strategy-detail.open-paper'],
        recommendedLinks: [
          { id: 'strategy-detail-link-market', label: '返回策略超市', href: '/strategy-market' },
          {
            id: 'strategy-detail-link-paper',
            label: '模拟盘测试',
            href: strategy ? `/paper-trading?from=strategy-detail&strategy_id=${encodeURIComponent(String(strategy.id))}` : '/paper-trading?from=strategy-detail',
          },
          {
            id: 'strategy-detail-link-portfolio',
            label: '策略组合页',
            href: portfolioHref,
          },
          {
            id: 'strategy-detail-link-copilot',
            label: '继续追问 Copilot',
            href: strategy ? `/assistant?symbol=${encodeURIComponent(strategy.name)}` : '/assistant?from=strategy-detail',
          },
        ],
        evidence: [
          { label: '当前标签', value: activeTabLabel },
          { label: '当前状态', value: displayStatus.label },
          { label: '市场状态', value: marketStatus.label },
          { label: '孵化阶段', value: showIncubationStage ? incubationSurface.stage.label : '未接入真实孵化' },
          { label: '收藏数', value: String(strategy?.subscriber_count ?? 0) },
          { label: '风险事件', value: String(openRiskEvents.length), tone: openRiskEvents.length > 0 ? 'warning' : 'neutral' },
          { label: '向量画像', value: String(vectorProfiles.length) },
          { label: '质量评级', value: String(latestQualityReport?.summary?.validation_grade ?? '-') },
        ],
        riskNotes: [
          ...(emptyDetailContract ? ['当前是策略详情空态契约，建议先回到策略超市重新筛选。'] : []),
          ...(!incubationSurface.promotionReady && strategy ? ['当前策略尚未达到晋级条件，进入组合前需要继续看质量门与运行风控。'] : []),
          ...(openRiskEvents.length > 0 ? [`当前存在 ${openRiskEvents.length} 个未关闭风险事件。`] : []),
          ...(detailError ? [detailError] : []),
        ],
        freshness: null,
        platformMeta: {
          sourceTool: 'strategy-market/detail',
          sourceChain: ['strategy-market', 'strategy-detail'],
          degraded: emptyDetailContract || Boolean(detailError),
          fallbackReason: [detailError].filter((item): item is string => Boolean(item)),
        },
        workbenchTask: defaultWorkbenchTask(
          'strategy-detail',
          strategy ? `复查策略 ${strategy.name}` : '复查策略详情',
          strategy ? `/strategy-market/${encodeURIComponent(String(strategy.id))}` : '/strategy-market',
          'strategy-detail-review',
          {
            strategyId: strategy?.id ?? strategyId ?? null,
            activeTab,
            factorySection: factoryPanelProps.activeSection,
          },
        ),
      }),
    [
      activeTab,
      activeTabLabel,
      detailError,
      detailLoading,
      emptyDetailContract,
      factoryPanelProps.activeSection,
      displayStatus.label,
      incubationSurface.promotionReady,
      incubationSurface.stage.label,
      latestQualityReport?.summary?.validation_grade,
      marketStatus.label,
      openRiskEvents.length,
      pageActions,
      portfolioHref,
      showIncubationStage,
      strategy,
      strategyDetailSummary,
      strategyId,
      vectorProfiles.length,
    ],
  );

  usePageContext({
    pageKey,
    title: emptyDetailContract
      ? '策略详情空态'
      : strategy?.name ? `策略详情 · ${strategy.name}` : '策略详情',
    summary: strategyDetailSummary,
    objectType: 'strategy',
    objectId: String(strategy?.id ?? strategyId ?? 'strategy-detail'),
    resultType: 'strategy-detail',
    tags: [
      emptyDetailContract ? '空态契约' : null,
      strategy?.status ? marketStatus.label : null,
      activeTabLabel,
      showIncubationStage ? incubationSurface.stage.label : '未入孵化',
      strategy?.author_id ? `作者 ${strategy.author_id}` : null,
      strategy?.subscriber_count != null ? `${strategy.subscriber_count} 收藏` : null,
      latestQualityReport?.summary?.validation_grade ? `评级 ${latestQualityReport.summary.validation_grade}` : null,
    ].filter((item): item is string => Boolean(item)),
    suggestions: emptyDetailContract
      ? ['返回策略超市', '运行工厂生成策略', '稍后重新加载详情页']
      : strategy
        ? [
            activeTab === 'overview' ? '切到实盘跟踪看信号与命中率' : '回概览确认样本期和质量门',
            activeTab === 'factory' ? '继续切换工厂审查分区' : '打开工厂审查看运行风控与实验事件',
            isSubscribed ? '取消收藏策略并返回列表继续筛选' : '收藏该策略并纳入后续跟踪',
          ]
        : ['返回策略超市', '重新加载策略详情'],
    recommendedActions: strategyDetailResult.recommendedActions ?? [],
    recommendedLinks: strategyDetailResult.recommendedLinks ?? [],
    evidenceSummary: evidenceToSummary(strategyDetailResult.evidence),
    riskNotes: strategyDetailResult.riskNotes ?? [],
    freshness: strategyDetailResult.freshness ?? null,
    raw: {
      strategyId: emptyDetailContract ? null : strategy?.id ?? strategyId ?? null,
      emptyDetailContract,
      activeTab,
      factorySection: factoryPanelProps.activeSection,
      favorited: isSubscribed,
      riskEvents: openRiskEvents.length,
      vectorProfiles: vectorProfiles.length,
      promotionReady: incubationSurface.promotionReady,
      marketStatus: marketStatus.label,
      incubationStage: incubationSurface.stage.label,
      ownerState,
      paperSessionState,
    },
  });

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
      {ownerState?.editable ? (
        <section key={String(strategy.id)} className="panel-soft rounded-[24px] p-4 sm:p-5">
          <div className="eyebrow">个人策略编辑</div>
          <h3 className="mt-2 mb-0 text-lg font-semibold text-text-primary">当前策略可直接编辑</h3>
          <p className="mt-2 text-sm text-text-secondary">
            修改名称、描述、参数与因子权重后会直接保存到你的个人策略草稿，不会影响市场策略。当前页 Copilot 也能直接执行保存、AI 优化和模拟盘动作。
          </p>
          <div className="mt-4 grid gap-3">
            <input
              ref={editNameRef}
              defaultValue={strategy.name ?? ''}
              placeholder="策略名称"
              className="w-full rounded-[16px] border border-border bg-surface px-3 py-2 text-sm"
            />
            <textarea
              ref={editDescriptionRef}
              defaultValue={strategy.description ?? ''}
              placeholder="策略描述"
              rows={3}
              className="w-full rounded-[16px] border border-border bg-surface px-3 py-2 text-sm"
            />
            <input
              ref={editTagsRef}
              defaultValue={Array.isArray(strategy.tags) ? strategy.tags.join(', ') : ''}
              placeholder="标签，逗号分隔"
              className="w-full rounded-[16px] border border-border bg-surface px-3 py-2 text-sm"
            />
            <textarea
              ref={editParamsTextRef}
              defaultValue={JSON.stringify(strategy.params ?? {}, null, 2)}
              placeholder="策略参数 JSON"
              rows={8}
              className="w-full rounded-[16px] border border-border bg-surface px-3 py-2 font-mono text-xs"
            />
            <textarea
              ref={editFactorWeightsTextRef}
              defaultValue={JSON.stringify(strategy.factor_weights ?? {}, null, 2)}
              placeholder="因子权重 JSON"
              rows={6}
              className="w-full rounded-[16px] border border-border bg-surface px-3 py-2 font-mono text-xs"
            />
            <div className="flex flex-wrap gap-2">
              <button
                type="button"
                onClick={() => void handleSavePersonalStrategy()}
                disabled={updateStrategyApi.isPending}
                className="rounded-full bg-primary px-4 py-2 text-sm text-white"
              >
                {updateStrategyApi.isPending ? '保存中...' : '保存个人策略'}
              </button>
              <button
                type="button"
                onClick={() => void handleAiOptimizePersonalStrategy()}
                disabled={aiOptimizeApi.isPending}
                className="rounded-full border border-border bg-surface px-4 py-2 text-sm"
              >
                {aiOptimizeApi.isPending ? 'AI 优化中...' : 'AI 优化我的策略'}
              </button>
              <button
                type="button"
                onClick={() => void handleOpenPaperSession()}
                disabled={paperSessionApi.isPending}
                className="rounded-full border border-border bg-surface px-4 py-2 text-sm"
              >
                {paperSessionApi.isPending ? '处理中...' : (paperSessionState?.has_session ? '打开我的模拟盘测试' : '创建模拟盘测试')}
              </button>
            </div>
          </div>
        </section>
      ) : null}
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
          latestIncubationPipelineSnapshot={latestIncubationPipelineSnapshot}
          openRiskEventsCount={openRiskEvents.length}
          vectorProfilesCount={vectorProfiles.length}
          highConfidenceQualityUiEnabled={highConfidenceQualityUiEnabled}
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
      displayStatus={displayStatus}
      marketStatus={marketStatus}
      incubationStage={incubationSurface.stage}
      showIncubationStage={showIncubationStage}
      promotionReady={incubationSurface.promotionReady}
      sampleWindow={sampleWindow}
      subscriberCount={strategy.subscriber_count ?? 0}
      openRiskEventsCount={openRiskEvents.length}
      vectorProfilesCount={vectorProfiles.length}
      activeTab={activeTab}
      activeTabLabel={activeTabLabel}
      latestQualityGrade={latestQualityReport?.summary?.validation_grade}
      latestIncubationDecision={incubationSurface.latestDecision.label}
      executionAuditGate={incubationSurface.executionAuditGate.label}
      blockerCount={incubationSurface.blockerCount}
      riskCount={incubationSurface.riskCount}
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
      onOpenPaper={() => void handleOpenPaperSession()}
    />
  );

  return (
    <PageContainer className="space-y-4">
      <StrategyDetailHeroSection
        strategy={strategy}
        displayStatus={displayStatus}
        marketStatus={marketStatus}
        incubationStage={incubationSurface.stage}
        showIncubationStage={showIncubationStage}
        promotionReady={incubationSurface.promotionReady}
        strategySummary={strategySummary}
        activeTab={activeTab}
        activeTabLabel={activeTabLabel}
        activeFactorySection={factoryPanelProps.activeSection}
        sampleStart={sampleStart}
        sampleWindow={sampleWindow}
        openRiskEventsCount={openRiskEvents.length}
        vectorProfilesCount={vectorProfiles.length}
        latestQualityGrade={latestQualityReport?.summary?.validation_grade}
        latestIncubationDecision={incubationSurface.latestDecision.label}
        executionAuditGate={incubationSurface.executionAuditGate.label}
        blockerCount={incubationSurface.blockerCount}
        riskCount={incubationSurface.riskCount}
        multipleTestingMode={multipleTestingMode}
        isSubscribed={isSubscribed}
        subscribePending={subscribePending}
        userId={userId}
        onAddToCart={addStrategyToCart}
        onSubscribe={handleSubscribe}
        onOpenPortfolio={() => router.push(portfolioHref)}
        onOpenPaperSession={() => void handleOpenPaperSession()}
      />

      <ResultWorkbench
        pageKey="strategy-detail"
        title="策略详情结果工作台"
        result={strategyDetailResult}
      />

      {!ownerState?.editable && userId ? (
        <section className="panel-soft rounded-[22px] px-4 py-3">
          <div className="flex flex-wrap items-center gap-2">
            <div className="text-sm text-text-secondary">
              {presentation?.recommended_action ?? '你可以先收藏、复制为个人策略，或直接拉起个人模拟盘测试。'}
            </div>
            <div className="ml-auto flex flex-wrap gap-2">
              <button
                type="button"
                onClick={() => void handleForkToPersonal()}
                disabled={forkStrategyApi.isPending}
                className="rounded-full border border-border bg-surface px-4 py-2 text-sm"
              >
                {forkStrategyApi.isPending ? '复制中...' : '复制为我的策略'}
              </button>
              <button
                type="button"
                onClick={() => void handleOpenPaperSession()}
                disabled={paperSessionApi.isPending}
                className="rounded-full border border-border bg-surface px-4 py-2 text-sm"
              >
                {paperSessionApi.isPending ? '处理中...' : (paperSessionState?.has_session ? '打开我的模拟盘测试' : '创建模拟盘测试')}
              </button>
            </div>
          </div>
        </section>
      ) : null}

      {!compactLayout ? (
        <WorkspaceToolbar pageKey={pageKey} currentView={currentView} onApplyView={applyView} supportsPagePanels />
      ) : null}
      <TabBar tabs={DETAIL_TABS} active={activeTab} onChange={setActiveTab} />
      <WorkspaceSplitLayout pageKey={pageKey} primary={primaryContent} secondary={secondaryContent} />
      {showCart ? <CartDrawer onClose={() => setShowCart(false)} /> : null}
    </PageContainer>
  );
}
