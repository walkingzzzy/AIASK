'use client';

import { FormEvent, useMemo, useState, useCallback, useEffect, useRef } from 'react';
import PaperTradingActivity from '@/app/paper-trading/components/paper-trading-activity';
import PaperTradingAnalytics from '@/app/paper-trading/components/paper-trading-analytics';
import PaperTradingHero from '@/app/paper-trading/components/paper-trading-hero';
import PaperTradingOrderWorkspace from '@/app/paper-trading/components/paper-trading-order-workspace';
import PaperTradingSummarySidebar from '@/app/paper-trading/components/paper-trading-summary-sidebar';
import WorkspaceSplitLayout from '@/components/workspace-split-layout';
import WorkspaceToolbar from '@/components/workspace-toolbar';
import { PageContainer } from '@/components/ui';
import { ConfirmDialog } from '@/components/ui/confirm-dialog';
import { useToast } from '@/components/ui/toast';
import { useApiQuery } from '@/hooks/use-api-query';
import { useApiMutation } from '@/hooks/use-api-mutation';
import { usePageActions } from '@/hooks/use-page-actions';
import { usePageContext } from '@/hooks/use-page-context';
import { apiKeys } from '@/lib/query-keys';
import { useStockCode } from '@/hooks/use-stock-code';
import { extractArray, fmtNum, fmtPct } from '@/lib/data-utils';
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
  PaperTradingRouteExecutionInput,
  PaperTradingStatusProbe,
  PaperTradingSummary,
  PaperTradingTrade,
} from '@aiask/shared-types';

type PendingOrderRequest = {
  body: PaperTradingPlaceOrderInput;
  idempotencyKey: string;
};

type PendingCancelRequest = {
  orderId: number;
  idempotencyKey: string;
};

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

