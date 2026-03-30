'use client';

import { FormEvent, useMemo, useState, useCallback, useEffect, useRef } from 'react';
import { AskAiButton } from '@/components/ask-ai-button';
import WorkspaceSplitLayout from '@/components/workspace-split-layout';
import WorkspaceToolbar from '@/components/workspace-toolbar';
import { PageContainer, SectionCard, KpiCard, KpiGrid, StockCodeInput, DataTable, Badge } from '@/components/ui';
import { ConfirmDialog } from '@/components/ui/confirm-dialog';
import { useToast } from '@/components/ui/toast';
import { LineChart, PieChart } from '@/components/charts';
import { useApiQuery } from '@/hooks/use-api-query';
import { useApiMutation } from '@/hooks/use-api-mutation';
import { usePageActions } from '@/hooks/use-page-actions';
import { usePageContext } from '@/hooks/use-page-context';
import { apiKeys } from '@/lib/query-keys';
import { useStockCode } from '@/hooks/use-stock-code';
import { ErrorState } from '@/components/status-state';
import { extractArray, fmtNum, fmtPct } from '@/lib/data-utils';
import { useTradeSubscription } from '@/lib/ws';
import { isTradingHours } from '@/lib/trading-hours';
import { exportCSV } from '@/lib/export';
import { selectActiveWorkspace, useWorkbenchStore } from '@/store/workbench-store';
import type {
  PaperTradingAccountsResponse,
  PaperTradingAccount,
  PaperTradingCancelOrderInput,
  PaperTradingComplianceResult,
  PaperTradingNavHistoryResponse,
  PaperTradingOrdersResponse,
  PaperTradingPendingOrder,
  PaperTradingPendingOrdersResponse,
  PaperTradingPerformanceResponse,
  PaperTradingPlaceOrderInput,
  PaperTradingPosition,
  PaperTradingPositionsResponse,
  PaperTradingRouteExecutionInput,
  PaperTradingStatusProbe,
  PaperTradingSummary,
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

function resolveTradeConfirmations(profile: Record<string, unknown> | null) {
  const prefs = profile?.preferences;
  const root = prefs && typeof prefs === 'object' && !Array.isArray(prefs) ? (prefs as Record<string, unknown>) : {};
  const tx = root.transactionConfirmations;
  const confirmations = tx && typeof tx === 'object' && !Array.isArray(tx) ? (tx as Record<string, unknown>) : {};
  return {
    paperOrder: confirmations.paperOrder !== false,
    paperCancel: confirmations.paperCancel !== false,
  };
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
  const navData = useMemo(
    () => (navQ.data?.nav ?? []) as Array<{ nav_date?: string; total_value?: number; daily_return?: number }>,
    [navQ.data?.nav],
  );
  const performanceData = useMemo(() => performanceQ.data?.dailyReturns ?? [], [performanceQ.data?.dailyReturns]);
  const performanceMetrics = performanceQ.data?.metrics ?? {};
  const confirmPrefs = useMemo(() => resolveTradeConfirmations(profileQ.data), [profileQ.data]);
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

  const heroPrimaryButtonCls =
    'inline-flex cursor-pointer items-center justify-center rounded-full bg-primary px-4 py-2 text-sm font-medium text-white shadow-[0_20px_40px_-24px_rgba(11,107,203,0.52)] transition hover:-translate-y-0.5 hover:shadow-[0_24px_46px_-24px_rgba(11,107,203,0.58)] disabled:cursor-not-allowed disabled:opacity-50';
  const heroSecondaryButtonCls =
    'action-chip cursor-pointer text-sm text-text-primary shadow-[0_16px_32px_-24px_rgba(15,23,42,0.28)]';
  const chipButtonCls = 'action-chip cursor-pointer text-xs text-text-primary';
  const noteCardCls = 'metric-tile rounded-[22px] p-3 text-xs text-text-secondary';
  const sidePanelCls = 'panel-soft rounded-[28px] p-4 sm:p-5';

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
      <section className="page-hero p-5 sm:p-6">
        <div className="grid gap-5 xl:grid-cols-[minmax(0,1.2fr)_380px]">
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <Badge variant="info">Paper Trading Workspace</Badge>
              <Badge variant={showAccountBootstrap ? 'warning' : 'success'}>
                {showAccountBootstrap ? '待建立交易轨迹' : '已有账户轨迹'}
              </Badge>
              <Badge variant={matchOk ? 'success' : 'warning'}>撮合 {matchStatusLabel}</Badge>
              <Badge variant={navOk ? 'success' : 'warning'}>净值 {navStatusLabel}</Badge>
            </div>
            <h1 className="mb-0 mt-4 text-[2rem] font-semibold tracking-[-0.03em] text-text-primary sm:text-[2.4rem]">
              模拟交易工作台
            </h1>
            <p className="mb-0 mt-3 max-w-3xl text-sm leading-7 text-text-secondary sm:text-[15px]">
              这里把首笔交易引导、下单预览、账户状态和绩效观察收成一条连续的交易链路。先确定委托参数，再顺着撮合、持仓和净值去看交易结果，比在多个面板之间跳转更容易形成稳定节奏。
            </p>
            <div className="mt-5 flex flex-wrap gap-2">
              <button type="button" onClick={() => loadExampleOrder('600519')} className={heroPrimaryButtonCls}>
                载入茅台示例
              </button>
              <button type="button" onClick={() => loadExampleOrder('000001')} className={heroSecondaryButtonCls}>
                载入平安银行示例
              </button>
              <button
                type="button"
                onClick={() => void handleRefreshPrices()}
                disabled={refreshPricesApi.isPending}
                className={heroSecondaryButtonCls}
              >
                {refreshPricesApi.isPending ? '刷新中...' : '刷新价格'}
              </button>
            </div>

            <div className="mt-5 grid gap-3 sm:grid-cols-4">
              <div className="rounded-[24px] border border-white/45 bg-white/38 p-4 shadow-[inset_0_1px_0_rgba(255,255,255,0.55)]">
                <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">当前标的</div>
                <div className="mt-3 text-2xl font-semibold text-text-primary">{trimmedCode || '-'}</div>
                <div className="mt-1 text-xs text-text-secondary">
                  {directionLabel} · {orderTypeLabel}
                </div>
              </div>
              <div className="rounded-[24px] border border-white/45 bg-white/30 p-4 shadow-[inset_0_1px_0_rgba(255,255,255,0.48)]">
                <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">预估金额</div>
                <div className="mt-3 text-2xl font-semibold text-text-primary">
                  {estimatedAmount != null ? fmtNum(estimatedAmount) : '-'}
                </div>
                <div className="mt-1 text-xs text-text-secondary">
                  {previewUnitPrice != null && previewUnitPrice > 0
                    ? `预览单价 ${fmtNum(previewUnitPrice, 2)}`
                    : '待补充价格后生成'}
                </div>
              </div>
              <div className="rounded-[24px] border border-white/45 bg-white/26 p-4 shadow-[inset_0_1px_0_rgba(255,255,255,0.42)]">
                <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">账户状态</div>
                <div className="mt-3 text-2xl font-semibold text-text-primary">{accountId || '默认账户'}</div>
                <div className="mt-1 text-xs text-text-secondary">
                  持仓 / 挂单 / 成交 {positions.length} / {pending.length} / {trades.length}
                </div>
              </div>
              <div className="rounded-[24px] border border-white/45 bg-white/24 p-4 shadow-[inset_0_1px_0_rgba(255,255,255,0.38)]">
                <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">资产概览</div>
                <div className="mt-3 text-2xl font-semibold text-text-primary">{fmtNum(totalValue)}</div>
                <div className="mt-1 text-xs text-text-secondary">
                  今日盈亏 {fmtNum(todayPnl)} · 收益率 {fmtPct(Number(returnPct))}
                </div>
              </div>
            </div>
          </div>

          <div className="grid gap-3">
            <div className={sidePanelCls}>
              <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">当前聚焦</div>
              <div className="mt-3 text-base font-semibold text-text-primary">
                {showAccountBootstrap ? '先完成第一笔模拟委托' : '继续处理账户状态与委托结果'}
              </div>
              <div className="mt-4 space-y-3">
                <div className={noteCardCls}>
                  方向 / 数量：
                  <span className="font-medium text-text-primary">
                    {directionLabel} /{' '}
                    {Number.isFinite(quantityValue) && quantityValue > 0 ? `${quantityValue} 股` : '待填写'}
                  </span>
                </div>
                <div className={noteCardCls}>
                  风控流程：
                  <span className="font-medium text-text-primary">
                    {useComplianceCheck ? '先做合规检查' : '标准提交流程'}
                  </span>
                </div>
                <div className={noteCardCls}>
                  执行路径：
                  <span className="font-medium text-text-primary">
                    {urgentExecution ? '极速智能路由已开启' : '当前按普通模拟委托处理'}
                  </span>
                </div>
              </div>
              <div className="mt-4">
                <AskAiButton
                  stockCode={trimmedCode || undefined}
                  summary={`账户 ${accountId || 'default'}，持仓 ${positions.length} 条，挂单 ${pending.length} 条`}
                  prompt="请评估当前模拟盘状态，并给出下一步操作建议"
                />
              </div>
            </div>

            <div className={sidePanelCls}>
              <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">下一步动作</div>
              <div className="mt-4 space-y-3">
                {(tradeNotice ? [tradeNotice, ...riskHints] : riskHints).slice(0, 3).map((hint) => (
                  <div key={hint} className={noteCardCls}>
                    {hint}
                  </div>
                ))}
              </div>
              <div className="mt-3 flex flex-wrap gap-2">
                <button type="button" onClick={() => setUseComplianceCheck((prev) => !prev)} className={chipButtonCls}>
                  {useComplianceCheck ? '关闭合规检查' : '开启合规检查'}
                </button>
                <button type="button" onClick={() => setUrgentExecution((prev) => !prev)} className={chipButtonCls}>
                  {urgentExecution ? '关闭极速路由' : '开启极速路由'}
                </button>
              </div>
            </div>
          </div>
        </div>
      </section>

      {error ? <ErrorState text={error} /> : null}

      {tradeNotice ? (
        <div className="panel-soft mb-4 rounded-[24px] px-4 py-3 text-sm text-primary">{tradeNotice}</div>
      ) : null}

      {showAccountBootstrap ? (
        <SectionCard className="mb-4 p-4 sm:p-5">
          <div className="grid gap-4 lg:grid-cols-[minmax(0,1.35fr)_minmax(280px,0.85fr)]">
            <div>
              <div className="eyebrow">Bootstrap Flow</div>
              <h2 className="mt-2 mb-0 text-xl font-semibold text-text-primary">账户尚未开始交易</h2>
              <p className="mb-0 mt-3 text-sm leading-7 text-text-secondary">
                当前还没有持仓、挂单、成交和净值轨迹。最顺手的进入方式不是先看报表，而是直接载入一笔示例委托，完成首笔交易后再回来观察账户变化。
              </p>
              <div className="mt-4 flex flex-wrap gap-2">
                <button type="button" onClick={() => loadExampleOrder('600519')} className={heroSecondaryButtonCls}>
                  载入贵州茅台示例
                </button>
                <button type="button" onClick={() => loadExampleOrder('000001')} className={heroSecondaryButtonCls}>
                  载入平安银行示例
                </button>
                <button type="button" onClick={() => void handleRefreshPrices()} className={chipButtonCls}>
                  先刷新价格
                </button>
              </div>
            </div>
            <div className="panel-soft rounded-[24px] p-4">
              <div className="text-sm font-medium text-text-primary">推荐流程</div>
              <div className="mt-3 space-y-3">
                <div className={noteCardCls}>1. 先载入示例代码，优先用 100 股市价单完成首笔交易。</div>
                <div className={noteCardCls}>2. 如需价格参考，可先手动刷新一次行情再提交。</div>
                <div className={noteCardCls}>3. 成交后再回来看持仓、净值和绩效变化。</div>
              </div>
            </div>
          </div>
        </SectionCard>
      ) : null}

      <SectionCard className="mb-4 p-4 sm:p-5">
        <div className="grid gap-4 2xl:grid-cols-[minmax(0,1.15fr)_minmax(320px,0.85fr)] 2xl:items-start">
          <div>
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <div className="eyebrow">Order Workspace</div>
                <h3 className="mt-2 mb-0 text-xl font-semibold text-text-primary">委托输入与提交流程</h3>
                <p className="mb-0 mt-2 text-sm leading-7 text-text-secondary">
                  把参数输入、风控开关和示例引导放在同一块 glass 表单里，提交前就能确认方向、账户、价格和执行路径。
                </p>
              </div>
              {showAccountBootstrap ? (
                <div className="panel-soft rounded-[20px] px-3 py-2 text-xs text-text-secondary">
                  首笔交易建议使用示例代码和 100 股市价单
                </div>
              ) : null}
            </div>

            <form onSubmit={handleOrder} className="mt-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
              <StockCodeInput
                id="paper-order-code"
                label="股票代码"
                value={code}
                onChange={setCode}
                error={codeError}
              />
              <label className="flex flex-col gap-2 text-xs text-text-secondary">
                <span>交易方向</span>
                <select
                  id="paper-order-direction"
                  value={direction}
                  onChange={(event) => setDirection(event.target.value as 'buy' | 'sell')}
                  className="text-sm"
                >
                  <option value="buy">买入</option>
                  <option value="sell">卖出</option>
                </select>
              </label>
              <label className="flex flex-col gap-2 text-xs text-text-secondary">
                <span>数量</span>
                <input
                  id="paper-order-quantity"
                  type="number"
                  min={1}
                  value={quantity}
                  onChange={(event) => setQuantity(event.target.value)}
                  placeholder="数量"
                  className="text-sm"
                />
              </label>
              <label className="flex flex-col gap-2 text-xs text-text-secondary">
                <span>订单类型</span>
                <select
                  id="paper-order-type"
                  value={orderType}
                  onChange={(event) => setOrderType(event.target.value as 'market' | 'limit' | 'stop')}
                  className="text-sm"
                >
                  <option value="market">市价单</option>
                  <option value="limit">限价单</option>
                  <option value="stop">止损单</option>
                </select>
              </label>

              {orderType === 'limit' || orderType === 'market' ? (
                <label className="flex flex-col gap-2 text-xs text-text-secondary">
                  <span>价格</span>
                  <input
                    id="paper-order-price"
                    type="number"
                    step="0.01"
                    value={price}
                    onChange={(event) => setPrice(event.target.value)}
                    placeholder={orderType === 'market' ? '价格（可选）' : '输入限价'}
                    className="text-sm"
                  />
                </label>
              ) : null}
              {orderType === 'stop' ? (
                <label className="flex flex-col gap-2 text-xs text-text-secondary">
                  <span>止损价</span>
                  <input
                    id="paper-order-stop-price"
                    type="number"
                    step="0.01"
                    value={stopPrice}
                    onChange={(event) => setStopPrice(event.target.value)}
                    placeholder="输入止损价"
                    className="text-sm"
                  />
                </label>
              ) : null}

              <div className="sm:col-span-2 xl:col-span-4 grid gap-3 md:grid-cols-2">
                <label
                  htmlFor="paper-order-compliance-check"
                  className="panel-soft flex cursor-pointer items-start gap-3 rounded-[22px] p-3 text-sm text-text-secondary"
                >
                  <input
                    id="paper-order-compliance-check"
                    type="checkbox"
                    checked={useComplianceCheck}
                    onChange={(event) => setUseComplianceCheck(event.target.checked)}
                    className="mt-0.5 rounded border-border accent-primary"
                  />
                  <span>
                    下单前执行合规风控。
                    <span className="mt-1 block text-xs text-text-muted">
                      先检查规则再决定是否继续提交，更适合有账户约束的模拟流程。
                    </span>
                  </span>
                </label>
                <label
                  htmlFor="paper-order-urgent-execution"
                  className="panel-soft flex cursor-pointer items-start gap-3 rounded-[22px] p-3 text-sm text-text-secondary"
                >
                  <input
                    id="paper-order-urgent-execution"
                    type="checkbox"
                    checked={urgentExecution}
                    onChange={(event) => setUrgentExecution(event.target.checked)}
                    className="mt-0.5 rounded border-border accent-primary"
                  />
                  <span>
                    启用极速智能路由。
                    <span className="mt-1 block text-xs text-text-muted">
                      由 Execution Manager 优先决定提交路径，更适合需要更快模拟反馈的场景。
                    </span>
                  </span>
                </label>
              </div>

              <div className="sm:col-span-2 xl:col-span-4 flex flex-wrap items-center gap-2">
                <button
                  type="submit"
                  disabled={placeApi.isPending || routeExecutionApi.isPending || complianceApi.isPending}
                  className={`inline-flex min-h-[42px] cursor-pointer items-center justify-center rounded-full px-5 py-2 text-sm font-medium text-white shadow-[0_18px_38px_-24px_rgba(15,23,42,0.4)] transition hover:-translate-y-0.5 disabled:cursor-not-allowed disabled:opacity-50 ${direction === 'buy' ? 'bg-danger' : 'bg-success'}`}
                >
                  {placeApi.isPending || routeExecutionApi.isPending
                    ? '提交中...'
                    : complianceApi.isPending
                      ? '风控检查中...'
                      : direction === 'buy'
                        ? '确认买入'
                        : '确认卖出'}
                </button>
                <button type="button" onClick={() => loadExampleOrder('600519')} className={chipButtonCls}>
                  载入茅台示例
                </button>
                <button type="button" onClick={() => loadExampleOrder('000001')} className={chipButtonCls}>
                  载入平安银行示例
                </button>
              </div>
            </form>
          </div>

          <div className="panel-soft rounded-[26px] p-4 sm:p-5">
            <div className="flex items-start justify-between gap-3">
              <div>
                <div className="text-sm font-medium text-text-primary">订单预览</div>
                <p className="mb-0 mt-2 text-xs leading-6 text-text-secondary">
                  在确认弹窗前先核对方向、数量、价格、账户与执行路径，移动端也能直接抓到关键信息。
                </p>
              </div>
              <Badge variant={direction === 'buy' ? 'danger' : 'success'}>{directionLabel}</Badge>
            </div>
            <div className="mt-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-1">
              <div className="metric-tile rounded-[24px] p-4">
                <div className="metric-label">标的 / 类型</div>
                <div className="metric-value mt-3 text-[1.45rem]">{trimmedCode || '待填写代码'}</div>
                <div className="mt-1 text-xs text-text-secondary">{orderTypeLabel}</div>
              </div>
              <div className="metric-tile rounded-[24px] p-4">
                <div className="metric-label">数量 / 账户</div>
                <div className="metric-value mt-3 text-[1.45rem]">
                  {Number.isFinite(quantityValue) && quantityValue > 0 ? `${quantityValue} 股` : '待填写数量'}
                </div>
                <div className="mt-1 text-xs text-text-secondary">{accountId || '默认账户'}</div>
              </div>
              <div className="metric-tile rounded-[24px] p-4">
                <div className="metric-label">预览价格</div>
                <div className="metric-value mt-3 text-[1.45rem]">
                  {previewUnitPrice != null && Number.isFinite(previewUnitPrice) && previewUnitPrice > 0
                    ? fmtNum(previewUnitPrice, 2)
                    : '-'}
                </div>
                <div className="mt-1 text-xs text-text-secondary">
                  {orderType === 'market' ? '市价单可不填写价格' : '需要有效价格才能形成完整预览'}
                </div>
              </div>
              <div className="metric-tile rounded-[24px] p-4">
                <div className="metric-label">预估金额</div>
                <div className="metric-value mt-3 text-[1.45rem]">
                  {estimatedAmount != null ? fmtNum(estimatedAmount) : '-'}
                </div>
                <div className="mt-1 text-xs text-text-secondary">
                  {urgentExecution ? '当前会优先走极速智能路由' : '当前按标准模拟提交流程处理'}
                </div>
              </div>
            </div>

            <div className="mt-4 rounded-[22px] border border-white/45 bg-white/36 p-4 shadow-[inset_0_1px_0_rgba(255,255,255,0.52)]">
              <div className="text-xs font-medium uppercase tracking-[0.16em] text-text-muted">提交前提醒</div>
              <div className="mt-3 space-y-2">
                {riskHints.map((hint) => (
                  <div key={hint} className="text-xs leading-6 text-text-secondary">
                    {hint}
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>

        {formError ? (
          <div className="panel-soft mt-4 rounded-[20px] px-4 py-3 text-xs font-medium text-danger" role="alert">
            {formError}
          </div>
        ) : null}
        {formStatus ? (
          <div className="panel-soft mt-3 rounded-[20px] px-4 py-3 text-xs text-primary" role="status">
            {formStatus}
          </div>
        ) : null}
        {lastActionResult ? (
          <div className="panel-soft mt-3 rounded-[20px] px-4 py-3 text-xs text-success">{lastActionResult}</div>
        ) : null}
      </SectionCard>

      <SectionCard className="mb-4 p-4 sm:p-5">
        <div className="grid gap-4 2xl:grid-cols-[minmax(0,1.12fr)_minmax(320px,0.88fr)]">
          <div>
            <div className="eyebrow">System Status</div>
            <h3 className="mt-2 mb-0 text-xl font-semibold text-text-primary">撮合、净值与账户上下文</h3>
            <p className="mb-0 mt-2 text-sm leading-7 text-text-secondary">
              交易时段内会自动刷新价格，非交易时段建议手动刷新后再核对持仓与收益。先确保账户和状态正常，再进入绩效复盘更稳妥。
            </p>
            <div className="toolbar-strip mt-4">
              <Badge variant={matchOk ? 'success' : 'warning'}>撮合 {matchStatusLabel}</Badge>
              <Badge variant={navOk ? 'success' : 'warning'}>净值 {navStatusLabel}</Badge>
              <button
                type="button"
                onClick={handleRefreshPrices}
                disabled={refreshPricesApi.isPending}
                className={chipButtonCls}
              >
                {refreshPricesApi.isPending ? '刷新中...' : '刷新价格'}
              </button>
              {accounts.length > 1 ? (
                <label className="flex min-w-[156px] flex-col gap-2 text-xs text-text-secondary">
                  <span>交易账户</span>
                  <select
                    id="paper-account-select"
                    value={accountId}
                    onChange={(event) => setAccountId(event.target.value)}
                    className="text-sm"
                  >
                    <option value="">默认账户</option>
                    {accounts.map((account, index) => (
                      <option key={account.account_id ?? index} value={account.account_id ?? ''}>
                        {account.account_id ?? `账户 ${index + 1}`}
                      </option>
                    ))}
                  </select>
                </label>
              ) : null}
              <div className="text-xs text-text-secondary">交易时段内每 15 秒自动刷新价格。</div>
              <div className="text-xs text-warning">非交易时段的市价单与盈亏估算可能使用延迟行情。</div>
            </div>
          </div>

          <div className="panel-soft rounded-[24px] p-4">
            <div className="text-sm font-medium text-text-primary">
              {showAccountBootstrap ? '首笔交易提示' : '状态说明'}
            </div>
            <div className="mt-3 space-y-3">
              {statusNotes.length > 0 ? (
                statusNotes.map((note) => (
                  <div key={note} className={noteCardCls}>
                    {note}
                  </div>
                ))
              ) : (
                <>
                  <div className={noteCardCls}>当前撮合与净值状态已可用，可以直接继续维护持仓与观察绩效。</div>
                  <div className={noteCardCls}>如遇价格偏差，优先手动刷新一次持仓价格，再核对当日盈亏与净值变化。</div>
                </>
              )}
            </div>
          </div>
        </div>
      </SectionCard>

      <KpiGrid cols={5} className="mb-4">
        <KpiCard title="总资产" value={fmtNum(totalValue)} />
        <KpiCard title="可用资金" value={fmtNum(cash)} />
        <KpiCard title="持仓市值" value={fmtNum(marketValue)} />
        <KpiCard title="总收益率" value={fmtPct(Number(returnPct))} change={Number(returnPct)} />
        <KpiCard title="今日盈亏" value={fmtNum(todayPnl)} change={todayPnl} />
      </KpiGrid>

      {!showAccountBootstrap ? (
        <SectionCard className="mb-4 p-4 sm:p-5">
          <div className="grid gap-4 2xl:grid-cols-[minmax(0,1.1fr)_minmax(300px,0.9fr)]">
            <div>
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <h3 className="m-0 font-medium">绩效分析</h3>
                  <p className="mb-0 mt-2 text-sm text-text-secondary">
                    这里聚焦模拟盘收益质量，先看窗口收益、回撤和胜率，再决定是否继续追到具体委托和个股。
                  </p>
                </div>
                <div className="flex flex-wrap gap-2">
                  {[7, 30, 90, 0].map((days) => (
                    <button
                      key={days}
                      type="button"
                      onClick={() => setPerfDays(days)}
                      className={`action-chip cursor-pointer text-xs ${perfDays === days ? 'border-primary/35 bg-primary/12 text-primary' : 'text-text-secondary'}`}
                    >
                      {days === 0 ? '全部' : `${days} 天`}
                    </button>
                  ))}
                  <button
                    type="button"
                    onClick={() =>
                      exportCSV(
                        performanceData.map((item) => ({
                          日期: item.date ?? '',
                          净值: item.totalValue ?? 0,
                          日收益率: item.dailyReturn ?? 0,
                        })),
                        `paper-trading-performance-${perfDays || 'all'}.csv`,
                      )
                    }
                    className={chipButtonCls}
                  >
                    导出 CSV
                  </button>
                </div>
              </div>
              <KpiGrid cols={5} className="mt-4">
                <KpiCard
                  title="区间收益率"
                  value={fmtPct(Number(performanceMetrics.totalReturn ?? 0) * 100)}
                  change={Number(performanceMetrics.totalReturn ?? 0) * 100}
                />
                <KpiCard title="夏普比率" value={fmtNum(Number(performanceMetrics.sharpe ?? 0))} />
                <KpiCard
                  title="最大回撤"
                  value={fmtPct(Number(performanceMetrics.maxDrawdown ?? 0) * 100)}
                  change={Number(performanceMetrics.maxDrawdown ?? 0) * 100}
                />
                <KpiCard
                  title="胜率"
                  value={fmtPct(Number(performanceMetrics.winRate ?? 0) * 100)}
                  change={Number(performanceMetrics.winRate ?? 0) * 100}
                />
                <KpiCard title="平均持仓天数" value={fmtNum(Number(performanceMetrics.avgHoldDays ?? 0))} />
              </KpiGrid>
            </div>

            <div className="panel-soft rounded-[24px] p-4">
              <div className="text-sm font-medium text-text-primary">绩效阅读顺序</div>
              <div className="mt-3 space-y-3">
                <div className={noteCardCls}>先确认区间收益率是否覆盖了成本与风险暴露。</div>
                <div className={noteCardCls}>再看最大回撤与胜率，判断当前交易节奏是否稳定。</div>
                <div className={noteCardCls}>最后结合持仓和成交列表，定位收益来自哪里、拖累来自哪里。</div>
              </div>
            </div>
          </div>

          <div className="mt-4">
            {performanceData.length > 1 ? (
              <LineChart categories={perfCategories} series={[{ name: '日收益率(%)', data: perfReturns }]} />
            ) : (
              <div className="panel-soft rounded-[22px] px-4 py-3 text-sm text-text-secondary">暂无足够绩效数据</div>
            )}
          </div>
        </SectionCard>
      ) : null}

      <SectionCard className="mb-4 p-4 sm:p-5">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h3 className="m-0 font-medium">持仓 ({positions.length})</h3>
            <p className="mb-0 mt-2 text-sm text-text-secondary">
              持仓区保留快速卖出入口，方便从复盘直接回到下一步交易动作。
            </p>
          </div>
        </div>
        {positions.length > 0 ? (
          <DataTable
            columns={[
              { key: 'stock_code', label: '代码' },
              { key: 'stock_name', label: '名称' },
              { key: 'quantity', label: '数量' },
              { key: 'sellable', label: '可卖' },
              { key: 'cost_price', label: '成本', render: (value: unknown) => fmtNum(Number(value), 2) },
              { key: 'current_price', label: '现价', render: (value: unknown) => fmtNum(Number(value), 2) },
              { key: 'market_value', label: '市值', render: (value: unknown) => fmtNum(Number(value)) },
              {
                key: 'profit_rate',
                label: '盈亏率',
                render: (value: unknown) => {
                  const amount = Number(value) * 100;
                  return (
                    <span className={amount >= 0 ? 'text-danger font-medium' : 'text-success font-medium'}>
                      {fmtPct(amount)}
                    </span>
                  );
                },
              },
              {
                key: 'action',
                label: '操作',
                render: (_value: unknown, row: Record<string, unknown>) => (
                  <button
                    type="button"
                    onClick={() => quickSell(row as PaperTradingPosition)}
                    className="action-chip cursor-pointer text-[11px] text-primary"
                  >
                    快速卖出
                  </button>
                ),
              },
            ]}
            rows={positions as Record<string, unknown>[]}
            mobileCardRender={(row) => {
              const profitRate = Number(row.profit_rate ?? 0) * 100;
              return (
                <div className="space-y-2">
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <div className="text-sm font-medium text-text-primary">
                        {String(row.stock_name ?? row.stock_code ?? '-')}
                      </div>
                      <div className="text-xs text-text-secondary">代码：{String(row.stock_code ?? '-')}</div>
                    </div>
                    <div className={`text-xs font-medium ${profitRate >= 0 ? 'text-danger' : 'text-success'}`}>
                      {fmtPct(profitRate)}
                    </div>
                  </div>
                  <div className="grid grid-cols-2 gap-2 text-xs text-text-secondary">
                    <div>数量：{String(row.quantity ?? '-')}</div>
                    <div>可卖：{String(row.sellable ?? '-')}</div>
                    <div>成本：{fmtNum(Number(row.cost_price ?? 0), 2)}</div>
                    <div>现价：{fmtNum(Number(row.current_price ?? 0), 2)}</div>
                    <div className="col-span-2">市值：{fmtNum(Number(row.market_value ?? 0))}</div>
                  </div>
                  <button
                    type="button"
                    onClick={() => quickSell(row as PaperTradingPosition)}
                    className="action-chip cursor-pointer text-[11px] text-primary"
                  >
                    快速卖出
                  </button>
                </div>
              );
            }}
          />
        ) : (
          <div className="panel-soft mt-4 rounded-[22px] px-4 py-3 text-sm text-text-secondary">
            {showAccountBootstrap ? '完成首笔下单后，这里会显示持仓摘要和快速卖出入口。' : '暂无持仓'}
          </div>
        )}
      </SectionCard>

      {positions.length > 0 ? (
        <SectionCard className="mb-4 p-4 sm:p-5">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <h3 className="m-0 font-medium">持仓分布</h3>
              <p className="mb-0 mt-2 text-sm text-text-secondary">
                用更柔和的图表容器观察资金集中度，快速判断账户是否过度押注单一标的。
              </p>
            </div>
          </div>
          <div className="mt-4">
            <PieChart
              data={positions.map((position) => ({
                name: position.stock_name || position.stock_code || '未知',
                value: Number(position.market_value ?? 0),
              }))}
              donut
              height={260}
            />
          </div>
        </SectionCard>
      ) : null}

      {pending.length > 0 ? (
        <SectionCard className="mb-4 p-4 sm:p-5">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <h3 className="m-0 font-medium">挂单 ({pending.length})</h3>
              <p className="mb-0 mt-2 text-sm text-text-secondary">
                挂单区保留撤单入口，方便在发现风控或价格偏差时直接修正。
              </p>
            </div>
          </div>
          <div className="mt-4">
            <DataTable
              columns={[
                { key: 'code', label: '代码' },
                { key: 'direction', label: '方向' },
                { key: 'shares', label: '数量' },
                { key: 'order_type', label: '类型' },
                { key: 'price', label: '价格', render: (value: unknown) => (value ? fmtNum(Number(value), 2) : '-') },
                {
                  key: 'stop_price',
                  label: '止损价',
                  render: (value: unknown) => (value ? fmtNum(Number(value), 2) : '-'),
                },
                {
                  key: 'id',
                  label: '操作',
                  render: (_value: unknown, row: Record<string, unknown>) => (
                    <button
                      type="button"
                      onClick={() => handleCancel(Number(row.id))}
                      disabled={cancelingOrderIds.includes(Number(row.id))}
                      className="action-chip cursor-pointer text-[11px] text-danger disabled:cursor-not-allowed disabled:opacity-50"
                    >
                      {cancelingOrderIds.includes(Number(row.id)) ? '撤单中...' : '撤单'}
                    </button>
                  ),
                },
              ]}
              rows={pending as Record<string, unknown>[]}
              mobileCardRender={(row) => {
                const orderId = Number(row.id ?? 0);
                const isCanceling = cancelingOrderIds.includes(orderId);
                return (
                  <div className="space-y-2">
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <div className="text-sm font-medium text-text-primary">
                          {String(row.code ?? '-')} · {String(row.direction ?? '-')}
                        </div>
                        <div className="text-xs text-text-secondary">
                          {String(row.order_type ?? '-')} / {String(row.shares ?? '-')} 股
                        </div>
                      </div>
                      <div className="text-xs text-text-secondary">#{orderId || '-'}</div>
                    </div>
                    <div className="grid grid-cols-2 gap-2 text-xs text-text-secondary">
                      <div>价格：{row.price ? fmtNum(Number(row.price), 2) : '-'}</div>
                      <div>止损价：{row.stop_price ? fmtNum(Number(row.stop_price), 2) : '-'}</div>
                    </div>
                    <button
                      type="button"
                      onClick={() => handleCancel(orderId)}
                      disabled={isCanceling}
                      className="action-chip cursor-pointer text-[11px] text-danger disabled:cursor-not-allowed disabled:opacity-50"
                    >
                      {isCanceling ? '撤单中...' : '撤单'}
                    </button>
                  </div>
                );
              }}
            />
          </div>
        </SectionCard>
      ) : null}

      {!showAccountBootstrap ? (
        <>
          <SectionCard className="mb-4 p-4 sm:p-5">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <h3 className="m-0 font-medium">成交记录</h3>
                <p className="mb-0 mt-2 text-sm text-text-secondary">
                  把成交时间、方向、金额和佣金保留在同一块，方便回溯一次委托的真实落地结果。
                </p>
              </div>
            </div>
            {trades.length > 0 ? (
              <div className="mt-4">
                <DataTable
                  columns={[
                    { key: 'trade_time', label: '时间', render: (value: unknown) => String(value ?? '').slice(0, 16) },
                    { key: 'stock_code', label: '代码' },
                    { key: 'trade_type', label: '方向' },
                    { key: 'quantity', label: '数量' },
                    { key: 'price', label: '价格', render: (value: unknown) => fmtNum(Number(value), 2) },
                    { key: 'amount', label: '金额', render: (value: unknown) => fmtNum(Number(value)) },
                    { key: 'commission', label: '佣金', render: (value: unknown) => fmtNum(Number(value), 4) },
                  ]}
                  rows={trades as Record<string, unknown>[]}
                  mobileCardRender={(row) => (
                    <div className="space-y-2">
                      <div className="flex items-start justify-between gap-3">
                        <div>
                          <div className="text-sm font-medium text-text-primary">
                            {String(row.stock_code ?? '-')} · {String(row.trade_type ?? '-')}
                          </div>
                          <div className="text-xs text-text-secondary">
                            时间：{String(row.trade_time ?? '').slice(0, 16) || '-'}
                          </div>
                        </div>
                        <div className="text-xs text-text-secondary">{String(row.quantity ?? '-')} 股</div>
                      </div>
                      <div className="grid grid-cols-2 gap-2 text-xs text-text-secondary">
                        <div>价格：{fmtNum(Number(row.price ?? 0), 2)}</div>
                        <div>金额：{fmtNum(Number(row.amount ?? 0))}</div>
                        <div className="col-span-2">佣金：{fmtNum(Number(row.commission ?? 0), 4)}</div>
                      </div>
                    </div>
                  )}
                />
              </div>
            ) : (
              <div className="panel-soft mt-4 rounded-[22px] px-4 py-3 text-sm text-text-secondary">暂无成交</div>
            )}
          </SectionCard>

          {navData.length > 1 ? (
            <SectionCard className="p-4 sm:p-5">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <h3 className="m-0 font-medium">账户净值走势</h3>
                  <p className="mb-0 mt-2 text-sm text-text-secondary">
                    净值曲线用于确认模拟交易是否真的沉淀成稳定账户表现，而不只是零散的单笔结果。
                  </p>
                </div>
              </div>
              <div className="mt-4">
                <LineChart categories={navCategories} series={[{ name: '净值', data: navValues }]} />
              </div>
            </SectionCard>
          ) : null}
        </>
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
    <SectionCard className="p-4 sm:p-5">
      <div className="eyebrow">Paper Summary</div>
      <h3 className="mt-2 mb-0 text-lg font-semibold text-text-primary">模拟盘工作区摘要</h3>
      <div className="mt-4 grid gap-3">
        <div className="metric-tile rounded-[24px] p-4">
          <div className="metric-label">账户与委托</div>
          <div className="metric-value mt-3 text-[1.45rem]">{accountId || '默认账户'}</div>
          <div className="mt-2 text-xs text-text-secondary">
            {trimmedCode || '未填写标的'} · {directionLabel} / {orderTypeLabel}
          </div>
          <div className="mt-1 text-xs text-text-secondary">
            预估金额 {estimatedAmount != null ? fmtNum(estimatedAmount) : '待补价格'}
          </div>
        </div>
        <div className="metric-tile rounded-[24px] p-4">
          <div className="metric-label">账户轨迹</div>
          <div className="metric-value mt-3 text-[1.45rem]">
            {positions.length} / {pending.length} / {trades.length}
          </div>
          <div className="mt-2 text-xs text-text-secondary">持仓 / 挂单 / 成交</div>
          <div className="mt-1 text-xs text-text-secondary">
            撮合 {matchStatusLabel} · 净值 {navStatusLabel}
          </div>
        </div>
        <div className="metric-tile rounded-[24px] p-4">
          <div className="metric-label">绩效与模式</div>
          <div className="metric-value mt-3 text-[1.45rem]">{fmtNum(totalValue)}</div>
          <div className="mt-2 text-xs text-text-secondary">
            绩效窗口 {perfDays} 天 · 今日盈亏 {fmtNum(todayPnl)}
          </div>
          <div className="mt-1 text-xs text-text-secondary">
            {useComplianceCheck ? '已开启合规检查' : '标准提交流程'} ·{' '}
            {urgentExecution ? '极速路由已开启' : '普通委托路径'}
          </div>
        </div>
        <div className="panel-soft rounded-[24px] p-4 text-xs text-text-secondary">
          保存视图后，可把账户、下单参数和风控开关固定成一套模拟盘操作面板，在不同工作区之间快速复用。
        </div>
      </div>
    </SectionCard>
  );

  return (
    <PageContainer>
      <WorkspaceToolbar pageKey="paper-trading" currentView={currentView} onApplyView={applyView} supportsPagePanels />
      <WorkspaceSplitLayout pageKey="paper-trading" primary={primaryContent} secondary={secondaryContent} />
    </PageContainer>
  );
}
