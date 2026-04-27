'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useParams, useRouter, useSearchParams } from 'next/navigation';
import ProgressiveWorkbenchSection from '@/components/progressive-workbench-section';
import WorkspaceSplitLayout from '@/components/workspace-split-layout';
import { PageContainer, TabBar } from '@/components/ui';
import { useMobile } from '@/hooks/use-mobile';
import { useApiMutation } from '@/hooks/use-api-mutation';
import { useApiQuery } from '@/hooks/use-api-query';
import { usePageActions } from '@/hooks/use-page-actions';
import { usePageContext } from '@/hooks/use-page-context';
import type { CopilotActionPayload } from '@/lib/copilot-types';
import { apiKeys } from '@/lib/query-keys';
import { buildLocalResultContract, defaultWorkbenchTask, evidenceToSummary } from '@/lib/result-workbench';
import {
  DETAIL_TABS,
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
import { StrategyRuntimeActionBar } from '../components/StrategyRuntimeActionBar';
import {
  StrategyDetailErrorState,
  StrategyDetailEmptyState,
  StrategyDetailLoadingState,
} from '../components/StrategyDetailStatusState';
import { useStrategyDetailPage } from '../hooks/use-strategy-detail-page';
import { isSurfacePlaceholderId } from '@/lib/surface-contracts';
import { RESPONSIVE_BREAKPOINTS } from '@/lib/responsive-layout';
import type { StrategyRuntimeActionContractItem, StrategyRuntimeActionId } from '../types';

type PersonalStrategyContextResponse = {
  strategy_id?: string;
  strategy_name?: string;
  editable?: boolean;
  personal_strategy?: boolean;
  mutation_guard?: {
    allowed?: boolean;
    reason?: string | null;
  };
  draft_snapshot?: {
    name?: string;
    description?: string;
    params?: Record<string, unknown>;
    factor_weights?: Record<string, number>;
    tags?: string[];
  };
  draft_stats?: {
    description_present?: boolean;
    tag_count?: number;
    param_key_count?: number;
    factor_weight_key_count?: number;
  };
  action_modes?: Array<{
    action_kind?: string;
    effect?: string;
    available?: boolean;
    label?: string;
    reason?: string | null;
  }>;
};

type PersonalStrategySuggestionResponse = {
  strategy_id?: string;
  advisory_only?: boolean;
  persisted?: boolean;
  summary?: string;
  changed_fields?: string[];
  apply_payload?: {
    name?: string;
    description?: string;
    params?: Record<string, unknown>;
    factor_weights?: Record<string, number>;
    tags?: string[];
  };
  suggestions?: Array<{
    field?: string;
    reason?: string;
    before?: unknown;
    after?: unknown;
  }>;
  risk_notes?: string[];
  context?: PersonalStrategyContextResponse | null;
  strategy?: Record<string, unknown> | null;
  post_update_pipeline?: {
    requested?: boolean;
    overall_status?: string;
  } | null;
};

function normalizeSuggestionPayload(payload: Record<string, unknown> | undefined) {
  const instructions = typeof payload?.instructions === 'string' ? payload.instructions.trim() : '';
  const objective = typeof payload?.objective === 'string' ? payload.objective.trim() : '';
  const rawFocusFields = Array.isArray(payload?.focus_fields)
    ? payload?.focus_fields
    : Array.isArray(payload?.focusFields)
      ? payload?.focusFields
      : typeof payload?.focus_fields === 'string'
        ? payload.focus_fields.split(',')
        : typeof payload?.focusFields === 'string'
          ? payload.focusFields.split(',')
          : [];
  const focus_fields = rawFocusFields
    .filter((item): item is string => typeof item === 'string')
    .map((item) => item.trim())
    .filter(Boolean);
  return {
    objective: objective || undefined,
    instructions: instructions || undefined,
    focus_fields: focus_fields.length ? focus_fields : undefined,
  };
}

export default function StrategyDetailPage() {
  const compactLayout = useMobile(RESPONSIVE_BREAKPOINTS.splitCollapse);
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const searchParams = useSearchParams();
  const addToCart = useCartStore((state) => state.addStrategy);
  const updateWorkbenchContext = useWorkbenchStore((state) => state.updateContext);
  const user = useAuthStore((state) => state.user);
  const userId = user?.id ?? user?.username ?? null;
  const strategyId = params?.id ?? null;
  const emptyDetailContract = isSurfacePlaceholderId(strategyId);
  const [showCart, setShowCart] = useState(false);
  const [pendingRuntimeActionId, setPendingRuntimeActionId] = useState<StrategyRuntimeActionId | null>(null);
  const editNameRef = useRef<HTMLInputElement | null>(null);
  const editDescriptionRef = useRef<HTMLTextAreaElement | null>(null);
  const editTagsRef = useRef<HTMLInputElement | null>(null);
  const editParamsTextRef = useRef<HTMLTextAreaElement | null>(null);
  const editFactorWeightsTextRef = useRef<HTMLTextAreaElement | null>(null);
  const updateStrategyApi = useApiMutation({ invalidates: [apiKeys.strategy()], successToast: '个人策略已更新' });
  const forkStrategyApi = useApiMutation({ invalidates: [apiKeys.strategy()], successToast: '已复制为我的策略' });
  const aiSuggestionApi = useApiMutation<PersonalStrategySuggestionResponse>({ successToast: 'AI 修改建议已生成' });
  const aiOptimizeApi = useApiMutation({ invalidates: [apiKeys.strategy()], successToast: 'AI 优化已完成' });
  const paperSessionApi = useApiMutation({ invalidates: [apiKeys.strategy()] });
  const personalStrategyContextQ = useApiQuery<PersonalStrategyContextResponse>(
    strategyId && userId ? `/strategy-market/${strategyId}/personal-context` : null,
    {
      enabled: Boolean(strategyId && userId),
      nonFatal: true,
    },
  );

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
    paperContext,
    paperAccount,
    latestPaperNav,
    paperNavRows,
    openRiskEvents,
    vectorProfiles,
    highConfidenceQualityUiEnabled,
    ownerState,
    paperSessionState,
    presentation,
    runtimeActionContract,
    rating,
    setRating,
    comment,
    setComment,
    isSubscribed,
    reviewPending,
    handleSubscribe,
    handleReview,
  } = overview;
  const localPersonalStrategyContext = useMemo<PersonalStrategyContextResponse | null>(
    () => (strategy
      ? {
          strategy_id: String(strategy.id),
          strategy_name: strategy.name,
          editable: Boolean(ownerState?.editable),
          personal_strategy: Boolean(ownerState?.personal_strategy),
          mutation_guard: {
            allowed: Boolean(ownerState?.editable),
            reason: ownerState?.editable ? null : '当前不是你的个人策略草稿，不能直接写入。',
          },
          draft_snapshot: {
            name: strategy.name,
            description: strategy.description ?? '',
            params: (strategy.params ?? {}) as Record<string, unknown>,
            factor_weights: (strategy.factor_weights ?? {}) as Record<string, number>,
            tags: Array.isArray(strategy.tags) ? strategy.tags : [],
          },
          draft_stats: {
            description_present: Boolean(strategy.description?.trim()),
            tag_count: Array.isArray(strategy.tags) ? strategy.tags.length : 0,
            param_key_count: Object.keys((strategy.params ?? {}) as Record<string, unknown>).length,
            factor_weight_key_count: Object.keys((strategy.factor_weights ?? {}) as Record<string, number>).length,
          },
          action_modes: [
            {
              action_kind: 'view',
              effect: 'readonly',
              available: true,
              label: '查看当前个人策略上下文',
            },
            {
              action_kind: 'generate_update_suggestion',
              effect: 'advisory',
              available: Boolean(ownerState?.editable),
              label: '生成修改建议',
            },
            {
              action_kind: 'optimize',
              effect: 'stateful',
              available: Boolean(ownerState?.editable),
              label: '执行 AI 优化',
            },
            {
              action_kind: 'persist_update',
              effect: 'stateful',
              available: Boolean(ownerState?.editable),
              label: '保存到个人策略草稿',
            },
          ],
        }
      : null),
    [ownerState?.editable, ownerState?.personal_strategy, strategy],
  );
  const personalStrategyContext = aiSuggestionApi.data?.context
    ?? personalStrategyContextQ.data
    ?? localPersonalStrategyContext;
  const latestAiSuggestion = aiSuggestionApi.data;
  const runtimeActionLookup = useMemo(
    () => new Map((runtimeActionContract?.actions ?? []).map((action) => [action.id, action])),
    [runtimeActionContract],
  );
  const aiModifyPersonalAction = runtimeActionLookup.get('ai_modify_personal_strategy') ?? null;
  const paperSessionAction = runtimeActionLookup.get('open_personal_paper_session') ?? null;

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

  useEffect(() => {
    if (!strategy) return;
    updateWorkbenchContext({
      strategyId: String(strategy.id),
      strategyName: strategy.name,
    });
  }, [strategy, updateWorkbenchContext]);

  useEffect(() => {
    const tab = searchParams?.get('tab');
    if (tab === 'overview' || tab === 'tracking' || tab === 'factory') {
      setActiveTab(tab);
    }
  }, [searchParams, setActiveTab, strategyId]);

  const syncDraftEditors = useCallback((nextDraft: {
    name?: unknown;
    description?: unknown;
    params?: unknown;
    factor_weights?: unknown;
    tags?: unknown;
  }) => {
    if (editNameRef.current && typeof nextDraft.name === 'string') {
      editNameRef.current.value = nextDraft.name;
    }
    if (editDescriptionRef.current && typeof nextDraft.description === 'string') {
      editDescriptionRef.current.value = nextDraft.description;
    }
    if (editTagsRef.current && Array.isArray(nextDraft.tags)) {
      editTagsRef.current.value = nextDraft.tags
        .filter((item): item is string => typeof item === 'string')
        .join(', ');
    }
    if (editParamsTextRef.current && nextDraft.params && typeof nextDraft.params === 'object' && !Array.isArray(nextDraft.params)) {
      editParamsTextRef.current.value = JSON.stringify(nextDraft.params, null, 2);
    }
    if (
      editFactorWeightsTextRef.current
      && nextDraft.factor_weights
      && typeof nextDraft.factor_weights === 'object'
      && !Array.isArray(nextDraft.factor_weights)
    ) {
      editFactorWeightsTextRef.current.value = JSON.stringify(nextDraft.factor_weights, null, 2);
    }
  }, []);

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

  const handleAiOptimizePersonalStrategy = useCallback(async (payload?: Record<string, unknown>) => {
    if (!strategy) return;
    const response = await aiOptimizeApi.triggerAsync(
      `/strategy-market/${strategy.id}/ai-optimize`,
      { method: 'POST' },
      normalizeSuggestionPayload(payload),
    ) as Record<string, unknown> | null;
    const nextStrategy = response?.strategy;
    if (nextStrategy && typeof nextStrategy === 'object' && !Array.isArray(nextStrategy)) {
      syncDraftEditors(nextStrategy as Record<string, unknown>);
    }
    aiSuggestionApi.reset();
    return response;
  }, [aiOptimizeApi, aiSuggestionApi, strategy, syncDraftEditors]);

  const handleAiSuggestPersonalStrategy = useCallback(async (payload?: Record<string, unknown>) => {
    if (!strategy) return null;
    const response = await aiSuggestionApi.triggerAsync(
      `/strategy-market/${strategy.id}/ai-modification-suggestions`,
      { method: 'POST' },
      normalizeSuggestionPayload(payload),
    );
    const nextStrategy = (response as PersonalStrategySuggestionResponse | null)?.strategy;
    if (nextStrategy && typeof nextStrategy === 'object' && !Array.isArray(nextStrategy)) {
      syncDraftEditors(nextStrategy);
    }
    return response;
  }, [aiSuggestionApi, strategy, syncDraftEditors]);

  const applyLatestAiSuggestion = useCallback(async (payload?: Record<string, unknown>) => {
    if (!strategy) {
      throw new Error('当前策略尚未加载完成');
    }
    const normalizedPayload = normalizeSuggestionPayload(payload);
    const hasInlineRequest = Object.keys(normalizedPayload).length > 0;
    const applyPayload = latestAiSuggestion?.apply_payload;
    if (hasInlineRequest || !applyPayload || Object.keys(applyPayload).length === 0) {
      const response = await aiSuggestionApi.triggerAsync(
        `/strategy-market/${strategy.id}/ai-modification-suggestions`,
        { method: 'POST' },
        {
          ...normalizedPayload,
          persist: true,
          run_post_update_pipeline: false,
        },
      ) as PersonalStrategySuggestionResponse | null;
      const nextStrategy = response?.strategy;
      if (nextStrategy && typeof nextStrategy === 'object' && !Array.isArray(nextStrategy)) {
        syncDraftEditors(nextStrategy);
      }
      aiSuggestionApi.reset();
      return response;
    }
    const response = await updateStrategyApi.triggerAsync(
      `/strategy-market/${strategy.id}`,
      { method: 'PATCH' },
      {
        ...applyPayload,
        mutationScope: 'draft',
      },
    ) as Record<string, unknown> | null;
    const nextStrategy = response?.strategy;
    if (nextStrategy && typeof nextStrategy === 'object' && !Array.isArray(nextStrategy)) {
      syncDraftEditors(nextStrategy as Record<string, unknown>);
    } else {
      syncDraftEditors(applyPayload);
    }
    aiSuggestionApi.reset();
    return response;
  }, [aiSuggestionApi, latestAiSuggestion?.apply_payload, strategy, syncDraftEditors, updateStrategyApi]);

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
    const response = await updateStrategyApi.triggerAsync(
      `/strategy-market/${strategy.id}`,
      { method: 'PATCH' },
      {
        mutationScope: 'draft',
        name: editNameRef.current?.value?.trim() || strategy.name,
        description: editDescriptionRef.current?.value?.trim() ?? '',
        params,
        factor_weights,
        tags,
      },
    ) as Record<string, unknown> | null;
    const nextStrategy = response?.strategy;
    if (nextStrategy && typeof nextStrategy === 'object' && !Array.isArray(nextStrategy)) {
      syncDraftEditors(nextStrategy as Record<string, unknown>);
    }
    aiSuggestionApi.reset();
    return response;
  }, [aiSuggestionApi, strategy, syncDraftEditors, updateStrategyApi]);

  async function handleSavePersonalStrategy() {
    try {
      await savePersonalStrategy();
    } catch (error) {
      window.alert(`个人策略保存失败：${String(error instanceof Error ? error.message : error)}`);
    }
  }

  const executeRuntimeAction = useCallback(async (action: StrategyRuntimeActionContractItem) => {
    if (action.status === 'unavailable') {
      window.alert(action.unavailable_reason ?? '当前动作不可用');
      return;
    }
    if (action.requires_confirmation) {
      const confirmed = window.confirm(action.confirm?.message ?? `确认执行“${action.label}”？`);
      if (!confirmed) return;
    }
    setPendingRuntimeActionId(action.id);
    try {
      if (action.id === 'view_factory_source') {
        setActiveTab('factory');
        if (action.navigation?.href) {
          router.push(action.navigation.href);
        }
        return;
      }
      if (action.id === 'ai_analyze_strategy' && action.navigation?.href) {
        router.push(action.navigation.href);
        return;
      }
      if (action.id === 'save_as_personal_strategy') {
        await handleForkToPersonal();
        return;
      }
      if (action.id === 'open_personal_paper_session') {
        await handleOpenPaperSession();
        return;
      }
      if (action.id === 'ai_modify_personal_strategy') {
        await handleAiOptimizePersonalStrategy(action.endpoint?.body ?? undefined);
        return;
      }
      if (action.navigation?.href) {
        router.push(action.navigation.href);
        return;
      }
      throw new Error('动作合同缺少前端执行器');
    } finally {
      setPendingRuntimeActionId(null);
    }
  }, [
    handleAiOptimizePersonalStrategy,
    handleForkToPersonal,
    handleOpenPaperSession,
    router,
    setActiveTab,
  ]);

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
            strategyActionKind: 'view' as const,
            mutationEffect: 'readonly' as const,
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
            strategyActionKind: 'view' as const,
            mutationEffect: 'readonly' as const,
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
        strategyActionKind: 'view' as const,
        mutationEffect: 'readonly' as const,
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
        strategyActionKind: 'view' as const,
        mutationEffect: 'readonly' as const,
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
        strategyActionKind: 'view' as const,
        mutationEffect: 'readonly' as const,
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
        strategyActionKind: 'view' as const,
        mutationEffect: 'readonly' as const,
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
            mutationEffect: 'stateful' as const,
            run: async () => {
              await handleForkToPersonal();
              return { message: `已复制 ${strategy?.name ?? '当前策略'} 为个人策略` };
            },
          }]
        : []),
      ...(ownerState?.editable
        ? [
          {
            id: 'strategy-detail.ai-suggest-personal',
            label: '生成 AI 修改建议',
            description: '读取当前个人策略草稿并生成建议态修改方案，不直接写库',
            keywords: ['AI建议', '修改建议', '个人策略'],
            scope: 'page' as const,
            pageKey,
            strategyActionKind: 'generate_update_suggestion' as const,
            mutationEffect: 'advisory' as const,
            run: async (payload?: CopilotActionPayload) => {
              const response = await handleAiSuggestPersonalStrategy(payload);
              const summary = typeof response?.summary === 'string'
                ? response.summary
                : `已生成 ${strategy?.name ?? '当前策略'} 的 AI 修改建议`;
              return { message: summary };
            },
          },
          {
            id: 'strategy-detail.save-personal',
            label: '保存我的策略',
            description: '保存当前个人策略草稿的名称、描述、参数与因子权重',
            keywords: ['保存', '个人策略', '草稿'],
            scope: 'page' as const,
            pageKey,
            strategyActionKind: 'persist_update' as const,
            mutationEffect: 'stateful' as const,
            run: async () => {
              await savePersonalStrategy();
              return { message: `已保存 ${strategy?.name ?? '当前策略'} 的个人草稿` };
            },
          },
          {
            id: 'strategy-detail.apply-ai-suggestion',
            label: '应用 AI 建议并保存',
            description: '把最近一次 AI 建议落库；如果传入新的目标/说明且当前没有建议，会先生成再直接应用并触发后验校验',
            keywords: ['应用建议', '保存', '个人策略'],
            scope: 'page' as const,
            pageKey,
            strategyActionKind: 'persist_update' as const,
            mutationEffect: 'stateful' as const,
            run: async (payload?: CopilotActionPayload) => {
              const response = await applyLatestAiSuggestion(payload);
              const pipelineStatus = typeof (response as Record<string, unknown> | null)?.post_update_pipeline === 'object'
                ? String(((response as Record<string, unknown>).post_update_pipeline as Record<string, unknown>).overall_status ?? '').trim()
                : '';
              return {
                message: pipelineStatus
                  ? `已将 AI 建议应用到 ${strategy?.name ?? '当前策略'}，后验流水线状态 ${pipelineStatus}`
                  : `已将 AI 建议应用到 ${strategy?.name ?? '当前策略'}`,
              };
            },
          },
          {
            id: 'strategy-detail.ai-optimize',
            label: 'AI 优化我的策略',
            description: '用现有 AI 实验链路优化当前个人策略并直接写回草稿，同时触发运行契约回填、回测、质检回放与执行审计',
            keywords: ['AI', '优化'],
            scope: 'page' as const,
            pageKey,
            strategyActionKind: 'optimize' as const,
            mutationEffect: 'stateful' as const,
            run: async (payload?: CopilotActionPayload) => {
              const response = await handleAiOptimizePersonalStrategy(payload);
              const pipelineStatus = typeof (response as Record<string, unknown> | null)?.post_update_pipeline === 'object'
                ? String(((response as Record<string, unknown>).post_update_pipeline as Record<string, unknown>).overall_status ?? '').trim()
                : '';
              return {
                message: pipelineStatus
                  ? `已触发 ${strategy?.name ?? '当前策略'} 的 AI 优化，后验流水线状态 ${pipelineStatus}`
                  : `已触发 ${strategy?.name ?? '当前策略'} 的 AI 优化`,
              };
            },
          },
        ]
        : []),
    ],
    [
      addToCart,
      applyLatestAiSuggestion,
      emptyDetailContract,
      handleAiSuggestPersonalStrategy,
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
  const resultPageActions = useMemo(
    () =>
      emptyDetailContract
        ? [
            {
              id: 'strategy-detail.empty.open-market',
              label: '返回策略超市',
              description: '回到策略列表继续筛选和比较',
              keywords: ['策略超市', '返回列表'],
              scope: 'page' as const,
              pageKey,
              strategyActionKind: 'view' as const,
              mutationEffect: 'readonly' as const,
              run: async () => null,
            },
            {
              id: 'strategy-detail.empty.reload',
              label: '重新加载策略详情',
              description: '重新尝试加载当前空态详情页',
              keywords: ['刷新', '重试'],
              scope: 'page' as const,
              pageKey,
              strategyActionKind: 'view' as const,
              mutationEffect: 'readonly' as const,
              run: async () => null,
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
              strategyActionKind: 'view' as const,
              mutationEffect: 'readonly' as const,
              run: async () => null,
            },
            {
              id: 'strategy-detail.switch.overview',
              label: '切到策略概览',
              description: '查看样本期、质量门、净值轨迹和用户评价',
              keywords: ['概览', '质量门'],
              scope: 'page' as const,
              pageKey,
              strategyActionKind: 'view' as const,
              mutationEffect: 'readonly' as const,
              run: async () => null,
            },
            {
              id: 'strategy-detail.switch.tracking',
              label: '切到实盘跟踪',
              description: '查看信号统计、前向验证与历史信号',
              keywords: ['实盘跟踪', '信号'],
              scope: 'page' as const,
              pageKey,
              strategyActionKind: 'view' as const,
              mutationEffect: 'readonly' as const,
              run: async () => null,
            },
            {
              id: 'strategy-detail.switch.factory',
              label: '切到工厂审查',
              description: '查看工厂摘要、孵化闭环、运行风控和实验事件',
              keywords: ['工厂审查', '风控'],
              scope: 'page' as const,
              pageKey,
              strategyActionKind: 'view' as const,
              mutationEffect: 'readonly' as const,
              run: async () => null,
            },
            {
              id: 'strategy-detail.subscribe',
              label: isSubscribed ? '取消收藏策略' : '收藏策略',
              description: '切换当前策略的收藏状态',
              keywords: ['收藏', '策略'],
              scope: 'page' as const,
              pageKey,
              run: async () => null,
            },
            {
              id: 'strategy-detail.add-to-portfolio',
              label: '加入组合购物车',
              description: '将当前策略加入组合购物车并打开购物车',
              keywords: ['加入组合', '购物车'],
              scope: 'page' as const,
              pageKey,
              run: async () => null,
            },
            {
              id: 'strategy-detail.open-paper',
              label: paperSessionState?.has_session ? '打开我的模拟盘测试' : '创建模拟盘测试',
              description: '为当前策略打开或创建个人模拟盘测试账户',
              keywords: ['模拟盘', 'paper'],
              scope: 'page' as const,
              pageKey,
              run: async () => null,
            },
            ...(userId && !ownerState?.editable
              ? [{
                  id: 'strategy-detail.fork-personal',
                  label: '复制为我的策略',
                  description: '把当前市场策略复制成个人草稿',
                  keywords: ['复制', '我的策略'],
                  scope: 'page' as const,
                  pageKey,
                  mutationEffect: 'stateful' as const,
                  run: async () => null,
                }]
              : []),
            ...(ownerState?.editable
              ? [
                  {
                    id: 'strategy-detail.ai-suggest-personal',
                    label: '生成 AI 修改建议',
                    description: '读取当前个人策略草稿并生成建议态修改方案，不直接写库',
                    keywords: ['AI建议', '修改建议', '个人策略'],
                    scope: 'page' as const,
                    pageKey,
                    strategyActionKind: 'generate_update_suggestion' as const,
                    mutationEffect: 'advisory' as const,
                    run: async () => null,
                  },
                  {
                    id: 'strategy-detail.save-personal',
                    label: '保存我的策略',
                    description: '保存当前个人策略草稿的名称、描述、参数与因子权重',
                    keywords: ['保存', '个人策略', '草稿'],
                    scope: 'page' as const,
                    pageKey,
                    strategyActionKind: 'persist_update' as const,
                    mutationEffect: 'stateful' as const,
                    run: async () => null,
                  },
                  {
                    id: 'strategy-detail.apply-ai-suggestion',
                    label: '应用 AI 建议并保存',
                    description: '把最近一次 AI 建议落库；如果传入新的目标/说明且当前没有建议，会先生成再直接应用并触发后验校验',
                    keywords: ['应用建议', '保存', '个人策略'],
                    scope: 'page' as const,
                    pageKey,
                    strategyActionKind: 'persist_update' as const,
                    mutationEffect: 'stateful' as const,
                    run: async () => null,
                  },
                  {
                    id: 'strategy-detail.ai-optimize',
                    label: 'AI 优化我的策略',
                    description: '用现有 AI 实验链路优化当前个人策略并继续触发运行契约回填、回测、质检回放与执行审计',
                    keywords: ['AI', '优化'],
                    scope: 'page' as const,
                    pageKey,
                    strategyActionKind: 'optimize' as const,
                    mutationEffect: 'stateful' as const,
                    run: async () => null,
                  },
                ]
              : []),
          ],
    [emptyDetailContract, isSubscribed, ownerState?.editable, pageKey, paperSessionState?.has_session, userId],
  );

  const strategyDetailSummary = emptyDetailContract
      ? '当前环境还没有可进入的策略详情数据，页面按空态契约渲染。'
      : strategy
      ? `${strategy.name} 当前处于 ${displayStatus.label}，市场状态 ${marketStatus.label}，${showIncubationStage ? `孵化阶段 ${incubationSurface.stage.label}` : '暂未进入真实孵化链路'}，当前工作流为 ${activeTabLabel}。收藏数 ${strategy.favorite_count ?? strategy.subscriber_count ?? 0}，风险事件 ${openRiskEvents.length}，向量画像 ${vectorProfiles.length}。${ownerState?.editable ? `当前为可编辑个人策略，${latestAiSuggestion?.summary ? `最近一轮 AI 建议：${latestAiSuggestion.summary}` : '可生成修改建议、执行 AI 优化或直接保存草稿。'}` : ''}`
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
        pageActions: resultPageActions,
        preferredActionIds: emptyDetailContract
          ? ['strategy-detail.empty.open-market', 'strategy-detail.empty.reload']
          : ownerState?.editable
            ? ['strategy-detail.ai-suggest-personal', 'strategy-detail.save-personal', 'strategy-detail.ai-optimize']
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
            href: strategy
              ? `/assistant?from=strategy-detail&strategy_id=${encodeURIComponent(String(strategy.id))}&objectType=strategy`
              : '/assistant?from=strategy-detail',
          },
        ],
        evidence: [
          { label: '当前标签', value: activeTabLabel },
          { label: '当前状态', value: displayStatus.label },
          { label: '市场状态', value: marketStatus.label },
          { label: '孵化阶段', value: showIncubationStage ? incubationSurface.stage.label : '未接入真实孵化' },
          { label: '收藏数', value: String(strategy?.favorite_count ?? strategy?.subscriber_count ?? 0) },
          { label: '风险事件', value: String(openRiskEvents.length), tone: openRiskEvents.length > 0 ? 'warning' : 'neutral' },
          { label: '向量画像', value: String(vectorProfiles.length) },
          { label: '质量评级', value: String(latestQualityReport?.summary?.validation_grade ?? '-') },
        ],
        riskNotes: [
          ...(emptyDetailContract ? ['当前是策略详情空态契约，建议先回到策略超市重新筛选。'] : []),
          ...(!incubationSurface.promotionReady && strategy ? ['当前策略尚未达到晋级条件，进入组合前需要继续看质量门与运行风控。'] : []),
          ...(openRiskEvents.length > 0 ? [`当前存在 ${openRiskEvents.length} 个未关闭风险事件。`] : []),
          ...(personalStrategyContextQ.error ? [`个人策略上下文加载失败：${personalStrategyContextQ.error}`] : []),
          ...((latestAiSuggestion?.risk_notes ?? []).filter((item): item is string => typeof item === 'string' && item.trim().length > 0)),
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
      emptyDetailContract,
      factoryPanelProps.activeSection,
      displayStatus.label,
      incubationSurface.promotionReady,
      incubationSurface.stage.label,
      latestQualityReport?.summary?.validation_grade,
      marketStatus.label,
      ownerState?.editable,
      openRiskEvents.length,
      personalStrategyContextQ.error,
      portfolioHref,
      resultPageActions,
      showIncubationStage,
      strategy,
      strategyDetailSummary,
      strategyId,
      vectorProfiles.length,
      latestAiSuggestion?.risk_notes,
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
      ownerState?.editable ? '个人策略可编辑' : null,
      latestAiSuggestion?.summary ? '存在 AI 修改建议' : null,
      strategy?.author_id ? `作者 ${strategy.author_id}` : null,
      strategy?.favorite_count != null || strategy?.subscriber_count != null ? `${strategy.favorite_count ?? strategy.subscriber_count} 收藏` : null,
      latestQualityReport?.summary?.validation_grade ? `评级 ${latestQualityReport.summary.validation_grade}` : null,
    ].filter((item): item is string => Boolean(item)),
    suggestions: emptyDetailContract
      ? ['返回策略超市', '运行工厂生成策略', '稍后重新加载详情页']
      : strategy
        ? [
            activeTab === 'overview' ? '切到实盘跟踪看信号与命中率' : '回概览确认样本期和质量门',
            activeTab === 'factory' ? '继续切换工厂审查分区' : '打开工厂审查看运行风控与实验事件',
            ...(ownerState?.editable
              ? [
                  latestAiSuggestion?.summary ? '先看 AI 修改建议，再决定是否应用并保存' : '先生成 AI 修改建议，再决定是保存还是直接 AI 优化',
                ]
              : []),
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
      personalStrategyContext,
      latestAiSuggestion: latestAiSuggestion
        ? {
            summary: latestAiSuggestion.summary ?? null,
            advisoryOnly: latestAiSuggestion.advisory_only ?? true,
            changedFields: latestAiSuggestion.changed_fields ?? [],
            hasApplyPayload: Boolean(latestAiSuggestion.apply_payload && Object.keys(latestAiSuggestion.apply_payload).length > 0),
          }
        : null,
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

  const primaryContent = (
    <div className="space-y-4 xl:h-full xl:overflow-y-auto xl:pr-1">
      {ownerState?.editable ? (
        <section key={String(strategy.id)} className="panel-soft rounded-[24px] p-4 sm:p-5">
          <div className="eyebrow">个人策略编辑</div>
          <h3 className="mt-2 mb-0 text-lg font-semibold text-text-primary">当前策略可直接编辑</h3>
          <p className="mt-2 text-sm text-text-secondary">
            修改名称、描述、参数与因子权重后会直接保存到你的个人策略草稿，不会影响市场策略。当前页 Copilot 现在可以区分查看、生成修改建议、执行 AI 优化和真实保存动作；应用建议或 AI 优化后会继续触发运行契约回填、回测、质检回放与执行审计。
          </p>
          {personalStrategyContext ? (
            <div className="mt-4 rounded-[18px] border border-border bg-surface-alt/70 px-3 py-3 text-xs text-text-secondary">
              <div className="font-medium text-text-primary">
                当前个人策略上下文
                {personalStrategyContext.strategy_name ? ` · ${personalStrategyContext.strategy_name}` : ''}
              </div>
              <div className="mt-2">
                {personalStrategyContext.editable ? '可编辑' : '只读'}，
                {personalStrategyContext.mutation_guard?.allowed
                  ? '允许 AI 建议与写入'
                  : (personalStrategyContext.mutation_guard?.reason ?? '当前不可写入')}
              </div>
              {personalStrategyContext.action_modes?.length ? (
                <div className="mt-2 flex flex-wrap gap-2">
                  {personalStrategyContext.action_modes.map((item) => (
                    <span key={`${item.action_kind ?? 'action'}:${item.effect ?? 'effect'}`} className="rounded-full bg-surface px-2.5 py-1 text-[11px] text-text-secondary">
                      {(item.label ?? item.action_kind ?? '动作')}
                      {item.effect ? ` · ${item.effect}` : ''}
                    </span>
                  ))}
                </div>
              ) : null}
            </div>
          ) : null}
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
              rows={compactLayout ? 2 : 3}
              className="w-full rounded-[16px] border border-border bg-surface px-3 py-2 text-sm"
            />
            {compactLayout ? (
              <details className="rounded-[18px] border border-white/45 bg-white/24 px-3 py-3">
                <summary className="cursor-pointer list-none text-sm font-medium text-text-primary">
                  展开高级参数与因子权重
                </summary>
                <div className="mt-3 grid gap-3">
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
                    rows={6}
                    className="w-full rounded-[16px] border border-border bg-surface px-3 py-2 font-mono text-xs"
                  />
                  <textarea
                    ref={editFactorWeightsTextRef}
                    defaultValue={JSON.stringify(strategy.factor_weights ?? {}, null, 2)}
                    placeholder="因子权重 JSON"
                    rows={5}
                    className="w-full rounded-[16px] border border-border bg-surface px-3 py-2 font-mono text-xs"
                  />
                </div>
              </details>
            ) : (
              <>
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
              </>
            )}
            <div className="flex flex-wrap gap-2">
              <button
                type="button"
                onClick={() => void handleAiSuggestPersonalStrategy()}
                disabled={aiSuggestionApi.isPending}
                className="rounded-full border border-border bg-surface px-4 py-2 text-sm"
              >
                {aiSuggestionApi.isPending ? '生成建议中...' : '生成 AI 修改建议'}
              </button>
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
                onClick={() => aiModifyPersonalAction && void executeRuntimeAction(aiModifyPersonalAction)}
                disabled={
                  !aiModifyPersonalAction ||
                  aiModifyPersonalAction.status === 'unavailable' ||
                  pendingRuntimeActionId === 'ai_modify_personal_strategy'
                }
                title={aiModifyPersonalAction?.unavailable_reason ?? aiModifyPersonalAction?.description ?? '交给 AI 修改个人策略'}
                className="rounded-full border border-border bg-surface px-4 py-2 text-sm"
              >
                {pendingRuntimeActionId === 'ai_modify_personal_strategy'
                  ? 'AI 修改中...'
                  : (aiModifyPersonalAction?.label ?? '交给 AI 修改个人策略')}
              </button>
              <button
                type="button"
                onClick={() => void applyLatestAiSuggestion()}
                disabled={updateStrategyApi.isPending || !latestAiSuggestion?.apply_payload || Object.keys(latestAiSuggestion.apply_payload).length === 0}
                className="rounded-full border border-border bg-surface px-4 py-2 text-sm"
              >
                {updateStrategyApi.isPending ? '应用中...' : '应用 AI 建议并保存'}
              </button>
              <button
                type="button"
                onClick={() => paperSessionAction && void executeRuntimeAction(paperSessionAction)}
                disabled={
                  !paperSessionAction ||
                  paperSessionAction.status === 'unavailable' ||
                  pendingRuntimeActionId === 'open_personal_paper_session'
                }
                title={paperSessionAction?.unavailable_reason ?? paperSessionAction?.description ?? '加入模拟盘'}
                className="rounded-full border border-border bg-surface px-4 py-2 text-sm"
              >
                {pendingRuntimeActionId === 'open_personal_paper_session'
                  ? '处理中...'
                  : (paperSessionAction?.label ?? '加入模拟盘')}
              </button>
            </div>
            {[aiModifyPersonalAction, paperSessionAction]
              .filter((action): action is StrategyRuntimeActionContractItem => Boolean(action?.unavailable_reason))
              .map((action) => (
                <div key={`${action.id}:edit-reason`} className="text-xs leading-6 text-text-secondary">
                  {action.label}：{action.unavailable_reason}
                </div>
              ))}
            {latestAiSuggestion ? (
              <div className="rounded-[18px] border border-primary/20 bg-primary/5 px-4 py-4 text-sm">
                <div className="font-medium text-text-primary">最近一次 AI 修改建议</div>
                <p className="mt-2 mb-0 text-text-secondary">
                  {latestAiSuggestion.summary ?? 'AI 已生成修改建议，可先查看再决定是否应用。'}
                </p>
                {latestAiSuggestion.changed_fields?.length ? (
                  <div className="mt-3 flex flex-wrap gap-2">
                    {latestAiSuggestion.changed_fields.map((field) => (
                      <span key={field} className="rounded-full bg-surface px-2.5 py-1 text-[11px] text-text-secondary">
                        {field}
                      </span>
                    ))}
                  </div>
                ) : null}
                {latestAiSuggestion.suggestions?.length ? (
                  <div className="mt-3 space-y-2 text-xs text-text-secondary">
                    {latestAiSuggestion.suggestions.slice(0, 4).map((item, index) => (
                      <div key={`${item.field ?? 'field'}:${index}`} className="rounded-[14px] border border-border bg-surface px-3 py-2">
                        <div className="font-medium text-text-primary">{item.field ?? '未命名字段'}</div>
                        <div className="mt-1">{item.reason ?? '已生成该字段的修改建议。'}</div>
                      </div>
                    ))}
                  </div>
                ) : null}
                <div className="mt-3 text-xs text-text-secondary">
                  当前仍为建议态；只有点击“应用 AI 建议并保存”或执行“AI 优化我的策略”时才会落库。
                </div>
              </div>
            ) : null}
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
          strategyStatus={strategy.status ?? null}
          strategyIncubationSurface={strategy.incubation_surface ?? null}
          paperContext={paperContext}
          incubationOverview={incubationOverview}
          latestQualityReport={latestQualityReport}
          incubationAccount={incubationAccount}
          latestIncubationMetric={latestIncubationMetric}
          latestIncubationPipelineSnapshot={latestIncubationPipelineSnapshot}
          openRiskEventsCount={openRiskEvents.length}
          vectorProfilesCount={vectorProfiles.length}
          highConfidenceQualityUiEnabled={highConfidenceQualityUiEnabled}
          ownerState={ownerState}
          paperSessionState={paperSessionState}
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
      subscriberCount={strategy.favorite_count ?? strategy.subscriber_count ?? 0}
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
      onOpenPaper={() => router.push('/paper-trading?from=strategy-detail')}
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
        runtimeActionContract={runtimeActionContract}
        pendingActionId={pendingRuntimeActionId}
        onRuntimeAction={executeRuntimeAction}
      />

      {!compactLayout ? (
        <ProgressiveWorkbenchSection
          pageKey="strategy-detail"
          title="策略详情结果工作台"
          result={strategyDetailResult}
          summaryMode="strip"
        />
      ) : null}

      {!ownerState?.editable && userId ? (
        <section className="panel-soft rounded-[22px] px-4 py-3">
          <div className="flex flex-wrap items-center gap-2">
            <div className="text-sm text-text-secondary">
              {presentation?.recommended_action ?? '你可以先收藏、复制为个人策略，或直接拉起个人模拟盘测试。'}
            </div>
            <div className="ml-auto">
              <StrategyRuntimeActionBar
                contract={runtimeActionContract}
                pendingActionId={pendingRuntimeActionId}
                onAction={executeRuntimeAction}
                compact
              />
            </div>
          </div>
        </section>
      ) : null}

      <TabBar tabs={DETAIL_TABS} active={activeTab} onChange={setActiveTab} />
      <WorkspaceSplitLayout pageKey={pageKey} primary={primaryContent} secondary={secondaryContent} />
      {showCart ? <CartDrawer onClose={() => setShowCart(false)} /> : null}
    </PageContainer>
  );
}
