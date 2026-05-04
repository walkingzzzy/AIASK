'use client';

import Link from 'next/link';
import { FormEvent, useMemo, useState, useCallback, useEffect, useRef } from 'react';
import PaperTradingActivity from '@/app/paper-trading/components/paper-trading-activity';
import PaperTradingAnalytics from '@/app/paper-trading/components/paper-trading-analytics';
import PaperTradingHero from '@/app/paper-trading/components/paper-trading-hero';
import PaperTradingOrderWorkspace from '@/app/paper-trading/components/paper-trading-order-workspace';
import PaperTradingSummarySidebar from '@/app/paper-trading/components/paper-trading-summary-sidebar';
import PaperTradingTrustStatusCard from '@/app/paper-trading/components/paper-trading-trust-status';
import ProgressiveWorkbenchSection from '@/components/progressive-workbench-section';
import { DataQualityBanner, LoadingState, PageStatusCard } from '@/components/status-state';
import WorkspaceSplitLayout from '@/components/workspace-split-layout';
import WorkspaceToolbar from '@/components/workspace-toolbar';
import { PageContainer, SectionCard, TabBar } from '@/components/ui';
import { ConfirmDialog } from '@/components/ui/confirm-dialog';
import { useToast } from '@/components/ui/toast';
import { useApiQuery } from '@/hooks/use-api-query';
import { useApiMutation } from '@/hooks/use-api-mutation';
import { useMobile } from '@/hooks/use-mobile';
import { usePageActions } from '@/hooks/use-page-actions';
import { usePageContext } from '@/hooks/use-page-context';
import { useStableSearchParams } from '@/hooks/use-stable-search-params';
import { apiKeys } from '@/lib/query-keys';
import { buildLocalResultContract, defaultWorkbenchTask, evidenceToSummary } from '@/lib/result-workbench';
import { useStockCode } from '@/hooks/use-stock-code';
import { extractArray, fmtNum, fmtPct } from '@/lib/data-utils';
import { RESPONSIVE_BREAKPOINTS } from '@/lib/responsive-layout';
import { useTradeSubscription } from '@/lib/ws';
import { isTradingHours } from '@/lib/trading-hours';
import { readTransactionConfirmations } from '@/lib/transaction-confirmations';
import { selectActiveWorkspace, useWorkbenchStore } from '@/store/workbench-store';
import type {
  PaperTradingAccountsResponse,
  PaperTradingAccount,
  PaperTradingCancelOrderInput,
  PaperTradingComplianceResult,
  PaperTradingNavPoint,
  PaperTradingNavHistoryResponse,
  PaperTradingOrdersResponse,
  PaperTradingPendingOrder,
  PaperTradingPendingOrdersResponse,
  PaperTradingPerformanceMetrics,
  PaperTradingPerformancePoint,
  PaperTradingPerformanceResponse,
  PaperTradingPlaceOrderInput,
  PaperTradingPosition,
  PaperTradingPositionsResponse,
  PaperTradingReconcileResponse,
  PaperTradingRouteExecutionInput,
  PaperTradingStatusProbe,
  PaperTradingSummary,
  PaperTradingTrade,
  PaperTradingTrustStatus,
  StrategyPaperContextResponse,
} from '@aiask/shared-types';

type PendingOrderRequest = {
  body: PaperTradingPlaceOrderInput;
  idempotencyKey: string;
};

type PendingCancelRequest = {
  orderId: number;
  idempotencyKey: string;
};

type PaperTradingMobilePrimaryTab = 'order' | 'analytics' | 'activity';

const PAPER_TRADING_MOBILE_PRIMARY_TABS = [
  { key: 'order', label: '下单' },
  { key: 'analytics', label: '账户分析' },
  { key: 'activity', label: '持仓与记录' },
] as const;

type CompliancePayload = {
  success?: boolean;
  data?: PaperTradingComplianceResult;
};

function createIdempotencyKey(scope: string) {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return `${scope}:${crypto.randomUUID()}`;
  }
  return `${scope}:${Date.now()}:${Math.random().toString(36).slice(2, 10)}`;
}

function readStatusProbeNote(probe: PaperTradingStatusProbe, fallback: string) {
  const record = probe as Record<string, unknown>;
  const note = record.reason ?? record.message;
  return typeof note === 'string' && note.trim() ? note : fallback;
}

function isSandboxAccount(accountId: string) {
  return /(sandbox|test|demo|paper-audit|playwright|qa)/i.test(accountId);
}

function readDegradedReason(value: unknown): string | null {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null;
  const record = value as Record<string, unknown>;
  if (record.degraded !== true) return null;
  const fallbackReason = record.fallback_reason ?? record.fallbackReason;
  if (typeof fallbackReason === 'string' && fallbackReason.trim()) {
    return fallbackReason.trim();
  }
  if (Array.isArray(fallbackReason)) {
    const joined = fallbackReason.map((item) => String(item).trim()).filter(Boolean).join('；');
    if (joined) return joined;
  }
  const message = record.message;
  return typeof message === 'string' && message.trim() ? message.trim() : '价格刷新暂不可用，已保留当前快照';
}

function normalizePaperRiskRules(value: unknown): Record<string, unknown> {
  if (!value) return {};
  if (typeof value === 'string') {
    try {
      const parsed = JSON.parse(value);
      if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
        return parsed as Record<string, unknown>;
      }
    } catch {
      return {};
    }
  }
  if (typeof value === 'object' && !Array.isArray(value)) {
    return value as Record<string, unknown>;
  }
  return {};
}

function normalizeRiskPct(value: unknown, fallback: number): number {
  const numeric = Number(value);
  if (!Number.isFinite(numeric) || numeric <= 0) {
    return fallback;
  }
  return numeric <= 1 ? numeric * 100 : numeric;
}

function readPaperAccountId(account: unknown): string {
  if (!account || typeof account !== 'object' || Array.isArray(account)) return '';
  const record = account as Record<string, unknown>;
  return String(record.account_id ?? record.id ?? '').trim();
}