export default function PaperTradingPage() {
  const { toast } = useToast();
  const workbenchHydrated = useWorkbenchStore((state) => state.hydrated);
  const activeWorkspaceId = useWorkbenchStore((state) => state.activeWorkspaceId);
  const workbenchContext = useWorkbenchStore((state) => selectActiveWorkspace(state).context);
  const updateWorkbenchContext = useWorkbenchStore((state) => state.updateContext);
  const lastWorkspaceIdRef = useRef<string | null>(null);
  const { code, setCode, codeError, validate, trimmedCode } = useStockCode('600519');
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

  const qs = accountId ? `?account_id=${accountId}` : '';

  // 8 read queries — auto-fetch on mount, re-fetch when qs changes
  const profileQ = useApiQuery<Record<string, unknown>>('/auth/profile');
  const accountsQ = useApiQuery<PaperTradingAccountsResponse | PaperTradingAccount[]>('/paper-trading/accounts');
  const matchStatusQ = useApiQuery<PaperTradingStatusProbe>('/paper-trading/matching-status');
  const navStatusQ = useApiQuery<PaperTradingStatusProbe>('/paper-trading/nav-status');
  const summaryQ = useApiQuery<PaperTradingSummary>(qs ? '/paper-trading/summary' + qs : '/paper-trading/summary');
  const positionsQ = useApiQuery<PaperTradingPositionsResponse>('/paper-trading/positions' + qs);
  const ordersQ = useApiQuery<PaperTradingOrdersResponse>('/paper-trading/orders' + qs);
  const pendingQ = useApiQuery<PaperTradingPendingOrdersResponse>('/paper-trading/pending-orders' + qs);
  const navQ = useApiQuery<PaperTradingNavHistoryResponse>('/paper-trading/nav-history' + qs);
  const performanceQ = useApiQuery<PaperTradingPerformanceResponse>(
    `/paper-trading/performance${qs ? `${qs}&days=${perfDays}` : `?days=${perfDays}`}`,
  );

  // Subscribe to trade updates via WS
  useTradeSubscription({ accountId: accountId || 'default', onUpdate: handleTradeUpdate });

  // Advanced MCP Managers (Compliance & Execution)
  const [useComplianceCheck, setUseComplianceCheck] = useState(false);
  const [urgentExecution, setUrgentExecution] = useState(false);
  const complianceApi = useApiMutation<CompliancePayload>();
  const routeExecutionApi = useApiMutation<Record<string, unknown>>({ invalidates: [[...apiKeys.paper()]] });
  const refreshPricesApi = useApiMutation<Record<string, unknown>>({
    invalidates: [[...apiKeys.paper()]],
    successToast: false,
  });
  const autoRefreshPricesApi = useApiMutation<Record<string, unknown>>({
    invalidates: [[...apiKeys.paper()]],
    successToast: false,
    errorToast: false,
  });

  // 2 write mutations — invalidate all paper queries on success
  const placeApi = useApiMutation<Record<string, unknown>>({ invalidates: [[...apiKeys.paper()]] });
  const cancelApi = useApiMutation<Record<string, unknown>>({ invalidates: [[...apiKeys.paper()]] });

  const accounts = useMemo(
    () => extractArray(accountsQ.data, 'accounts', 'items', 'data') as PaperTradingAccount[],
    [accountsQ.data],
  );
  const matchStatus = useMemo(() => matchStatusQ.data ?? {}, [matchStatusQ.data]);
  const navStatus = useMemo(() => navStatusQ.data ?? {}, [navStatusQ.data]);
  const matchOk = matchStatus.status === 'running' || matchStatus.running === true || matchStatus.ok === true;
  const navOk = navStatus.status === 'running' || navStatus.running === true || navStatus.ok === true;

  const acct = summaryQ.data?.account ?? undefined;
  const totalValue = Number(summaryQ.data?.total_value ?? acct?.total_value ?? 0);
  const cash = Number(acct?.current_capital ?? 0);
  const initial = Number(acct?.initial_capital ?? 100000);
  const marketValue = totalValue - cash;
  const returnPct = summaryQ.data?.total_return_pct ?? (initial > 0 ? ((totalValue - initial) / initial) * 100 : 0);

  const positions = positionsQ.data?.positions ?? [];
  const trades = ordersQ.data?.orders ?? [];
  const pending = pendingQ.data?.orders ?? [];
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
    return notes;
  }, [matchOk, matchStatus, navOk, navStatus]);
  const quantityValue = Number.parseInt(quantity, 10);
  const limitPriceValue = price.trim() ? Number(price) : null;
  const stopPriceValue = stopPrice.trim() ? Number(stopPrice) : null;
  const previewUnitPrice = orderType === 'stop' ? stopPriceValue : limitPriceValue;
  const estimatedAmount = useMemo(() => {
    if (!Number.isFinite(quantityValue) || quantityValue <= 0) return null;
    if (previewUnitPrice == null || !Number.isFinite(previewUnitPrice) || previewUnitPrice <= 0) return null;
    return quantityValue * previewUnitPrice;
  }, [previewUnitPrice, quantityValue]);
  const orderTypeLabel = orderType === 'market' ? '市价单' : orderType === 'limit' ? '限价单' : '止损单';
  const directionLabel = direction === 'buy' ? '买入' : '卖出';
  const riskHints = useMemo(() => {
    const hints: string[] = [];
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
    if (useComplianceCheck) hints.push('已开启下单前合规风控，提交时会先做额外检查。');
    if (urgentExecution) hints.push('已开启极速智能路由，提交成功文案会与普通委托不同。');
    if (!useComplianceCheck && !urgentExecution) hints.push('当前为标准提交流程：直接确认并提交委托。');
    return hints;
  }, [
    direction,
    limitPriceValue,
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

  const error = summaryQ.error || positionsQ.error || refreshPricesApi.error;
  const accountIdRef = useRef(accountId);
  const autoRefreshBusyRef = useRef(false);
  const manualRefreshPendingRef = useRef(refreshPricesApi.isPending);
  const autoRefreshTriggerRef = useRef(autoRefreshPricesApi.triggerAsync);

  useEffect(() => {
    accountIdRef.current = accountId;
  }, [accountId]);

  useEffect(() => {
    manualRefreshPendingRef.current = refreshPricesApi.isPending;
  }, [refreshPricesApi.isPending]);

  useEffect(() => {
    autoRefreshTriggerRef.current = autoRefreshPricesApi.triggerAsync;
  }, [autoRefreshPricesApi.triggerAsync]);

  const handleRefreshPrices = useCallback(async () => {
    setFormError(null);
    setFormStatus('正在刷新持仓价格...');
    setLastActionResult(null);
    try {
      await refreshPricesApi.triggerAsync(
        '/paper-trading/update-prices',
        { method: 'POST' },
        accountId ? { account_id: accountId } : {},
      );
      toast('持仓价格已刷新', 'success');
      setFormStatus(null);
      setLastActionResult('持仓价格已刷新');
    } catch (err) {
      setFormStatus(null);
      setFormError(err instanceof Error ? err.message : String(err));
    }
  }, [accountId, refreshPricesApi, toast]);

  useEffect(() => {
    if (typeof window === 'undefined') return;
    const tick = async () => {
      if (typeof document !== 'undefined' && document.visibilityState === 'hidden') return;
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
  }, []);

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

    const body: PaperTradingPlaceOrderInput = {
      code: trimmedCode,
      direction,
      quantity: qty,
      order_type: orderType,
    };
    if (orderType === 'limit' && price) body.price = parseFloat(price);
    if (orderType === 'stop' && stopPrice) body.stop_price = parseFloat(stopPrice);
    if (orderType === 'market' && price) body.price = parseFloat(price);
    if (accountId) body.account_id = accountId;

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

  function loadExampleOrder(nextCode = '600519') {
    setCode(nextCode);
    setDirection('buy');
    setQuantity('100');
    setOrderType('market');
    setPrice('');
    setStopPrice('');
    setFormError(null);
    setFormStatus(`已载入 ${nextCode} 的示例下单参数，可直接调整后提交。`);
  }

  const matchStatusLabel = matchOk ? '运行中' : showAccountBootstrap ? '待确认' : '待检查';
  const navStatusLabel = navOk ? '运行中' : showAccountBootstrap ? '待确认' : '待检查';

  useEffect(() => {
    if (!workbenchHydrated) return;
    const workspaceChanged = lastWorkspaceIdRef.current !== activeWorkspaceId;
    lastWorkspaceIdRef.current = activeWorkspaceId;
    if (!workspaceChanged) return;
    setCode(workbenchContext.stockCode ?? '600519');
    setAccountId(workbenchContext.accountId ?? '');
  }, [activeWorkspaceId, setCode, workbenchContext.accountId, workbenchContext.stockCode, workbenchHydrated]);

  useEffect(() => {
    if (!workbenchHydrated) return;
    updateWorkbenchContext({
      stockCode: trimmedCode || null,
      accountId: accountId || null,
      mode: 'account',
    });
  }, [accountId, trimmedCode, updateWorkbenchContext, workbenchHydrated]);

  usePageContext({
    pageKey: 'paper-trading',
    title: '模拟交易',
    summary: `账户 ${accountId || 'default'}，持仓 ${positions.length} 条，挂单 ${pending.length} 条，订单 ${trades.length} 条，总资产 ${fmtNum(totalValue, 2)}。`,
    stockCode: trimmedCode || undefined,
    tags: [
      `${positions.length} 条持仓`,
      `${pending.length} 条挂单`,
      `${trades.length} 条订单`,
      useComplianceCheck ? '合规检查开启' : '标准提交流程',
    ],
    suggestions: [
      trimmedCode ? `评估 ${trimmedCode} 当前下单参数是否合理` : '评估当前模拟盘状态',
      '总结账户表现、持仓和待处理订单',
      '把当前模拟盘整理成下一步操作清单',
    ],
    raw: {
      accountId: accountId || 'default',
      stockCode: trimmedCode || null,
      positionCount: positions.length,
      pendingCount: pending.length,
      orderCount: trades.length,
      totalValue,
      urgentExecution,
      useComplianceCheck,
    },
  });

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
          await Promise.allSettled([
            accountsQ.refetch(),
            summaryQ.refetch(),
            positionsQ.refetch(),
            ordersQ.refetch(),
            pendingQ.refetch(),
            navQ.refetch(),
            performanceQ.refetch(),
          ]);
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
    [accountsQ, handleRefreshPrices, navQ, ordersQ, pendingQ, performanceQ, positionsQ, summaryQ, useComplianceCheck],
  );

  usePageActions(pageActions);

  const currentView = useMemo<Record<string, unknown>>(
    () => ({
      code,
      direction,
      quantity,
      price,
      orderType,
      stopPrice,
      accountId,
      useComplianceCheck,
      urgentExecution,
      perfDays,
    }),
    [accountId, code, direction, orderType, perfDays, price, quantity, stopPrice, urgentExecution, useComplianceCheck],
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
      <PaperTradingHero
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
        accountId={accountId}
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
        onLoadExampleOrder={loadExampleOrder}
        onRefreshPrices={() => void handleRefreshPrices()}
        refreshPricesPending={refreshPricesApi.isPending}
      />

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
        accountId={accountId}
        previewUnitPrice={previewUnitPrice}
        estimatedAmount={estimatedAmount}
        riskHints={riskHints}
        formError={formError}
        formStatus={formStatus}
        lastActionResult={lastActionResult}
        onLoadExampleOrder={loadExampleOrder}
      />

      <PaperTradingAnalytics
        showAccountBootstrap={showAccountBootstrap}
        matchOk={matchOk}
        navOk={navOk}
        matchStatusLabel={matchStatusLabel}
        navStatusLabel={navStatusLabel}
        onRefreshPrices={() => void handleRefreshPrices()}
        refreshPricesPending={refreshPricesApi.isPending}
        accounts={accounts}
        accountId={accountId}
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
    <PaperTradingSummarySidebar
      accountId={accountId}
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
  );

  return (
    <PageContainer>
      <WorkspaceToolbar pageKey="paper-trading" currentView={currentView} onApplyView={applyView} supportsPagePanels />
      <WorkspaceSplitLayout pageKey="paper-trading" primary={primaryContent} secondary={secondaryContent} />
    </PageContainer>
  );
}
