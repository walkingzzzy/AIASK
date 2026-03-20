'use client';

import { FormEvent, useMemo, useState, useCallback, useEffect, useRef } from 'react';
import { PageContainer, SectionCard, KpiCard, KpiGrid, StockCodeInput, DataTable, Badge } from '@/components/ui';
import { ConfirmDialog } from '@/components/ui/confirm-dialog';
import { useToast } from '@/components/ui/toast';
import { LineChart, PieChart } from '@/components/charts';
import { useApiQuery } from '@/hooks/use-api-query';
import { useApiMutation } from '@/hooks/use-api-mutation';
import { apiKeys } from '@/lib/query-keys';
import { useStockCode } from '@/hooks/use-stock-code';
import { ErrorState } from '@/components/status-state';
import { extractArray, fmtNum, fmtPct } from '@/lib/data-utils';
import { useTradeSubscription } from '@/lib/ws';
import { isTradingHours } from '@/lib/trading-hours';
import { exportCSV } from '@/lib/export';
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
  const root = prefs && typeof prefs === 'object' && !Array.isArray(prefs) ? prefs as Record<string, unknown> : {};
  const tx = root.transactionConfirmations;
  const confirmations = tx && typeof tx === 'object' && !Array.isArray(tx) ? tx as Record<string, unknown> : {};
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
    setTradeNotice(`订单 ${code} ${status === 'filled' ? '已成交' : status === 'partial' ? '部分成交' : status === 'rejected' ? '被拒绝' : '状态更新'}`);
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
  const performanceQ = useApiQuery<PaperTradingPerformanceResponse>(`/paper-trading/performance${qs ? `${qs}&days=${perfDays}` : `?days=${perfDays}`}`);

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

  const accounts = useMemo(() => extractArray(accountsQ.data, 'accounts', 'items', 'data') as PaperTradingAccount[], [accountsQ.data]);
  const matchStatus = useMemo(() => matchStatusQ.data ?? {}, [matchStatusQ.data]);
  const navStatus = useMemo(() => navStatusQ.data ?? {}, [navStatusQ.data]);
  const matchOk = matchStatus.status === 'running' || matchStatus.running === true || matchStatus.ok === true;
  const navOk = navStatus.status === 'running' || navStatus.running === true || navStatus.ok === true;

  const acct = summaryQ.data?.account ?? undefined;
  const totalValue = Number(summaryQ.data?.total_value ?? acct?.total_value ?? 0);
  const cash = Number(acct?.current_capital ?? 0);
  const initial = Number(acct?.initial_capital ?? 100000);
  const marketValue = totalValue - cash;
  const returnPct = summaryQ.data?.total_return_pct ?? (initial > 0 ? (totalValue - initial) / initial * 100 : 0);

  const positions = positionsQ.data?.positions ?? [];
  const trades = ordersQ.data?.orders ?? [];
  const pending = pendingQ.data?.orders ?? [];
  const navData = useMemo(
    () => (navQ.data?.nav ?? []) as Array<{ nav_date?: string; total_value?: number; daily_return?: number }>,
    [navQ.data?.nav],
  );
  const performanceData = useMemo(
    () => performanceQ.data?.dailyReturns ?? [],
    [performanceQ.data?.dailyReturns],
  );
  const performanceMetrics = performanceQ.data?.metrics ?? {};
  const confirmPrefs = useMemo(() => resolveTradeConfirmations(profileQ.data), [profileQ.data]);
  const showAccountBootstrap = positions.length === 0 && pending.length === 0 && trades.length === 0 && navData.length === 0;
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
    if (orderType === 'limit' && (limitPriceValue == null || !Number.isFinite(limitPriceValue) || limitPriceValue <= 0)) {
      hints.push('限价单需填写有效价格，预览金额才会完整显示。');
    }
    if (orderType === 'stop' && (stopPriceValue == null || !Number.isFinite(stopPriceValue) || stopPriceValue <= 0)) {
      hints.push('止损单需填写止损价，系统会先按止损触发价进行预览。');
    }
    if (useComplianceCheck) hints.push('已开启下单前合规风控，提交时会先做额外检查。');
    if (urgentExecution) hints.push('已开启极速智能路由，提交成功文案会与普通委托不同。');
    if (!useComplianceCheck && !urgentExecution) hints.push('当前为标准提交流程：直接确认并提交委托。');
    return hints;
  }, [direction, limitPriceValue, orderType, quantityValue, stopPriceValue, trimmedCode, urgentExecution, useComplianceCheck]);

  // 今日盈亏：最新 NAV 的 daily_return * 前一日总资产
  const todayPnl = useMemo(() => {
    if (navData.length === 0) return 0;
    const latest = navData[navData.length - 1];
    const dr = Number(latest.daily_return ?? 0);
    const prevVal = navData.length >= 2 ? Number(navData[navData.length - 2].total_value ?? totalValue) : initial;
    return dr * prevVal;
  }, [navData, totalValue, initial]);

  const navCategories = useMemo(() => navData.map(n => n.nav_date?.slice(5) ?? ''), [navData]);
  const navValues = useMemo(() => navData.map(n => n.total_value ?? 0), [navData]);
  const perfCategories = useMemo(() => performanceData.map((item) => item.date?.slice(5) ?? ''), [performanceData]);
  const perfReturns = useMemo(() => performanceData.map((item) => Number(item.dailyReturn ?? 0) * 100), [performanceData]);

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

  async function handleRefreshPrices() {
    setFormError(null);
    setFormStatus('正在刷新持仓价格...');
    setLastActionResult(null);
    try {
      await refreshPricesApi.triggerAsync('/paper-trading/update-prices', { method: 'POST' }, accountId ? { account_id: accountId } : {});
      toast('持仓价格已刷新', 'success');
      setFormStatus(null);
      setLastActionResult('持仓价格已刷新');
    } catch (err) {
      setFormStatus(null);
      setFormError(err instanceof Error ? err.message : String(err));
    }
  }

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
    if (!qty || qty <= 0) { setFormError('数量必须大于0'); return; }
    if (direction === 'buy' && qty % 100 !== 0) { setFormError('买入数量必须为100的整数倍（手数规则）'); return; }
    if (orderType === 'limit' && (!price || parseFloat(price) <= 0)) { setFormError('限价单必须填写有效价格'); return; }
    if (orderType === 'stop' && (!stopPrice || parseFloat(stopPrice) <= 0)) { setFormError('止损单必须填写止损价'); return; }
    if (price && parseFloat(price) <= 0) { setFormError('价格必须大于0'); return; }

    const body: PaperTradingPlaceOrderInput = {
      code: trimmedCode, direction, quantity: qty, order_type: orderType,
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

  return (
    <PageContainer>
      <div className="mb-3">
        <h1 className="text-lg font-semibold m-0">模拟交易</h1>
        <p className="mt-1 mb-0 text-xs text-text-secondary">先完成一笔示例委托或真实模拟单，再继续看账户状态、持仓和绩效更顺手。</p>
      </div>

      {error && <ErrorState text={error} />}

      {/* WS 交易通知 */}
      {tradeNotice && (
        <div className="mb-3 px-4 py-2 rounded-lg bg-primary/10 border border-primary/30 text-sm text-primary flex items-center gap-2">
          <span>📋</span> {tradeNotice}
        </div>
      )}

      {showAccountBootstrap ? (
        <SectionCard className="mb-4 p-4">
          <div className="grid gap-4 lg:grid-cols-[minmax(0,1.4fr)_minmax(260px,0.8fr)]">
            <div>
              <h2 className="mt-0 text-base font-semibold">账户尚未开始交易</h2>
              <p className="text-sm text-text-secondary mb-3">
                当前还没有持仓、挂单、成交和净值轨迹。先载入一笔示例委托并直接在下方提交，比先读完整个绩效与流水面板更容易进入状态。
              </p>
              <div className="flex gap-2 flex-wrap">
                <button type="button" onClick={() => loadExampleOrder('600519')} className="px-3 py-1.5 rounded border border-border text-sm cursor-pointer hover:bg-surface-alt">载入贵州茅台示例</button>
                <button type="button" onClick={() => loadExampleOrder('000001')} className="px-3 py-1.5 rounded border border-border text-sm cursor-pointer hover:bg-surface-alt">载入平安银行示例</button>
                <button type="button" onClick={() => void handleRefreshPrices()} className="px-3 py-1.5 rounded border border-border text-sm cursor-pointer hover:bg-surface-alt">先刷新价格</button>
              </div>
            </div>
            <div className="rounded-xl border border-border bg-surface-alt/40 p-3">
              <div className="text-sm font-medium text-text-primary">推荐流程</div>
              <ol className="mt-2 mb-0 space-y-2 pl-4 text-xs text-text-secondary">
                <li>载入示例代码，先用 100 股市价单完成首笔交易。</li>
                <li>如需价格参考，可先手动刷新一次行情。</li>
                <li>成交后再回来看持仓、净值和绩效变化。</li>
              </ol>
            </div>
          </div>
        </SectionCard>
      ) : null}

      {/* 下单面板 */}
      <SectionCard className="mb-4">
        <div className="flex items-center justify-between gap-3 flex-wrap mb-2">
          <h3 className="font-medium m-0">下单</h3>
          {showAccountBootstrap ? <span className="text-xs text-text-secondary">首笔交易建议使用示例代码和 100 股市价单</span> : null}
        </div>
        <div className="grid gap-4 xl:grid-cols-[minmax(0,1.15fr)_minmax(300px,0.85fr)] xl:items-start">
          <div>
            <form onSubmit={handleOrder} className="grid grid-cols-2 sm:grid-cols-4 gap-3">
              <StockCodeInput
                id="paper-order-code"
                label="股票代码"
                value={code}
                onChange={setCode}
                error={codeError}
              />
              <div className="flex flex-col gap-1">
                <label htmlFor="paper-order-direction" className="text-xs text-text-secondary">交易方向</label>
                <select
                  id="paper-order-direction"
                  value={direction}
                  onChange={e => setDirection(e.target.value as 'buy' | 'sell')}
                  className="border border-border rounded px-2 py-1.5 bg-surface text-sm"
                >
                  <option value="buy">买入</option>
                  <option value="sell">卖出</option>
                </select>
              </div>
              <div className="flex flex-col gap-1">
                <label htmlFor="paper-order-quantity" className="text-xs text-text-secondary">数量</label>
                <input
                  id="paper-order-quantity"
                  type="number"
                  value={quantity}
                  onChange={e => setQuantity(e.target.value)}
                  placeholder="数量"
                  min={1}
                  className="border border-border rounded px-2 py-1.5 bg-surface text-sm"
                />
              </div>
              <div className="flex flex-col gap-1">
                <label htmlFor="paper-order-type" className="text-xs text-text-secondary">订单类型</label>
                <select
                  id="paper-order-type"
                  value={orderType}
                  onChange={e => setOrderType(e.target.value as 'market' | 'limit' | 'stop')}
                  className="border border-border rounded px-2 py-1.5 bg-surface text-sm"
                >
                  <option value="market">市价单</option>
                  <option value="limit">限价单</option>
                  <option value="stop">止损单</option>
                </select>
              </div>
              {(orderType === 'limit' || orderType === 'market') && (
                <div className="flex flex-col gap-1">
                  <label htmlFor="paper-order-price" className="text-xs text-text-secondary">价格</label>
                  <input
                    id="paper-order-price"
                    type="number"
                    step="0.01"
                    value={price}
                    onChange={e => setPrice(e.target.value)}
                    placeholder="价格（可选）"
                    className="border border-border rounded px-2 py-1.5 bg-surface text-sm"
                  />
                </div>
              )}
              {orderType === 'stop' && (
                <div className="flex flex-col gap-1">
                  <label htmlFor="paper-order-stop-price" className="text-xs text-text-secondary">止损价</label>
                  <input
                    id="paper-order-stop-price"
                    type="number"
                    step="0.01"
                    value={stopPrice}
                    onChange={e => setStopPrice(e.target.value)}
                    placeholder="止损价"
                    className="border border-border rounded px-2 py-1.5 bg-surface text-sm"
                  />
                </div>
              )}
              <button type="submit" disabled={placeApi.isPending || routeExecutionApi.isPending || complianceApi.isPending}
                className={`col-span-2 sm:col-span-1 px-4 py-1.5 rounded text-sm font-medium text-white ${direction === 'buy' ? 'bg-danger' : 'bg-success'} disabled:opacity-50`}>
                {placeApi.isPending || routeExecutionApi.isPending ? '提交中...' : complianceApi.isPending ? '风控检查中...' : direction === 'buy' ? '买入' : '卖出'}
              </button>
            </form>
          </div>

          <div className="rounded-2xl border border-border bg-surface-alt/40 p-4">
            <div className="flex items-start justify-between gap-3">
              <div>
                <div className="text-sm font-medium text-text-primary">订单预览</div>
                <p className="mb-0 mt-1 text-xs leading-5 text-text-secondary">在确认弹窗前先核对方向、数量、价格、风控与执行路径，移动端也能直接看到关键信息。</p>
              </div>
              <Badge variant={direction === 'buy' ? 'danger' : 'success'}>{directionLabel}</Badge>
            </div>
            <div className="mt-3 grid gap-2 sm:grid-cols-2 xl:grid-cols-1">
              <div className="rounded-xl border border-border bg-surface p-3">
                <div className="text-xs text-text-secondary">标的 / 类型</div>
                <div className="mt-1 text-sm font-medium">{trimmedCode || '待填写代码'} · {orderTypeLabel}</div>
              </div>
              <div className="rounded-xl border border-border bg-surface p-3">
                <div className="text-xs text-text-secondary">数量 / 账户</div>
                <div className="mt-1 text-sm font-medium">{Number.isFinite(quantityValue) && quantityValue > 0 ? `${quantityValue} 股` : '待填写数量'} · {accountId || '默认账户'}</div>
              </div>
              <div className="rounded-xl border border-border bg-surface p-3">
                <div className="text-xs text-text-secondary">预览价格</div>
                <div className="mt-1 text-sm font-medium">{previewUnitPrice != null && Number.isFinite(previewUnitPrice) && previewUnitPrice > 0 ? fmtNum(previewUnitPrice, 2) : orderType === 'market' ? '未填写，按市价提交流程处理' : '待填写价格'}</div>
              </div>
              <div className="rounded-xl border border-border bg-surface p-3">
                <div className="text-xs text-text-secondary">预估金额</div>
                <div className="mt-1 text-sm font-medium">{estimatedAmount != null ? fmtNum(estimatedAmount) : '待补充价格后计算'}</div>
              </div>
            </div>

            <div className="mt-3 rounded-xl border border-border bg-surface p-3">
              <div className="text-xs font-medium text-text-primary">执行与风控开关</div>
              <div className="mt-2 space-y-2 text-sm text-text-secondary">
                <label htmlFor="paper-order-compliance-check" className="flex items-start gap-2 cursor-pointer">
                  <input id="paper-order-compliance-check" type="checkbox" checked={useComplianceCheck} onChange={e => setUseComplianceCheck(e.target.checked)} className="mt-0.5 rounded border-border accent-primary" />
                  <span>下单前执行合规风控，先检查规则再决定是否继续提交。</span>
                </label>
                <label htmlFor="paper-order-urgent-execution" className="flex items-start gap-2 cursor-pointer">
                  <input id="paper-order-urgent-execution" type="checkbox" checked={urgentExecution} onChange={e => setUrgentExecution(e.target.checked)} className="mt-0.5 rounded border-border accent-primary" />
                  <span className={urgentExecution ? 'text-primary' : ''}>启用极速智能路由，由 Execution Manager 优先决定提交路径。</span>
                </label>
              </div>
            </div>

            <div className="mt-3 rounded-xl border border-border bg-surface p-3">
              <div className="text-xs font-medium text-text-primary">提交前提醒</div>
              <ul className="mb-0 mt-2 space-y-2 pl-4 text-xs leading-5 text-text-secondary">
                {riskHints.map((hint) => <li key={hint}>{hint}</li>)}
              </ul>
            </div>
          </div>
        </div>

        {formError && <p className="text-danger text-xs mt-2 font-bold" role="alert">{formError}</p>}
        {formStatus && <p className="text-primary text-xs mt-2" role="status">{formStatus}</p>}
        {lastActionResult && <p className="text-success text-xs mt-2">{lastActionResult}</p>}
      </SectionCard>

      {/* System Status + Account Selector */}
      <div className="flex items-center gap-3 mb-3 flex-wrap">
        <Badge variant={matchOk ? 'success' : 'warning'}>撮合: {matchStatusLabel}</Badge>
        <Badge variant={navOk ? 'success' : 'warning'}>净值: {navStatusLabel}</Badge>
        <button
          type="button"
          onClick={handleRefreshPrices}
          disabled={refreshPricesApi.isPending}
          className="text-sm px-3 py-1 rounded border border-glass-border bg-surface hover:bg-surface/80 disabled:opacity-50 cursor-pointer"
        >
          {refreshPricesApi.isPending ? '刷新中...' : '刷新价格'}
        </button>
        {accounts.length > 1 && (
          <div className="flex flex-col gap-1">
            <label htmlFor="paper-account-select" className="text-xs text-text-secondary">交易账户</label>
            <select
              id="paper-account-select"
              value={accountId}
              onChange={(e) => setAccountId(e.target.value)}
              className="text-sm px-2 py-1 rounded border border-glass-border"
            >
              <option value="">默认账户</option>
              {accounts.map((a, i) => (
                <option key={a.account_id ?? i} value={a.account_id ?? ''}>{a.account_id ?? `账户${i + 1}`}</option>
              ))}
            </select>
          </div>
        )}
        <span className="text-xs text-text-secondary">交易时段内每 15 秒自动刷新价格，非交易时段仅支持手动刷新。</span>
        <span className="text-xs text-warning">市价单与持仓盈亏以最近一次刷新价格估算，非交易时段可能使用延迟行情。</span>
      </div>
      {statusNotes.length > 0 ? (
        <SectionCard className="mb-3 p-3">
          <h2 className="mt-0 text-sm font-semibold">{showAccountBootstrap ? '首笔交易提示' : '状态说明'}</h2>
          {showAccountBootstrap ? (
            <p className="mt-1 mb-2 text-xs text-text-secondary">
              首次进入模拟盘时，撮合和净值状态可能先显示为“待确认”。通常刷新价格或完成首笔委托后，状态会逐步稳定。
            </p>
          ) : null}
          <div className="space-y-1 text-xs text-text-secondary">
            {statusNotes.map((note) => <p key={note} className="m-0">{note}</p>)}
          </div>
        </SectionCard>
      ) : null}

      {/* KPI */}
      <KpiGrid cols={4} className="mb-4">
        <KpiCard title="总资产" value={fmtNum(totalValue)} />
        <KpiCard title="可用资金" value={fmtNum(cash)} />
        <KpiCard title="持仓市值" value={fmtNum(marketValue)} />
        <KpiCard title="总收益率" value={fmtPct(Number(returnPct))} change={Number(returnPct)} />
        <KpiCard title="今日盈亏" value={fmtNum(todayPnl)} change={todayPnl} />
      </KpiGrid>

      {!showAccountBootstrap ? (
        <SectionCard className="mb-4">
          <div className="flex items-center justify-between gap-3 flex-wrap mb-3">
            <h3 className="font-medium m-0">绩效分析</h3>
            <div className="flex items-center gap-2 flex-wrap">
              {[7, 30, 90, 0].map((days) => (
                <button
                  key={days}
                  type="button"
                  onClick={() => setPerfDays(days)}
                  className={`text-xs px-2 py-1 rounded border cursor-pointer ${perfDays === days ? 'border-primary text-primary' : 'border-glass-border text-text-secondary'}`}
                >
                  {days === 0 ? '全部' : `${days}天`}
                </button>
              ))}
              <button type="button" onClick={() => exportCSV(performanceData.map((item) => ({ 日期: item.date ?? '', 净值: item.totalValue ?? 0, 日收益率: item.dailyReturn ?? 0 })), `paper-trading-performance-${perfDays || 'all'}.csv`)} className="text-xs px-3 py-1 rounded border border-glass-border cursor-pointer">导出 CSV</button>
            </div>
          </div>
          <KpiGrid cols={4} className="mb-3">
            <KpiCard title="区间收益率" value={fmtPct(Number(performanceMetrics.totalReturn ?? 0) * 100)} change={Number(performanceMetrics.totalReturn ?? 0) * 100} />
            <KpiCard title="夏普比率" value={fmtNum(Number(performanceMetrics.sharpe ?? 0))} />
            <KpiCard title="最大回撤" value={fmtPct(Number(performanceMetrics.maxDrawdown ?? 0) * 100)} change={Number(performanceMetrics.maxDrawdown ?? 0) * 100} />
            <KpiCard title="胜率" value={fmtPct(Number(performanceMetrics.winRate ?? 0) * 100)} change={Number(performanceMetrics.winRate ?? 0) * 100} />
            <KpiCard title="平均持仓天数" value={fmtNum(Number(performanceMetrics.avgHoldDays ?? 0))} />
          </KpiGrid>
          {performanceData.length > 1 ? <LineChart categories={perfCategories} series={[{ name: '日收益率(%)', data: perfReturns }]} /> : <div className="text-sm text-text-secondary">暂无足够绩效数据</div>}
        </SectionCard>
      ) : null}

      {/* 持仓列表 */}
      <SectionCard className="mb-4">
        <h3 className="font-medium mb-2">持仓 ({positions.length})</h3>
        {positions.length > 0 ? (
          <DataTable
            columns={[
              { key: 'stock_code', label: '代码' },
              { key: 'stock_name', label: '名称' },
              { key: 'quantity', label: '数量' },
              { key: 'sellable', label: '可卖' },
              { key: 'cost_price', label: '成本', render: (v: unknown) => fmtNum(Number(v), 2) },
              { key: 'current_price', label: '现价', render: (v: unknown) => fmtNum(Number(v), 2) },
              { key: 'market_value', label: '市值', render: (v: unknown) => fmtNum(Number(v)) },
              {
                key: 'profit_rate', label: '盈亏率', render: (v: unknown) => {
                  const n = Number(v) * 100;
                  return <span className={n >= 0 ? 'text-danger font-medium' : 'text-success font-medium'}>{fmtPct(n)}</span>;
                }
              },
              {
                key: 'action',
                label: '操作',
                render: (_value: unknown, row: Record<string, unknown>) => (
                  <button
                    type="button"
                    onClick={() => quickSell(row as PaperTradingPosition)}
                    className="text-xs text-primary underline cursor-pointer"
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
                      <div className="text-sm font-medium text-text-primary">{String(row.stock_name ?? row.stock_code ?? '-')}</div>
                      <div className="text-xs text-text-secondary">代码：{String(row.stock_code ?? '-')}</div>
                    </div>
                    <div className={`text-xs font-medium ${profitRate >= 0 ? 'text-danger' : 'text-success'}`}>{fmtPct(profitRate)}</div>
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
                    className="text-xs text-primary underline cursor-pointer"
                  >
                    快速卖出
                  </button>
                </div>
              );
            }}
          />
        ) : <p className="text-muted text-sm">{showAccountBootstrap ? '完成首笔下单后，这里会显示持仓摘要和快速卖出入口。' : '暂无持仓'}</p>}
      </SectionCard>

      {/* 持仓分布 */}
      {positions.length > 0 && (
        <SectionCard className="mb-4 p-4">
          <h3 className="font-medium mb-2">持仓分布</h3>
          <PieChart
            data={positions.map(p => ({
              name: p.stock_name || p.stock_code || '未知',
              value: Number(p.market_value ?? 0),
            }))}
            donut
            height={260}
          />
        </SectionCard>
      )}

      {/* 挂单列表 */}
      {pending.length > 0 && (
        <SectionCard className="mb-4">
          <h3 className="font-medium mb-2">挂单 ({pending.length})</h3>
          <DataTable
            columns={[
              { key: 'code', label: '代码' },
              { key: 'direction', label: '方向' },
              { key: 'shares', label: '数量' },
              { key: 'order_type', label: '类型' },
              { key: 'price', label: '价格', render: (v: unknown) => v ? fmtNum(Number(v), 2) : '-' },
              { key: 'stop_price', label: '止损价', render: (v: unknown) => v ? fmtNum(Number(v), 2) : '-' },
              {
                key: 'id', label: '操作', render: (_: unknown, row: Record<string, unknown>) => (
                  <button
                    type="button"
                    onClick={() => handleCancel(Number(row.id))}
                    disabled={cancelingOrderIds.includes(Number(row.id))}
                    className="text-xs text-danger underline cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed"
                  >
                    {cancelingOrderIds.includes(Number(row.id)) ? '撤单中...' : '撤单'}
                  </button>
                )
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
                      <div className="text-sm font-medium text-text-primary">{String(row.code ?? '-')} · {String(row.direction ?? '-')}</div>
                      <div className="text-xs text-text-secondary">{String(row.order_type ?? '-')} / {String(row.shares ?? '-')} 股</div>
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
                    className="text-xs text-danger underline cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed"
                  >
                    {isCanceling ? '撤单中...' : '撤单'}
                  </button>
                </div>
              );
            }}
          />
        </SectionCard>
      )}

      {!showAccountBootstrap ? (
        <>
          {/* 成交记录 */}
          <SectionCard className="mb-4">
            <h3 className="font-medium mb-2">成交记录</h3>
            {trades.length > 0 ? (
              <DataTable
                columns={[
                  { key: 'trade_time', label: '时间', render: (v: unknown) => String(v ?? '').slice(0, 16) },
                  { key: 'stock_code', label: '代码' },
                  { key: 'trade_type', label: '方向' },
                  { key: 'quantity', label: '数量' },
                  { key: 'price', label: '价格', render: (v: unknown) => fmtNum(Number(v), 2) },
                  { key: 'amount', label: '金额', render: (v: unknown) => fmtNum(Number(v)) },
                  { key: 'commission', label: '佣金', render: (v: unknown) => fmtNum(Number(v), 4) },
                ]}
                rows={trades as Record<string, unknown>[]}
                mobileCardRender={(row) => (
                  <div className="space-y-2">
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <div className="text-sm font-medium text-text-primary">{String(row.stock_code ?? '-')} · {String(row.trade_type ?? '-')}</div>
                        <div className="text-xs text-text-secondary">时间：{String(row.trade_time ?? '').slice(0, 16) || '-'}</div>
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
            ) : <p className="text-muted text-sm">暂无成交</p>}
          </SectionCard>

          {/* NAV 曲线 */}
          {navData.length > 1 ? (
            <SectionCard>
              <h3 className="font-medium mb-2">账户净值走势</h3>
              <LineChart categories={navCategories} series={[{ name: '净值', data: navValues }]} />
            </SectionCard>
          ) : null}
        </>
      ) : null}
      {/* 下单确认弹窗 */}
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
            <div>标的：<span className="font-medium">{String(pendingOrderRequest.body.code)}</span></div>
            <div>方向：<span className={`font-medium ${pendingOrderRequest.body.direction === 'buy' ? 'text-danger' : 'text-success'}`}>{pendingOrderRequest.body.direction === 'buy' ? '买入' : '卖出'}</span></div>
            <div>数量：<span className="font-medium">{String(pendingOrderRequest.body.quantity)} 股</span></div>
            <div>类型：<span className="font-medium">{pendingOrderRequest.body.order_type === 'market' ? '市价单' : pendingOrderRequest.body.order_type === 'limit' ? '限价单' : '止损单'}</span></div>
            {pendingOrderRequest.body.price ? <div>价格：<span className="font-medium">{String(pendingOrderRequest.body.price)}</span></div> : null}
            {pendingOrderRequest.body.stop_price ? <div>止损价：<span className="font-medium">{String(pendingOrderRequest.body.stop_price)}</span></div> : null}
            {pendingOrderRequest.body.price ? <div>预估金额：<span className="font-medium">{fmtNum(Number(pendingOrderRequest.body.price) * Number(pendingOrderRequest.body.quantity))}</span></div> : null}
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
    </PageContainer>
  );
}