export default function PaperTradingPage() {
  const { toast } = useToast();
  const searchParams = useStableSearchParams();
  const workbenchHydrated = useWorkbenchStore((state) => state.hydrated);
  const activeWorkspaceId = useWorkbenchStore((state) => state.activeWorkspaceId);
  const workbenchContext = useWorkbenchStore((state) => selectActiveWorkspace(state).context);
  const updateWorkbenchContext = useWorkbenchStore((state) => state.updateContext);
  const lastWorkspaceIdRef = useRef<string | null>(null);
  const queryAccountId = searchParams.get('account_id')?.trim() ?? '';
  const queryStrategyId = searchParams.get('strategy_id')?.trim() ?? '';
  const queryStrategyName = searchParams.get('strategy_name')?.trim() ?? '';
  const queryMode = searchParams.get('mode')?.trim() ?? '';
  const queryStockCode = searchParams.get('stock_code')?.trim() ?? '';
  const linkedStrategyId = queryStrategyId || workbenchContext.linkedStrategyId || workbenchContext.strategyId || '';
  const personalStrategyMode =
    queryMode === 'personal-strategy'
    || workbenchContext.mode === 'personal-strategy'
    || workbenchContext.strategyTestMode === 'personal-strategy';
  const { code, setCode, codeError, validate, trimmedCode } = useStockCode('');
  const [direction, setDirection] = useState<'buy' | 'sell'>('buy');
  const [quantity, setQuantity] = useState('100');
  const [price, setPrice] = useState('');
  const [orderType, setOrderType] = useState<'market' | 'limit' | 'stop'>('market');
  const [stopPrice, setStopPrice] = useState('');
  const [formError, setFormError] = useState<string | null>(null);
  const [formStatus, setFormStatus] = useState<string | null>(null);
  const [lastActionResult, setLastActionResult] = useState<string | null>(null);
  const [accountId, setAccountId] = useState('');
  const [pendingOrderRequest, setPendingOrderRequest] = useState<PendingOrderRequest | null>(null);
  const [pendingCancelRequest, setPendingCancelRequest] = useState<PendingCancelRequest | null>(null);
  const [cancelingOrderIds, setCancelingOrderIds] = useState<number[]>([]);
  const [tradeNotice, setTradeNotice] = useState<string | null>(null);
  const [perfDays, setPerfDays] = useState(30);
  const [loadingGraceExpired, setLoadingGraceExpired] = useState(false);
  const [mobilePrimaryTab, setMobilePrimaryTab] = useState<PaperTradingMobilePrimaryTab>('order');
  const collapseToTabs = useMobile(RESPONSIVE_BREAKPOINTS.splitCollapse);
  const strategyDetailQ = useApiQuery<Record<string, unknown>>(
    linkedStrategyId ? `/strategy-market/${encodeURIComponent(linkedStrategyId)}` : null,
    { enabled: Boolean(linkedStrategyId), staleTime: 60_000 },
  );
  const strategyPaperContextQ = useApiQuery<StrategyPaperContextResponse>(
    linkedStrategyId ? `/strategy-market/${encodeURIComponent(linkedStrategyId)}/paper-context` : null,
    {
      enabled: personalStrategyMode && Boolean(linkedStrategyId),
      staleTime: 60_000,
      nonFatal: true,
    },
  );
  const accountsQ = useApiQuery<PaperTradingAccountsResponse | PaperTradingAccount[]>('/paper-trading/accounts');
  const accounts = useMemo(
    () => extractArray(accountsQ.data, 'accounts', 'items', 'data') as PaperTradingAccount[],
    [accountsQ.data],
  );
  const firstAccountId = useMemo(
    () => accounts.map(readPaperAccountId).find(Boolean) ?? '',
    [accounts],
  );

  // T-005: WS real-time trade order updates
  const handleTradeUpdate = useCallback((data: Partial<PaperTradingPendingOrder> & { stock_code?: string }) => {
    const status = String(data.status ?? '');
    const code = String(data.code ?? data.stock_code ?? '');
    setTradeNotice(
      `订单 ${code} ${status === 'filled' ? '已成交' : status === 'partial' ? '部分成交' : status === 'rejected' ? '被拒绝' : '状态更新'}`,
    );
    // Auto-dismiss after 5s
    setTimeout(() => setTradeNotice(null), 5000);
  }, []);

  const personalTrack = strategyPaperContextQ.data?.personal ?? null;
  const resolvedPersonalAccountId = String(
    personalTrack?.account_id
      ?? personalTrack?.account?.id
      ?? personalTrack?.account?.account_id
      ?? '',
  ).trim();
  const requiresPersonalSession = personalStrategyMode && Boolean(linkedStrategyId);
  const workspaceAccountId = String(workbenchContext.accountId ?? '').trim();
  const activeAccountId = queryAccountId
    || (requiresPersonalSession
      ? (accountId || resolvedPersonalAccountId)
      : (accountId || workspaceAccountId || firstAccountId));
  const canLoadAccountQueries = Boolean(activeAccountId);
  const qs = canLoadAccountQueries ? `?account_id=${encodeURIComponent(activeAccountId)}` : '';

  // 8 read queries — auto-fetch on mount, re-fetch when qs changes
  const profileQ = useApiQuery<Record<string, unknown>>('/auth/profile', { critical: true });
  const matchStatusQ = useApiQuery<PaperTradingStatusProbe>('/paper-trading/matching-status');
  const navStatusQ = useApiQuery<PaperTradingStatusProbe>('/paper-trading/nav-status');
  const summaryQ = useApiQuery<PaperTradingSummary>(qs ? '/paper-trading/summary' + qs : '/paper-trading/summary', {
    enabled: canLoadAccountQueries,
  });
  const positionsQ = useApiQuery<PaperTradingPositionsResponse>('/paper-trading/positions' + qs, {
    enabled: canLoadAccountQueries,
  });
  const ordersQ = useApiQuery<PaperTradingOrdersResponse>('/paper-trading/orders' + qs, {
    enabled: canLoadAccountQueries,
  });
  const pendingQ = useApiQuery<PaperTradingPendingOrdersResponse>('/paper-trading/pending-orders' + qs, {
    enabled: canLoadAccountQueries,
  });
  const navQ = useApiQuery<PaperTradingNavHistoryResponse>('/paper-trading/nav-history' + qs, {
    enabled: canLoadAccountQueries,
  });
  const performanceQ = useApiQuery<PaperTradingPerformanceResponse>(
    `/paper-trading/performance${qs ? `${qs}&days=${perfDays}` : `?days=${perfDays}`}`,
    { enabled: canLoadAccountQueries },
  );
  const trustStatusQ = useApiQuery<PaperTradingTrustStatus>('/paper-trading/trust-status' + qs, {
    placeholderData: 'keepPrevious',
    nonFatal: true,
    enabled: canLoadAccountQueries,
  });

  // Subscribe to trade updates via WS
  useTradeSubscription({ accountId: activeAccountId, onUpdate: handleTradeUpdate, enabled: canLoadAccountQueries });

  // Advanced MCP Managers (Compliance & Execution)
  const [useComplianceCheck, setUseComplianceCheck] = useState(false);
  const [urgentExecution, setUrgentExecution] = useState(false);
  const complianceApi = useApiMutation<CompliancePayload>();
  const routeExecutionApi = useApiMutation<Record<string, unknown>>({ invalidates: [[...apiKeys.paper()]] });
  const refreshPricesApi = useApiMutation<Record<string, unknown>>({
    invalidates: [[...apiKeys.paper()]],
    successToast: false,
  });
  const reconcileApi = useApiMutation<Record<string, unknown>>({
    invalidates: [[...apiKeys.paper()]],
    successToast: false,
  });
  const cleanupApi = useApiMutation<Record<string, unknown>>({
    invalidates: [[...apiKeys.paper()]],
    successToast: '测试账户已清理',
  });
  const autoRefreshPricesApi = useApiMutation<Record<string, unknown>>({
    invalidates: [[...apiKeys.paper()]],
    successToast: false,
    errorToast: false,
  });

  // 2 write mutations — invalidate all paper queries on success
  const placeApi = useApiMutation<Record<string, unknown>>({ invalidates: [[...apiKeys.paper()]] });
  const cancelApi = useApiMutation<Record<string, unknown>>({ invalidates: [[...apiKeys.paper()]] });

  const refreshPaperData = useCallback(async () => {
    const tasks = [
      profileQ.refetch(),
      accountsQ.refetch(),
      matchStatusQ.refetch(),
      navStatusQ.refetch(),
    ];
    if (personalStrategyMode && linkedStrategyId) {
      tasks.unshift(strategyPaperContextQ.refetch());
    }
    if (canLoadAccountQueries) {
      tasks.push(
        summaryQ.refetch(),
        positionsQ.refetch(),
        ordersQ.refetch(),
        pendingQ.refetch(),
        navQ.refetch(),
        performanceQ.refetch(),
        trustStatusQ.refetch(),
      );
    }
    await Promise.allSettled(tasks);
  }, [accountsQ, canLoadAccountQueries, linkedStrategyId, matchStatusQ, navQ, navStatusQ, ordersQ, pendingQ, performanceQ, personalStrategyMode, positionsQ, profileQ, strategyPaperContextQ, summaryQ, trustStatusQ]);

  const matchStatus = useMemo(() => matchStatusQ.data ?? {}, [matchStatusQ.data]);
  const navStatus = useMemo(() => navStatusQ.data ?? {}, [navStatusQ.data]);
  const matchOk = matchStatus.status === 'running' || matchStatus.running === true || matchStatus.ok === true;
  const navOk = navStatus.status === 'running' || navStatus.running === true || navStatus.ok === true;
  const linkedStrategyRecord = useMemo(() => {
    if (!strategyDetailQ.data || typeof strategyDetailQ.data !== 'object') return null;
    const root = strategyDetailQ.data as Record<string, unknown>;
    const strategy = root.strategy;
    return strategy && typeof strategy === 'object' ? strategy as Record<string, unknown> : null;
  }, [strategyDetailQ.data]);
  const linkedStrategyName =
    String(
      linkedStrategyRecord?.name
        ?? queryStrategyName
        ?? workbenchContext.linkedStrategyName
        ?? workbenchContext.strategyName
        ?? '',
    ).trim();
  const linkedStrategyStatus = String(linkedStrategyRecord?.status ?? '').trim() || null;

  const acct = summaryQ.data?.account ?? undefined;
  const totalValue = Number(summaryQ.data?.total_value ?? acct?.total_value ?? 0);
  const cash = Number(acct?.current_capital ?? 0);
  const initial = Number(acct?.initial_capital ?? 100000);
  const marketValue = totalValue - cash;
  const returnPct = summaryQ.data?.total_return_pct ?? (initial > 0 ? ((totalValue - initial) / initial) * 100 : 0);
  const accountRiskRules = useMemo(() => normalizePaperRiskRules(acct?.risk_rules), [acct?.risk_rules]);
  const maxPositionPct = useMemo(
    () => normalizeRiskPct(accountRiskRules.max_position_pct ?? accountRiskRules.maxPositionPct, 30),
    [accountRiskRules],
  );
  const maxPositionAmount = useMemo(() => {
    if (!Number.isFinite(totalValue) || totalValue <= 0) {
      return null;
    }
    return totalValue * (maxPositionPct / 100);
  }, [maxPositionPct, totalValue]);

  const positions = positionsQ.data?.positions ?? [];
  const trades = ordersQ.data?.orders ?? [];
  const pending = pendingQ.data?.orders ?? [];
  const reconciliation = useMemo(
    () => (summaryQ.data?.reconciliation ?? positionsQ.data?.reconciliation ?? null) as PaperTradingReconcileResponse | null,
    [positionsQ.data?.reconciliation, summaryQ.data?.reconciliation],
  );
  const trustStatus = useMemo(() => trustStatusQ.data ?? null, [trustStatusQ.data]);
  const navData = useMemo(() => (navQ.data?.nav ?? []) as PaperTradingNavPoint[], [navQ.data?.nav]);
  const performanceData = useMemo(
    () => (performanceQ.data?.dailyReturns ?? []) as PaperTradingPerformancePoint[],
    [performanceQ.data?.dailyReturns],
  );
  const performanceMetrics = (performanceQ.data?.metrics ?? {}) as PaperTradingPerformanceMetrics;
  const confirmPrefs = useMemo(() => readTransactionConfirmations(profileQ.data), [profileQ.data]);
  const showAccountBootstrap =
    positions.length === 0 && pending.length === 0 && trades.length === 0 && navData.length === 0;
  const statusNotes = useMemo(() => {
    const notes: string[] = [];
    if (!matchOk) notes.push(`撮合状态未确认：${readStatusProbeNote(matchStatus, '请检查撮合服务或稍后重试')}`);
    if (!navOk) notes.push(`净值状态未确认：${readStatusProbeNote(navStatus, '请刷新价格或检查净值服务')}`);
    if (reconciliation?.reconciled) {
      const reason = reconciliation.reasons?.length ? reconciliation.reasons.join('，') : '检测到账本漂移并已自动校准';
      notes.push(`账本已校准：${reason}`);
    }
    return notes;
  }, [matchOk, matchStatus, navOk, navStatus, reconciliation?.reasons, reconciliation?.reconciled]);
  const quantityValue = Number.parseInt(quantity, 10);
  const limitPriceValue = price.trim() ? Number(price) : null;
  const stopPriceValue = stopPrice.trim() ? Number(stopPrice) : null;
  const previewUnitPrice = orderType === 'stop' ? stopPriceValue : limitPriceValue;
  const estimatedAmount = useMemo(() => {
    if (!Number.isFinite(quantityValue) || quantityValue <= 0) return null;
    if (previewUnitPrice == null || !Number.isFinite(previewUnitPrice) || previewUnitPrice <= 0) return null;
    return quantityValue * previewUnitPrice;
  }, [previewUnitPrice, quantityValue]);
  const exceedsPositionCap =
    direction === 'buy' &&
    estimatedAmount != null &&
    maxPositionAmount != null &&
    estimatedAmount > maxPositionAmount + 1e-6;
  const orderTypeLabel = orderType === 'market' ? '市价单' : orderType === 'limit' ? '限价单' : '止损单';
  const directionLabel = direction === 'buy' ? '买入' : '卖出';
  const riskHints = useMemo(() => {
    const hints: string[] = [];
    if (maxPositionAmount != null) {
      hints.push(`当前账户单股仓位上限约 ${fmtNum(maxPositionAmount)}（${fmtPct(maxPositionPct)}）。`);
    }
    if (!trimmedCode) hints.push('请先输入有效股票代码，再进入提交确认。');
    if (!Number.isFinite(quantityValue) || quantityValue <= 0) hints.push('数量需为正整数。');
    if (direction === 'buy' && Number.isFinite(quantityValue) && quantityValue > 0 && quantityValue % 100 !== 0) {
      hints.push('买入数量需满足 100 股整数倍的手数规则。');
    }
    if (
      orderType === 'limit' &&
      (limitPriceValue == null || !Number.isFinite(limitPriceValue) || limitPriceValue <= 0)
    ) {
      hints.push('限价单需填写有效价格，预览金额才会完整显示。');
    }
    if (orderType === 'stop' && (stopPriceValue == null || !Number.isFinite(stopPriceValue) || stopPriceValue <= 0)) {
      hints.push('止损单需填写止损价，系统会先按止损触发价进行预览。');
    }
    if (exceedsPositionCap && estimatedAmount != null && maxPositionAmount != null) {
      hints.push(`当前委托预估金额 ${fmtNum(estimatedAmount)} 已超过单股仓位上限 ${fmtNum(maxPositionAmount)}。`);
    }
    if (useComplianceCheck) hints.push('已开启下单前合规风控，提交时会先做额外检查。');
    if (urgentExecution) hints.push('已开启极速智能路由，提交成功文案会与普通委托不同。');
    if (!useComplianceCheck && !urgentExecution) hints.push('当前为标准提交流程：直接确认并提交委托。');
    return hints;
  }, [
    direction,
    estimatedAmount,
    exceedsPositionCap,
    limitPriceValue,
    maxPositionAmount,
    maxPositionPct,
    orderType,
    quantityValue,
    stopPriceValue,
    trimmedCode,
    urgentExecution,
    useComplianceCheck,
  ]);

  // 今日盈亏：最新 NAV 的 daily_return * 前一日总资产
  const todayPnl = useMemo(() => {
    if (navData.length === 0) return 0;
    const latest = navData[navData.length - 1];
    const dr = Number(latest.daily_return ?? 0);
    const prevVal = navData.length >= 2 ? Number(navData[navData.length - 2].total_value ?? totalValue) : initial;
    return dr * prevVal;
  }, [navData, totalValue, initial]);

  const navCategories = useMemo(() => navData.map((n) => n.nav_date?.slice(5) ?? ''), [navData]);
  const navValues = useMemo(() => navData.map((n) => n.total_value ?? 0), [navData]);
  const perfCategories = useMemo(() => performanceData.map((item) => item.date?.slice(5) ?? ''), [performanceData]);
  const perfReturns = useMemo(
    () => performanceData.map((item) => Number(item.dailyReturn ?? 0) * 100),
    [performanceData],
  );

  useEffect(() => {
    setLoadingGraceExpired(false);
    const timer = window.setTimeout(() => setLoadingGraceExpired(true), 12_000);
    return () => window.clearTimeout(timer);
  }, [activeAccountId, requiresPersonalSession]);

  const accountDataLoading = canLoadAccountQueries && (
    summaryQ.isPending ||
    positionsQ.isPending ||
    ordersQ.isPending ||
    pendingQ.isPending ||
    navQ.isPending ||
    performanceQ.isPending
  );
  const accountDataError = canLoadAccountQueries
    ? summaryQ.error || positionsQ.error || ordersQ.error || pendingQ.error || navQ.error || performanceQ.error
    : null;
  const rawPageLoading =
    (requiresPersonalSession && !queryAccountId && strategyPaperContextQ.isPending) ||
    profileQ.isPending ||
    accountsQ.isPending ||
    matchStatusQ.isPending ||
    navStatusQ.isPending ||
    accountDataLoading;
  const pageLoading = rawPageLoading && !loadingGraceExpired;
  const pageError =
    profileQ.error ||
    accountsQ.error ||
    matchStatusQ.error ||
    navStatusQ.error ||
    accountDataError;
  const error = pageError || refreshPricesApi.error || reconcileApi.error;
  const accountIdRef = useRef(activeAccountId);
  const autoRefreshBusyRef = useRef(false);
  const manualRefreshPendingRef = useRef(refreshPricesApi.isPending);
  const autoRefreshTriggerRef = useRef(autoRefreshPricesApi.triggerAsync);

  useEffect(() => {
    accountIdRef.current = activeAccountId;
  }, [activeAccountId]);

  useEffect(() => {
    manualRefreshPendingRef.current = refreshPricesApi.isPending;
  }, [refreshPricesApi.isPending]);

  useEffect(() => {
    autoRefreshTriggerRef.current = autoRefreshPricesApi.triggerAsync;
  }, [autoRefreshPricesApi.triggerAsync]);

  const handleRefreshPrices = useCallback(async () => {
    if (!canLoadAccountQueries) {
      setFormError('尚未创建个人模拟盘测试，当前不会回退到默认账户。');
      return;
    }
    setFormError(null);
    setFormStatus('正在刷新持仓价格...');
    setLastActionResult(null);
    try {
      const refreshResult = await refreshPricesApi.triggerAsync(
        '/paper-trading/update-prices',
        { method: 'POST' },
        activeAccountId ? { account_id: activeAccountId } : {},
      );
      setFormStatus(null);
      const degradedReason = readDegradedReason(refreshResult);
      if (degradedReason) {
        setFormError(degradedReason);
        setLastActionResult('持仓价格刷新已降级，页面保留当前快照');
      } else {
        toast('持仓价格已刷新', 'success');
        setLastActionResult('持仓价格已刷新');
      }
    } catch (err) {
      setFormStatus(null);
      setFormError(err instanceof Error ? err.message : String(err));
    }
  }, [activeAccountId, canLoadAccountQueries, refreshPricesApi, toast]);

  const handleReconcileLedger = useCallback(async () => {
    if (!canLoadAccountQueries) {
      setFormError('尚未创建个人模拟盘测试，当前不会回退到默认账户。');
      return;
    }
    setFormError(null);
    setFormStatus('正在校准账本与持仓快照...');
    setLastActionResult(null);
    try {
      await reconcileApi.triggerAsync(
        '/paper-trading/reconcile',
        { method: 'POST' },
        activeAccountId ? { account_id: activeAccountId, refresh_prices: true } : { refresh_prices: true },
      );
      toast('账本已完成校准', 'success');
      setFormStatus(null);
      setLastActionResult('账本已完成校准');
    } catch (err) {
      setFormStatus(null);
      setFormError(err instanceof Error ? err.message : String(err));
    }
  }, [activeAccountId, canLoadAccountQueries, reconcileApi, toast]);

  useEffect(() => {
    if (typeof window === 'undefined') return;
    const tick = async () => {
      if (typeof document !== 'undefined' && document.visibilityState === 'hidden') return;
      if (!canLoadAccountQueries) return;
      if (positions.length === 0 && pending.length === 0 && trades.length === 0) return;
      if (!isTradingHours()) return;
      if (manualRefreshPendingRef.current || autoRefreshBusyRef.current) return;
      autoRefreshBusyRef.current = true;
      try {
        await autoRefreshTriggerRef.current(
          '/paper-trading/update-prices',
          { method: 'POST' },
          accountIdRef.current ? { account_id: accountIdRef.current } : {},
        );
      } catch {
        // 静默自动刷新：失败时不打断用户当前操作
      } finally {
        autoRefreshBusyRef.current = false;
      }
    };
    void tick();
    const id = window.setInterval(() => {
      void tick();
    }, 15_000);
    return () => window.clearInterval(id);
  }, [canLoadAccountQueries, pending.length, positions.length, trades.length]);

  async function submitOrder(request: PendingOrderRequest) {
    const { body, idempotencyKey } = request;
    try {
      setFormError(null);
      setLastActionResult(null);
      if (useComplianceCheck) {
        setFormStatus('正在进行合规检查...');
        const complianceRes = await complianceApi.triggerAsync(
          '/paper-trading/check-compliance',
          { method: 'POST' },
          body,
        );
        const compData = complianceRes?.data;
        if (!complianceRes?.success || compData?.status !== 'passed') {
          setFormStatus(null);
          setFormError(`合规检查失败: ${compData?.reason || '触发风控限制'}`);
          return;
        }
      }

      setFormStatus(urgentExecution ? '正在通过智能路由提交订单...' : '正在提交订单...');
      if (urgentExecution) {
        const routeBody: PaperTradingRouteExecutionInput = {
          ...body,
          urgency: 'high',
          idempotency_key: idempotencyKey,
        };
        await routeExecutionApi.triggerAsync(
          '/paper-trading/route-execution',
          { method: 'POST', headers: { 'Idempotency-Key': idempotencyKey } },
          routeBody,
        );
        setLastActionResult('智能路由订单已提交');
      } else {
        await placeApi.triggerAsync(
          '/paper-trading/order',
          { method: 'POST', headers: { 'Idempotency-Key': idempotencyKey } },
          { ...body, idempotency_key: idempotencyKey },
        );
        setLastActionResult('订单已提交');
      }
      setFormStatus(null);
    } catch (err) {
      setFormStatus(null);
      setFormError(err instanceof Error ? err.message : String(err));
    }
  }

  async function handleOrder(e: FormEvent) {
    e.preventDefault();
    setFormError(null);
    setFormStatus(null);
    setLastActionResult(null);
    placeApi.reset();
    if (!validate()) return;
    const qty = parseInt(quantity, 10);
    if (!qty || qty <= 0) {
      setFormError('数量必须大于0');
      return;
    }
    if (direction === 'buy' && qty % 100 !== 0) {
      setFormError('买入数量必须为100的整数倍（手数规则）');
      return;
    }
    if (orderType === 'limit' && (!price || parseFloat(price) <= 0)) {
      setFormError('限价单必须填写有效价格');
      return;
    }
    if (orderType === 'stop' && (!stopPrice || parseFloat(stopPrice) <= 0)) {
      setFormError('止损单必须填写止损价');
      return;
    }
    if (price && parseFloat(price) <= 0) {
      setFormError('价格必须大于0');
      return;
    }
    if (direction === 'buy' && estimatedAmount != null && maxPositionAmount != null && estimatedAmount > maxPositionAmount + 1e-6) {
      setFormError(`当前委托预估金额 ${fmtNum(estimatedAmount)} 超过单股仓位上限 ${fmtNum(maxPositionAmount)}（${fmtPct(maxPositionPct)}）`);
      return;
    }

    const body: PaperTradingPlaceOrderInput = {
      code: trimmedCode,
      direction,
      quantity: qty,
      order_type: orderType,
    };
    if (orderType === 'limit' && price) body.price = parseFloat(price);
    if (orderType === 'stop' && stopPrice) body.stop_price = parseFloat(stopPrice);
    if (orderType === 'market' && price) body.price = parseFloat(price);
    if (activeAccountId) body.account_id = activeAccountId;

    const request = {
      body,
      idempotencyKey: createIdempotencyKey('paper-order'),
    } satisfies PendingOrderRequest;

    if (confirmPrefs.paperOrder) {
      setPendingOrderRequest(request);
      return;
    }

    await submitOrder(request);
  }

  async function confirmOrder() {
    if (!pendingOrderRequest) return;
    const request = pendingOrderRequest;
    setPendingOrderRequest(null);
    await submitOrder(request);
  }

  async function submitCancel(request: PendingCancelRequest) {
    const { orderId, idempotencyKey } = request;
    setCancelingOrderIds((prev) => (prev.includes(orderId) ? prev : [...prev, orderId]));
    try {
      setFormError(null);
      setFormStatus(`正在撤销订单 #${orderId}...`);
      setLastActionResult(null);
      const body: PaperTradingCancelOrderInput = {
        order_id: String(orderId),
        idempotency_key: idempotencyKey,
      };
      await cancelApi.triggerAsync(
        '/paper-trading/cancel',
        { method: 'POST', headers: { 'Idempotency-Key': idempotencyKey } },
        body,
      );
      setFormStatus(null);
      setLastActionResult(`订单 #${orderId} 已撤销`);
    } catch (err) {
      setFormStatus(null);
      setFormError(err instanceof Error ? err.message : String(err));
    } finally {
      setCancelingOrderIds((prev) => prev.filter((item) => item !== orderId));
    }
  }

  async function handleCancel(orderId: number) {
    const request = {
      orderId,
      idempotencyKey: createIdempotencyKey(`paper-cancel-${orderId}`),
    } satisfies PendingCancelRequest;
    if (confirmPrefs.paperCancel) {
      setPendingCancelRequest(request);
      return;
    }
    await submitCancel(request);
  }

  async function confirmCancel() {
    if (!pendingCancelRequest) return;
    const request = pendingCancelRequest;
    setPendingCancelRequest(null);
    await submitCancel(request);
  }

  const handleTestCleanup = useCallback(async () => {
    if (!activeAccountId || !isSandboxAccount(activeAccountId)) {
      setFormError('测试清理只允许 sandbox/test/demo/qa/playwright/paper-audit 账户');
      return;
    }
    setFormError(null);
    setFormStatus('正在清理测试账户挂单、测试持仓并刷新对账...');
    try {
      const cleanup = await cleanupApi.triggerAsync(
        '/paper-trading/test-cleanup',
        { method: 'POST' },
        { account_id: activeAccountId, include_filled_positions: true },
      );
      setFormStatus(null);
      const cancelled = Number(cleanup?.cancelled_count ?? 0);
      const positions = Number(cleanup?.filled_positions_count ?? 0);
      const failed = Number(cleanup?.failed_count ?? 0);
      setLastActionResult(`测试账户清理已完成：取消 ${cancelled}，重置持仓 ${positions}，失败 ${failed}`);
      await refreshPaperData();
    } catch (err) {
      setFormStatus(null);
      setFormError(err instanceof Error ? err.message : String(err));
    }
  }, [activeAccountId, cleanupApi, refreshPaperData]);

  function quickSell(position: PaperTradingPosition) {
    const sellable = Number(position.sellable ?? position.quantity ?? 0);
    if (!Number.isFinite(sellable) || sellable <= 0) {
      setFormError('当前持仓暂无可卖数量');
      return;
    }
    setDirection('sell');
    setCode(String(position.stock_code ?? ''));
    setQuantity(String(Math.floor(sellable)));
    setOrderType('market');
    setPrice('');
    setStopPrice('');
    setFormError(null);
    setFormStatus(`已载入 ${String(position.stock_code ?? '')} 的快速卖出参数，请确认后提交。`);
  }

  const matchStatusLabel = matchOk ? '运行中' : showAccountBootstrap ? '待确认' : '待检查';
  const navStatusLabel = navOk ? '运行中' : showAccountBootstrap ? '待确认' : '待检查';
  const missingPersonalSession =
    requiresPersonalSession
    && !queryAccountId
    && !resolvedPersonalAccountId
    && !strategyPaperContextQ.isPending;
  const accountDisplayId = activeAccountId || (requiresPersonalSession ? '未创建个人盘' : '未选择账户');

  useEffect(() => {
    if (!workbenchHydrated) return;
    const workspaceChanged = lastWorkspaceIdRef.current !== activeWorkspaceId;
    lastWorkspaceIdRef.current = activeWorkspaceId;
    if (!workspaceChanged) return;
    setCode(queryStockCode || (workbenchContext.stockCode ?? ''));
    if (queryAccountId) {
      setAccountId(queryAccountId);
      return;
    }
    if (requiresPersonalSession) {
      setAccountId(resolvedPersonalAccountId || '');
      return;
    }
    setAccountId(workspaceAccountId || firstAccountId || '');
  }, [
    activeWorkspaceId,
    firstAccountId,
    queryAccountId,
    queryStockCode,
    requiresPersonalSession,
    resolvedPersonalAccountId,
    setCode,
    workspaceAccountId,
    workbenchContext.stockCode,
    workbenchHydrated,
  ]);

  useEffect(() => {
    if (!workbenchHydrated) return;
    if (queryStockCode) {
      setCode(queryStockCode);
    }
    if (queryAccountId) {
      setAccountId(queryAccountId);
      return;
    }
    if (requiresPersonalSession) {
      setAccountId(resolvedPersonalAccountId || '');
      return;
    }
    if (!accountId && (workspaceAccountId || firstAccountId)) {
      setAccountId(workspaceAccountId || firstAccountId);
    }
  }, [accountId, firstAccountId, queryAccountId, queryStockCode, requiresPersonalSession, resolvedPersonalAccountId, setCode, workspaceAccountId, workbenchHydrated]);

  useEffect(() => {
    if (!workbenchHydrated) return;
    updateWorkbenchContext({
      stockCode: trimmedCode || null,
      accountId: activeAccountId || null,
      strategyId: linkedStrategyId || null,
      strategyName: linkedStrategyName || null,
      linkedStrategyId: linkedStrategyId || null,
      linkedStrategyName: linkedStrategyName || null,
      mode: personalStrategyMode ? 'personal-strategy' : 'account',
      strategyTestMode: personalStrategyMode ? 'personal-strategy' : null,
    });
  }, [
    activeAccountId,
    linkedStrategyId,
    linkedStrategyName,
    personalStrategyMode,
    trimmedCode,
    updateWorkbenchContext,
    workbenchHydrated,
  ]);

  const pageActions = useMemo(
    () => [
      {
        id: 'paper.refresh',
        label: '刷新模拟盘',
        description: '刷新账户、持仓、订单、净值和绩效数据',
        keywords: ['刷新', '模拟盘'],
        scope: 'page' as const,
        pageKey: 'paper-trading',
        run: async () => {
          await refreshPaperData();
          return { message: '已刷新模拟盘数据' };
        },
      },
      {
        id: 'paper.refresh-prices',
        label: '刷新持仓价格',
        description: '刷新当前模拟盘持仓价格',
        keywords: ['刷新', '价格'],
        scope: 'page' as const,
        pageKey: 'paper-trading',
        run: async () => {
          await handleRefreshPrices();
          return { message: '已触发持仓价格刷新' };
        },
      },
      {
        id: 'paper.reconcile',
        label: '校准账本',
        description: '基于成交账本重建持仓和账户快照',
        keywords: ['校准', '对账', '账本'],
        scope: 'page' as const,
        pageKey: 'paper-trading',
        run: async () => {
          await handleReconcileLedger();
          return { message: '已触发账本校准' };
        },
      },
      {
        id: 'paper.test-cleanup',
        label: '清理测试账户',
        description: '仅 sandbox/test/demo/qa 账户可用，取消测试挂单并刷新对账',
        keywords: ['清理', '测试账户', 'cleanup'],
        scope: 'page' as const,
        pageKey: 'paper-trading',
        run: async () => {
          await handleTestCleanup();
          return { message: '已触发测试账户清理' };
        },
      },
      {
        id: 'paper.toggle-compliance',
        label: useComplianceCheck ? '关闭合规检查' : '开启合规检查',
        description: '切换下单前的合规风控检查',
        keywords: ['合规', '风控'],
        scope: 'page' as const,
        pageKey: 'paper-trading',
        run: () => {
          setUseComplianceCheck((prev) => !prev);
          return { message: useComplianceCheck ? '已关闭合规检查' : '已开启合规检查' };
        },
      },
    ],
    [handleReconcileLedger, handleRefreshPrices, handleTestCleanup, refreshPaperData, useComplianceCheck],
  );

  usePageActions(pageActions);
  const paperSummary = `账户 ${accountDisplayId}，持仓 ${positions.length} 条，挂单 ${pending.length} 条，订单 ${trades.length} 条，总资产 ${fmtNum(totalValue, 2)}。${linkedStrategyName ? ` 当前策略 ${linkedStrategyName}。` : ''}`;
  const paperResult = buildLocalResultContract({
    summary: paperSummary,
    status: showAccountBootstrap ? 'empty' : (!matchOk || !navOk ? 'degraded' : 'ready'),
    availableViews: positions.length > 1 || pending.length > 1 || trades.length > 1 ? ['compare'] : [],
    pageActions,
    preferredActionIds: ['paper.refresh', 'paper.refresh-prices', 'paper.reconcile', 'paper.test-cleanup', 'paper.toggle-compliance'],
    recommendedLinks: [
      { id: 'paper-open-assistant-link', label: '继续问 Copilot', href: '/assistant' },
      { id: 'paper-open-performance-link', label: '绩效中心', href: '/performance' },
      { id: 'paper-open-risk-link', label: '风险中心', href: '/risk' },
      { id: 'paper-open-strategy-market-link', label: '策略超市', href: linkedStrategyId ? `/strategy-market/${encodeURIComponent(linkedStrategyId)}` : '/strategy-market' },
    ],
    recommendedNextActions: [
      showAccountBootstrap ? '先完成第一笔真实模拟委托，再回来看账户分析和活动记录。' : '先确认账户健康和挂单状态，再决定是否继续下单。',
      !matchOk || !navOk ? '撮合或净值未完全正常时，优先刷新价格或校准账本。' : '账户健康正常时，再进入绩效或风险闭环。',
    ],
    evidence: [
      { label: '账户', value: accountDisplayId },
      { label: '持仓数', value: String(positions.length) },
      { label: '挂单数', value: String(pending.length) },
      { label: '订单数', value: String(trades.length) },
      { label: '总资产', value: fmtNum(totalValue, 2) },
    ],
    riskNotes: [...statusNotes, ...riskHints.slice(0, 3), ...(error ? [error] : [])],
    emptyState: showAccountBootstrap ? {
      title: '账户还没有形成交易轨迹',
      description: '先输入真实标的和委托参数，再提交首笔模拟交易。',
      example: 'code=600519，direction=buy，quantity=100',
    } : null,
    degradedState: !matchOk || !navOk ? {
      title: '交易链路当前未完全就绪',
      description: '先刷新价格或校准账本，再继续解释持仓和绩效。',
      reason: [
        matchOk ? null : readStatusProbeNote(matchStatus, '撮合服务尚未就绪'),
        navOk ? null : readStatusProbeNote(navStatus, '净值服务尚未就绪'),
      ].filter((item): item is string => Boolean(item)).join('；'),
    } : null,
    freshness: summaryQ.dataUpdatedAt ? { updatedAt: new Date(summaryQ.dataUpdatedAt).toISOString(), label: '模拟盘快照' } : null,
    platformMeta: {
      sourceTool: 'paper-trading',
      sourceChain: ['paper-trading', accountDisplayId],
      degraded: Boolean(error) || !matchOk || !navOk,
      fallbackReason: [error, !matchOk ? '撮合状态未确认' : null, !navOk ? '净值状态未确认' : null].filter((item): item is string => Boolean(item)),
    },
    workbenchTask: defaultWorkbenchTask(
      'paper-trading',
      `复查模拟盘${linkedStrategyName ? ` · ${linkedStrategyName}` : ''}`,
      linkedStrategyId ? `/paper-trading?strategy_id=${encodeURIComponent(linkedStrategyId)}` : '/paper-trading',
      'paper-trading-review',
      { accountId: accountDisplayId, stockCode: trimmedCode || null, linkedStrategyId: linkedStrategyId || null },
    ),
  });

  usePageContext({
    pageKey: 'paper-trading',
    title: personalStrategyMode && linkedStrategyName ? `模拟交易 · ${linkedStrategyName}` : '模拟交易',
    summary: paperSummary,
    primaryGoal: '先确认账户健康和订单输入，再把交易动作落到真实模拟链路里。',
    requiredInputs: ['accountId', 'stockCode', 'direction', 'quantity'],
    stockCode: trimmedCode || undefined,
    objectType: 'portfolio',
    objectId: accountDisplayId,
    resultType: 'paper-trading-dashboard',
    tags: [
      `${positions.length} 条持仓`,
      `${pending.length} 条挂单`,
      `${trades.length} 条订单`,
      linkedStrategyName ? `策略 ${linkedStrategyName}` : null,
      personalStrategyMode ? '个人模拟盘测试' : null,
      useComplianceCheck ? '合规检查开启' : '标准提交流程',
    ].filter((item): item is string => Boolean(item)),
    suggestions: [
      trimmedCode ? `评估 ${trimmedCode} 当前下单参数是否合理` : '评估当前模拟盘状态',
      '总结账户表现、持仓和待处理订单',
      '把当前模拟盘整理成下一步操作清单',
    ],
    recommendedNextActions: paperResult.recommendedNextActions,
    recommendedActions: paperResult.recommendedActions ?? [],
    recommendedLinks: paperResult.recommendedLinks ?? [],
    evidenceSummary: evidenceToSummary(paperResult.evidence),
    riskNotes: paperResult.riskNotes ?? [],
    freshness: paperResult.freshness ?? null,
    dataFreshness: paperResult.freshness?.updatedAt ?? null,
    degradedReason: paperResult.riskNotes ?? [],
    raw: {
      accountId: accountDisplayId,
      stockCode: trimmedCode || null,
      positionCount: positions.length,
      pendingCount: pending.length,
      orderCount: trades.length,
      totalValue,
      linkedStrategyId: linkedStrategyId || null,
      linkedStrategyName: linkedStrategyName || null,
      personalStrategyMode,
      urgentExecution,
      useComplianceCheck,
    },
  });

  const currentView = useMemo<Record<string, unknown>>(
    () => ({
      code,
      direction,
      quantity,
      price,
      orderType,
      stopPrice,
      accountId: activeAccountId,
      useComplianceCheck,
      urgentExecution,
      perfDays,
    }),
    [activeAccountId, code, direction, orderType, perfDays, price, quantity, stopPrice, urgentExecution, useComplianceCheck],
  );

  const applyView = useCallback(
    (snapshot: Record<string, unknown>) => {
      if (typeof snapshot.code === 'string') {
        setCode(snapshot.code);
      }
      if (snapshot.direction === 'buy' || snapshot.direction === 'sell') {
        setDirection(snapshot.direction);
      }
      if (typeof snapshot.quantity === 'string' || typeof snapshot.quantity === 'number') {
        setQuantity(String(snapshot.quantity));
      }
      if (typeof snapshot.price === 'string' || typeof snapshot.price === 'number') {
        setPrice(String(snapshot.price));
      }
      if (snapshot.orderType === 'market' || snapshot.orderType === 'limit' || snapshot.orderType === 'stop') {
        setOrderType(snapshot.orderType);
      }
      if (typeof snapshot.stopPrice === 'string' || typeof snapshot.stopPrice === 'number') {
        setStopPrice(String(snapshot.stopPrice));
      }
      if (typeof snapshot.accountId === 'string') {
        setAccountId(snapshot.accountId);
      }
      if (typeof snapshot.useComplianceCheck === 'boolean') {
        setUseComplianceCheck(snapshot.useComplianceCheck);
      }
      if (typeof snapshot.urgentExecution === 'boolean') {
        setUrgentExecution(snapshot.urgentExecution);
      }
      if (typeof snapshot.perfDays === 'number') {
        setPerfDays(snapshot.perfDays);
      }
    },
    [setCode],
  );

  const primaryContent = (
    <>
      <div>
        <PaperTradingHero
          compactMobile={collapseToTabs}
          showAccountBootstrap={showAccountBootstrap}
          matchOk={matchOk}
          navOk={navOk}
          matchStatusLabel={matchStatusLabel}
          navStatusLabel={navStatusLabel}
          trimmedCode={trimmedCode}
          directionLabel={directionLabel}
          orderTypeLabel={orderTypeLabel}
          estimatedAmount={estimatedAmount}
          previewUnitPrice={previewUnitPrice}
          accountId={activeAccountId}
          positionsCount={positions.length}
          pendingCount={pending.length}
          tradesCount={trades.length}
          totalValue={totalValue}
          todayPnl={todayPnl}
          returnPct={Number(returnPct)}
          quantityValue={quantityValue}
          useComplianceCheck={useComplianceCheck}
          urgentExecution={urgentExecution}
          riskHints={riskHints}
          tradeNotice={tradeNotice}
          error={error}
          linkedStrategyId={linkedStrategyId || null}
          linkedStrategyName={linkedStrategyName || null}
          linkedStrategyStatus={linkedStrategyStatus}
          personalStrategyMode={personalStrategyMode}
          onRefreshPrices={() => void handleRefreshPrices()}
          refreshPricesPending={refreshPricesApi.isPending}
          onReconcileLedger={() => void handleReconcileLedger()}
          reconcilePending={reconcileApi.isPending}
        />
      </div>

      <div className="space-y-2">
        <DataQualityBanner trust={summaryQ.trust} title="模拟盘资产数据质量" onRetry={() => void summaryQ.refetch()} />
        <DataQualityBanner trust={positionsQ.trust} title="模拟盘持仓数据质量" onRetry={() => void positionsQ.refetch()} />
        <DataQualityBanner trust={performanceQ.trust} title="模拟盘绩效数据质量" onRetry={() => void performanceQ.refetch()} />
      </div>

      {!collapseToTabs && trustStatus ? <PaperTradingTrustStatusCard status={trustStatus} /> : null}

      {!collapseToTabs ? (
        <SectionCard className="mb-4 p-4">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <h3 className="m-0 text-sm font-semibold text-text-primary">测试数据清理</h3>
              <p className="mt-1 mb-0 text-xs text-text-secondary">
                仅 sandbox/test/demo/qa/playwright/paper-audit 账户可用；可取消挂单并重置测试持仓，真实或默认账户会被拒绝。
              </p>
            </div>
            <button
              type="button"
              onClick={() => void handleTestCleanup()}
              disabled={!activeAccountId || !isSandboxAccount(activeAccountId) || cleanupApi.isPending}
              className="action-chip cursor-pointer text-sm text-text-primary disabled:cursor-not-allowed disabled:opacity-50"
            >
              {cleanupApi.isPending ? '清理中...' : '清理测试账户'}
            </button>
          </div>
        </SectionCard>
      ) : null}

      {!collapseToTabs ? (
        <ProgressiveWorkbenchSection
          pageKey="paper-trading"
          title="模拟盘结果工作台"
          result={paperResult}
          summaryMode="strip"
        />
      ) : null}

      {showAccountBootstrap || !matchOk || !navOk ? (
        !collapseToTabs ? (
          <PageStatusCard
            status={showAccountBootstrap ? 'empty' : 'degraded'}
            title={showAccountBootstrap ? '先完成第一笔模拟交易' : '交易链路当前未完全就绪'}
            reason={
              showAccountBootstrap
                ? '当前还没有持仓、挂单、成交和净值轨迹，请先提交首笔真实模拟委托。'
                : [
                    matchOk ? null : readStatusProbeNote(matchStatus, '撮合服务尚未就绪'),
                    navOk ? null : readStatusProbeNote(navStatus, '净值服务尚未就绪'),
                  ].filter((item): item is string => Boolean(item)).join('；')
            }
            freshness={summaryQ.dataUpdatedAt ? new Date(summaryQ.dataUpdatedAt).toLocaleString('zh-CN') : null}
            primaryAction={(
              <button type="button" onClick={() => void handleRefreshPrices()} className="action-chip cursor-pointer text-sm text-text-primary">
                刷新价格
              </button>
            )}
            secondaryAction={(
              <button type="button" onClick={() => void handleReconcileLedger()} className="action-chip cursor-pointer text-sm text-text-primary">
                校准账本
              </button>
            )}
            example="code=600519，direction=buy，quantity=100"
            className="mb-4"
          />
        ) : null
      ) : null}

      {collapseToTabs ? (
        <div className="mb-4">
          <TabBar tabs={PAPER_TRADING_MOBILE_PRIMARY_TABS} active={mobilePrimaryTab} onChange={setMobilePrimaryTab} />
        </div>
      ) : null}

      {!collapseToTabs || mobilePrimaryTab === 'order' ? (
        <div>
          <PaperTradingOrderWorkspace
            showAccountBootstrap={showAccountBootstrap}
            handleOrder={handleOrder}
            code={code}
            setCode={setCode}
            codeError={codeError}
            direction={direction}
            setDirection={setDirection}
            quantity={quantity}
            setQuantity={setQuantity}
            orderType={orderType}
            setOrderType={setOrderType}
            price={price}
            setPrice={setPrice}
            stopPrice={stopPrice}
            setStopPrice={setStopPrice}
            useComplianceCheck={useComplianceCheck}
            setUseComplianceCheck={setUseComplianceCheck}
            urgentExecution={urgentExecution}
            setUrgentExecution={setUrgentExecution}
            placePending={placeApi.isPending}
            routeExecutionPending={routeExecutionApi.isPending}
            compliancePending={complianceApi.isPending}
            directionLabel={directionLabel}
            orderTypeLabel={orderTypeLabel}
            trimmedCode={trimmedCode}
            quantityValue={quantityValue}
            accountId={activeAccountId}
            previewUnitPrice={previewUnitPrice}
            estimatedAmount={estimatedAmount}
            riskHints={riskHints}
            formError={formError}
            formStatus={formStatus}
            lastActionResult={lastActionResult}
          />
        </div>
      ) : null}

      {!collapseToTabs || mobilePrimaryTab === 'analytics' ? (
        <PaperTradingAnalytics
          showAccountBootstrap={showAccountBootstrap}
          matchOk={matchOk}
          navOk={navOk}
          matchStatusLabel={matchStatusLabel}
          navStatusLabel={navStatusLabel}
          onRefreshPrices={() => void handleRefreshPrices()}
          refreshPricesPending={refreshPricesApi.isPending}
          onReconcileLedger={() => void handleReconcileLedger()}
          reconcilePending={reconcileApi.isPending}
          accounts={accounts}
          accountId={activeAccountId}
          onAccountChange={setAccountId}
          statusNotes={statusNotes}
          totalValue={totalValue}
          cash={cash}
          marketValue={marketValue}
          returnPct={Number(returnPct)}
          todayPnl={todayPnl}
          perfDays={perfDays}
          onPerfDaysChange={setPerfDays}
          performanceData={performanceData}
          performanceMetrics={performanceMetrics}
          perfCategories={perfCategories}
          perfReturns={perfReturns}
        />
      ) : null}

      {!collapseToTabs || mobilePrimaryTab === 'activity' ? (
        <PaperTradingActivity
          showAccountBootstrap={showAccountBootstrap}
          positions={positions}
          onQuickSell={quickSell}
          pending={pending}
          cancelingOrderIds={cancelingOrderIds}
          onCancel={(orderId) => {
            void handleCancel(orderId);
          }}
          trades={trades as PaperTradingTrade[]}
          navData={navData}
          navCategories={navCategories}
          navValues={navValues}
        />
      ) : null}

      <ConfirmDialog
        open={!!pendingOrderRequest}
        title={`确认${pendingOrderRequest?.body.direction === 'buy' ? '买入' : '卖出'}`}
        onConfirm={confirmOrder}
        onCancel={() => setPendingOrderRequest(null)}
        confirmText="确认下单"
        cancelText="取消"
        danger={pendingOrderRequest?.body.direction === 'sell'}
      >
        {pendingOrderRequest && (
          <div className="space-y-1 text-sm">
            <div>
              标的：<span className="font-medium">{String(pendingOrderRequest.body.code)}</span>
            </div>
            <div>
              方向：
              <span
                className={`font-medium ${pendingOrderRequest.body.direction === 'buy' ? 'text-danger' : 'text-success'}`}
              >
                {pendingOrderRequest.body.direction === 'buy' ? '买入' : '卖出'}
              </span>
            </div>
            <div>
              数量：<span className="font-medium">{String(pendingOrderRequest.body.quantity)} 股</span>
            </div>
            <div>
              类型：
              <span className="font-medium">
                {pendingOrderRequest.body.order_type === 'market'
                  ? '市价单'
                  : pendingOrderRequest.body.order_type === 'limit'
                    ? '限价单'
                    : '止损单'}
              </span>
            </div>
            {pendingOrderRequest.body.price ? (
              <div>
                价格：<span className="font-medium">{String(pendingOrderRequest.body.price)}</span>
              </div>
            ) : null}
            {pendingOrderRequest.body.stop_price ? (
              <div>
                止损价：<span className="font-medium">{String(pendingOrderRequest.body.stop_price)}</span>
              </div>
            ) : null}
            {pendingOrderRequest.body.price ? (
              <div>
                预估金额：
                <span className="font-medium">
                  {fmtNum(Number(pendingOrderRequest.body.price) * Number(pendingOrderRequest.body.quantity))}
                </span>
              </div>
            ) : null}
          </div>
        )}
      </ConfirmDialog>

      {/* 撤单确认弹窗 */}
      <ConfirmDialog
        open={pendingCancelRequest != null}
        title="确认撤单"
        message={`确定要撤销订单 #${pendingCancelRequest?.orderId ?? '-'} 吗？`}
        onConfirm={confirmCancel}
        onCancel={() => setPendingCancelRequest(null)}
        confirmText="确认撤单"
        danger
      />
    </>
  );

  const secondaryContent = (
    <div>
      <PaperTradingSummarySidebar
        accountId={activeAccountId}
        trimmedCode={trimmedCode}
        directionLabel={directionLabel}
        orderTypeLabel={orderTypeLabel}
        estimatedAmount={estimatedAmount}
        positionsCount={positions.length}
        pendingCount={pending.length}
        tradesCount={trades.length}
        matchStatusLabel={matchStatusLabel}
        navStatusLabel={navStatusLabel}
        totalValue={totalValue}
        perfDays={perfDays}
        todayPnl={todayPnl}
        useComplianceCheck={useComplianceCheck}
        urgentExecution={urgentExecution}
      />
    </div>
  );

  if (missingPersonalSession) {
    return (
      <PageContainer>
        <PageStatusCard
          status="empty"
          title="尚未创建个人模拟盘测试"
          reason={`${String(personalTrack?.reason ?? '当前策略还没有 personal paper session').trim() || '当前策略还没有 personal paper session'}，不会回退到默认账户。`}
          primaryAction={(
            linkedStrategyId ? (
              <Link
                href={`/strategy-market/${encodeURIComponent(linkedStrategyId)}`}
                className="action-chip text-sm no-underline text-inherit"
              >
                返回策略详情
              </Link>
            ) : undefined
          )}
          secondaryAction={(
            <button type="button" onClick={() => void refreshPaperData()} className="action-chip cursor-pointer text-sm text-text-primary">
              重新检查
            </button>
          )}
          example={linkedStrategyName ? `从“${linkedStrategyName}”详情页点击“创建模拟盘测试”` : '从策略详情页点击“创建模拟盘测试”'}
        />
      </PageContainer>
    );
  }

  if (pageLoading && !pageError && !summaryQ.data) {
    return (
      <PageContainer>
        <div className="space-y-3">
          <PageStatusCard
            status="loading"
            title="正在准备模拟交易工作区"
            reason="账户、挂单、持仓、净值和绩效正在同步。若停留过久，可以主动刷新；如果只是先看机会，也可以先回行情页继续观察。"
            primaryAction={(
              <button type="button" onClick={() => void refreshPaperData()} className="action-chip cursor-pointer text-sm text-text-primary">
                刷新模拟盘
              </button>
            )}
            secondaryAction={<Link href="/market" className="action-chip text-sm no-underline text-inherit">先去行情页</Link>}
            example="code=600519，direction=buy，quantity=100"
          />
          <LoadingState text="正在加载模拟交易账户、持仓与绩效数据..." />
        </div>
      </PageContainer>
    );
  }

  if (pageError) {
    return (
      <PageContainer>
        <PageStatusCard
          status="unavailable"
          title="模拟交易主链路暂不可用"
          reason={pageError}
          freshness={summaryQ.dataUpdatedAt ? new Date(summaryQ.dataUpdatedAt).toLocaleString('zh-CN') : null}
          primaryAction={(
            <button type="button" onClick={() => void refreshPaperData()} className="action-chip cursor-pointer text-sm text-text-primary">
              重试加载
            </button>
          )}
          secondaryAction={<Link href="/market" className="action-chip text-sm no-underline text-inherit">先去行情页</Link>}
          example="请确认账户 ID 存在；测试清理仅支持 sandbox / demo / test / qa / playwright / paper-audit 账户。"
        />
      </PageContainer>
    );
  }

  return (
    <PageContainer>
      <WorkspaceToolbar
        pageKey="paper-trading"
        currentView={currentView}
        onApplyView={applyView}
        supportsPagePanels
        mobileSummaryMode="hidden"
      />
      <WorkspaceSplitLayout
        pageKey="paper-trading"
        primary={primaryContent}
        secondary={secondaryContent}
        primaryLabel="交易主区"
        secondaryLabel="交易摘要"
        defaultMobileTab="primary"
      />
    </PageContainer>
  );
}
