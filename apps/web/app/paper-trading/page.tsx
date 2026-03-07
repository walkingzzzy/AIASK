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
import { ErrorState, LoadingState } from '@/components/status-state';
import { extractArray, fmtNum, fmtPct } from '@/lib/data-utils';
import { useTradeSubscription } from '@/lib/ws';
import { isTradingHours } from '@/lib/trading-hours';
import { exportCSV } from '@/lib/export';

type Account = { account_id?: string; user_id?: string; initial_capital?: number };

type Summary = {
  account_id?: string;
  account?: Record<string, unknown>;
  positions_count?: number;
  pending_orders_count?: number;
  total_value?: number;
  total_return_pct?: number;
};

type Position = {
  stock_code?: string; stock_name?: string; quantity?: number;
  cost_price?: number; current_price?: number; market_value?: number; profit_rate?: number; sellable?: number;
};

type Trade = {
  id?: string; stock_code?: string; trade_type?: string;
  price?: number; quantity?: number; amount?: number; commission?: number;
  trade_time?: string;
};

type PendingOrder = {
  id?: number; code?: string; direction?: string; shares?: number;
  price?: number; order_type?: string; stop_price?: number; status?: string;
  created_at?: string;
};

type NavPoint = { nav_date?: string; total_value?: number; daily_return?: number };
type PerformancePoint = { date?: string; totalValue?: number; dailyReturn?: number };
type PerformanceMetrics = { totalReturn?: number; sharpe?: number; maxDrawdown?: number; winRate?: number; avgHoldDays?: number };

export default function PaperTradingPage() {
  const { toast } = useToast();
  const { code, setCode, codeError, validate, trimmedCode } = useStockCode('600519');
  const [direction, setDirection] = useState<'buy' | 'sell'>('buy');
  const [quantity, setQuantity] = useState('100');
  const [price, setPrice] = useState('');
  const [orderType, setOrderType] = useState<'market' | 'limit' | 'stop'>('market');
  const [stopPrice, setStopPrice] = useState('');
  const [formError, setFormError] = useState<string | null>(null);
  const [accountId, setAccountId] = useState('');
  const [pendingOrderBody, setPendingOrderBody] = useState<Record<string, unknown> | null>(null);
  const [cancelOrderId, setCancelOrderId] = useState<number | null>(null);
  const [tradeNotice, setTradeNotice] = useState<string | null>(null);
  const [perfDays, setPerfDays] = useState(30);

  // T-005: WS real-time trade order updates
  const handleTradeUpdate = useCallback((data: Record<string, unknown>) => {
    const status = String(data.status ?? '');
    const code = String(data.code ?? data.stock_code ?? '');
    setTradeNotice(`订单 ${code} ${status === 'filled' ? '已成交' : status === 'partial' ? '部分成交' : status === 'rejected' ? '被拒绝' : '状态更新'}`);
    // Auto-dismiss after 5s
    setTimeout(() => setTradeNotice(null), 5000);
  }, []);

  const qs = accountId ? `?account_id=${accountId}` : '';

  // 8 read queries — auto-fetch on mount, re-fetch when qs changes
  const accountsQ = useApiQuery<unknown>('/paper-trading/accounts');
  const matchStatusQ = useApiQuery<unknown>('/paper-trading/matching-status');
  const navStatusQ = useApiQuery<unknown>('/paper-trading/nav-status');
  const summaryQ = useApiQuery<Summary>(qs ? '/paper-trading/summary' + qs : '/paper-trading/summary');
  const positionsQ = useApiQuery<{ positions?: Position[] }>('/paper-trading/positions' + qs);
  const ordersQ = useApiQuery<{ orders?: Trade[] }>('/paper-trading/orders' + qs);
  const pendingQ = useApiQuery<{ orders?: PendingOrder[] }>('/paper-trading/pending-orders' + qs);
  const navQ = useApiQuery<{ nav?: NavPoint[] }>('/paper-trading/nav-history' + qs);
  const performanceQ = useApiQuery<{ dailyReturns?: PerformancePoint[]; metrics?: PerformanceMetrics }>(`/paper-trading/performance${qs ? `${qs}&days=${perfDays}` : `?days=${perfDays}`}`);

  // Subscribe to trade updates via WS
  useTradeSubscription({ accountId: accountId || 'default', onUpdate: handleTradeUpdate });

  // Advanced MCP Managers (Compliance & Execution)
  const [useComplianceCheck, setUseComplianceCheck] = useState(false);
  const [urgentExecution, setUrgentExecution] = useState(false);
  const complianceApi = useApiMutation<Record<string, unknown>>();
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

  const accounts = useMemo(() => extractArray(accountsQ.data, 'accounts', 'items', 'data') as Account[], [accountsQ.data]);
  const matchStatus = (matchStatusQ.data ?? {}) as Record<string, unknown>;
  const navStatus = (navStatusQ.data ?? {}) as Record<string, unknown>;
  const matchOk = matchStatus.status === 'running' || matchStatus.running === true || matchStatus.ok === true;
  const navOk = navStatus.status === 'running' || navStatus.running === true || navStatus.ok === true;

  const acct = summaryQ.data?.account as Record<string, unknown> | undefined;
  const totalValue = Number(summaryQ.data?.total_value ?? acct?.total_value ?? 0);
  const cash = Number(acct?.current_capital ?? 0);
  const initial = Number(acct?.initial_capital ?? 100000);
  const marketValue = totalValue - cash;
  const returnPct = summaryQ.data?.total_return_pct ?? (initial > 0 ? (totalValue - initial) / initial * 100 : 0);

  const positions = positionsQ.data?.positions ?? [];
  const trades = ordersQ.data?.orders ?? [];
  const pending = pendingQ.data?.orders ?? [];
  const navData = navQ.data?.nav ?? [];
  const performanceData = performanceQ.data?.dailyReturns ?? [];
  const performanceMetrics = performanceQ.data?.metrics ?? {};

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

  const loading = summaryQ.isPending || refreshPricesApi.isPending;
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
    try {
      await refreshPricesApi.triggerAsync('/paper-trading/update-prices', { method: 'POST' }, accountId ? { account_id: accountId } : {});
      toast('持仓价格已刷新', 'success');
    } catch (err) {
      setFormError(String(err));
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

  async function handleOrder(e: FormEvent) {
    e.preventDefault();
    setFormError(null);
    placeApi.reset();
    if (!validate()) return;
    const qty = parseInt(quantity, 10);
    if (!qty || qty <= 0) { setFormError('数量必须大于0'); return; }
    if (direction === 'buy' && qty % 100 !== 0) { setFormError('买入数量必须为100的整数倍（手数规则）'); return; }
    if (orderType === 'limit' && (!price || parseFloat(price) <= 0)) { setFormError('限价单必须填写有效价格'); return; }
    if (orderType === 'stop' && (!stopPrice || parseFloat(stopPrice) <= 0)) { setFormError('止损单必须填写止损价'); return; }
    if (price && parseFloat(price) <= 0) { setFormError('价格必须大于0'); return; }

    const body: Record<string, unknown> = {
      code: trimmedCode, direction, quantity: qty, order_type: orderType,
    };
    if (orderType === 'limit' && price) body.price = parseFloat(price);
    if (orderType === 'stop' && stopPrice) body.stop_price = parseFloat(stopPrice);
    if (orderType === 'market' && price) body.price = parseFloat(price);

    setPendingOrderBody(body);
  }

  async function confirmOrder() {
    if (!pendingOrderBody) return;
    try {
      if (useComplianceCheck) {
        setFormError('正在进行合规检查...');
        const complianceRes = await complianceApi.triggerAsync('/paper-trading/check-compliance', { method: 'POST' }, pendingOrderBody);
        const compData = complianceRes?.data as Record<string, unknown> | undefined;
        if (!complianceRes?.success || compData?.status !== 'passed') {
          setFormError(`合规检查失败: ${compData?.reason || '触发风控限制'}`);
          setPendingOrderBody(null);
          return;
        }
      }

      setFormError('正在提交订单...');
      if (urgentExecution) {
        // Use intelligent execution manager router
        await routeExecutionApi.triggerAsync('/paper-trading/route-execution', { method: 'POST' }, { ...pendingOrderBody, urgency: 'high' });
      } else {
        // Use standard paper trading local router
        await placeApi.triggerAsync('/paper-trading/order', { method: 'POST' }, pendingOrderBody);
      }
      setFormError(null);
      setPendingOrderBody(null);
    } catch (err) {
      setFormError(String(err));
      setPendingOrderBody(null);
    }
  }

  async function handleCancel(orderId: number) {
    setCancelOrderId(orderId);
  }

  async function confirmCancel() {
    if (cancelOrderId == null) return;
    const id = cancelOrderId;
    setCancelOrderId(null);
    try {
      await cancelApi.triggerAsync('/paper-trading/cancel', { method: 'POST' }, { order_id: String(id) });
    } catch (err) {
      setFormError(String(err));
    }
  }

  return (
    <PageContainer>
      <h2 className="text-lg font-semibold mb-3">模拟交易</h2>

      {/* System Status + Account Selector */}
      <div className="flex items-center gap-3 mb-3 flex-wrap">
        <Badge variant={matchOk ? 'success' : 'warning'}>撮合: {matchOk ? '运行中' : '未知'}</Badge>
        <Badge variant={navOk ? 'success' : 'warning'}>净值: {navOk ? '运行中' : '未知'}</Badge>
        <button
          type="button"
          onClick={handleRefreshPrices}
          disabled={refreshPricesApi.isPending}
          className="text-sm px-3 py-1 rounded border border-glass-border bg-surface hover:bg-surface/80 disabled:opacity-50 cursor-pointer"
        >
          {refreshPricesApi.isPending ? '刷新中...' : '刷新价格'}
        </button>
        {accounts.length > 1 && (
          <select value={accountId} onChange={(e) => setAccountId(e.target.value)}
            className="text-sm px-2 py-1 rounded border border-glass-border">
            <option value="">默认账户</option>
            {accounts.map((a, i) => (
              <option key={a.account_id ?? i} value={a.account_id ?? ''}>{a.account_id ?? `账户${i + 1}`}</option>
            ))}
          </select>
        )}
        <span className="text-xs text-text-secondary">交易时段内每 15 秒自动刷新价格，非交易时段仅支持手动刷新。</span>
      </div>

      {error && <ErrorState text={error} />}

      {/* WS 交易通知 */}
      {tradeNotice && (
        <div className="mb-3 px-4 py-2 rounded-lg bg-primary/10 border border-primary/30 text-sm text-primary flex items-center gap-2">
          <span>📋</span> {tradeNotice}
        </div>
      )}

      {/* KPI */}
      <KpiGrid cols={4} className="mb-4">
        <KpiCard title="总资产" value={fmtNum(totalValue)} />
        <KpiCard title="可用资金" value={fmtNum(cash)} />
        <KpiCard title="持仓市值" value={fmtNum(marketValue)} />
        <KpiCard title="总收益率" value={fmtPct(Number(returnPct))} change={Number(returnPct)} />
        <KpiCard title="今日盈亏" value={fmtNum(todayPnl)} change={todayPnl} />
      </KpiGrid>

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

      {/* 下单面板 */}
      <SectionCard className="mb-4">
        <h3 className="font-medium mb-2">下单</h3>
        <form onSubmit={handleOrder} className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          <StockCodeInput value={code} onChange={setCode} error={codeError} />
          <select value={direction} onChange={e => setDirection(e.target.value as 'buy' | 'sell')}
            aria-label="交易方向"
            className="border border-border rounded px-2 py-1.5 bg-surface text-sm">
            <option value="buy">买入</option>
            <option value="sell">卖出</option>
          </select>
          <input type="number" value={quantity} onChange={e => setQuantity(e.target.value)}
            aria-label="数量" placeholder="数量" min={1} className="border border-border rounded px-2 py-1.5 bg-surface text-sm" />
          <select value={orderType} onChange={e => setOrderType(e.target.value as 'market' | 'limit' | 'stop')}
            aria-label="订单类型"
            className="border border-border rounded px-2 py-1.5 bg-surface text-sm">
            <option value="market">市价单</option>
            <option value="limit">限价单</option>
            <option value="stop">止损单</option>
          </select>
          {(orderType === 'limit' || orderType === 'market') && (
            <input type="number" step="0.01" value={price} onChange={e => setPrice(e.target.value)}
              aria-label="价格" placeholder="价格（可选）" className="border border-border rounded px-2 py-1.5 bg-surface text-sm" />
          )}
          {orderType === 'stop' && (
            <input type="number" step="0.01" value={stopPrice} onChange={e => setStopPrice(e.target.value)}
              aria-label="止损价" placeholder="止损价" className="border border-border rounded px-2 py-1.5 bg-surface text-sm" />
          )}
          <button type="submit" disabled={placeApi.isPending || routeExecutionApi.isPending || complianceApi.isPending}
            className={`col-span-2 sm:col-span-1 px-4 py-1.5 rounded text-sm font-medium text-white ${direction === 'buy' ? 'bg-danger' : 'bg-success'} disabled:opacity-50`}>
            {placeApi.isPending || routeExecutionApi.isPending ? '提交中...' : complianceApi.isPending ? '风控检查中...' : direction === 'buy' ? '买入' : '卖出'}
          </button>
        </form>

        <div className="flex gap-4 mt-4 items-center text-sm text-muted-foreground border-t pt-3">
          <label className="flex items-center gap-1 cursor-pointer">
            <input type="checkbox" checked={useComplianceCheck} onChange={e => setUseComplianceCheck(e.target.checked)} className="rounded border-border accent-primary" />
            <span>下单前执行合规风控 (Compliance Check)</span>
          </label>
          <label className="flex items-center gap-1 cursor-pointer">
            <input type="checkbox" checked={urgentExecution} onChange={e => setUrgentExecution(e.target.checked)} className="rounded border-border accent-primary" />
            <span className={urgentExecution ? 'text-primary' : ''}>启用极速智能路由 (Execution Manager)</span>
          </label>
        </div>

        {formError && <p className="text-danger text-xs mt-2 font-bold" role="alert">{formError}</p>}
        {(placeApi.data || routeExecutionApi.data) && <p className="text-success text-xs mt-2">下单成功</p>}
      </SectionCard>

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
            ]}
            rows={positions as Record<string, unknown>[]}
          />
        ) : <p className="text-muted text-sm">暂无持仓</p>}
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
                  <button onClick={() => handleCancel(row.id as number)}
                    disabled={cancelApi.isPending}
                    className="text-xs text-danger underline cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed">撤单</button>
                )
              },
            ]}
            rows={pending as Record<string, unknown>[]}
          />
        </SectionCard>
      )}

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
          />
        ) : <p className="text-muted text-sm">暂无成交</p>}
      </SectionCard>

      {/* NAV 曲线 */}
      {navData.length > 1 && (
        <SectionCard>
          <h3 className="font-medium mb-2">账户净值走势</h3>
          <LineChart categories={navCategories} series={[{ name: '净值', data: navValues }]} />
        </SectionCard>
      )}
      {/* 下单确认弹窗 */}
      <ConfirmDialog
        open={!!pendingOrderBody}
        title={`确认${pendingOrderBody?.direction === 'buy' ? '买入' : '卖出'}`}
        onConfirm={confirmOrder}
        onCancel={() => setPendingOrderBody(null)}
        confirmText="确认下单"
        cancelText="取消"
        danger={pendingOrderBody?.direction === 'sell'}
      >
        {pendingOrderBody && (
          <div className="space-y-1 text-sm">
            <div>标的：<span className="font-medium">{String(pendingOrderBody.code)}</span></div>
            <div>方向：<span className={`font-medium ${pendingOrderBody.direction === 'buy' ? 'text-danger' : 'text-success'}`}>{pendingOrderBody.direction === 'buy' ? '买入' : '卖出'}</span></div>
            <div>数量：<span className="font-medium">{String(pendingOrderBody.quantity)} 股</span></div>
            <div>类型：<span className="font-medium">{pendingOrderBody.order_type === 'market' ? '市价单' : pendingOrderBody.order_type === 'limit' ? '限价单' : '止损单'}</span></div>
            {pendingOrderBody.price ? <div>价格：<span className="font-medium">{String(pendingOrderBody.price)}</span></div> : null}
            {pendingOrderBody.stop_price ? <div>止损价：<span className="font-medium">{String(pendingOrderBody.stop_price)}</span></div> : null}
            {pendingOrderBody.price ? <div>预估金额：<span className="font-medium">{fmtNum(Number(pendingOrderBody.price) * Number(pendingOrderBody.quantity))}</span></div> : null}
          </div>
        )}
      </ConfirmDialog>

      {/* 撤单确认弹窗 */}
      <ConfirmDialog
        open={cancelOrderId != null}
        title="确认撤单"
        message={`确定要撤销订单 #${cancelOrderId} 吗？`}
        onConfirm={confirmCancel}
        onCancel={() => setCancelOrderId(null)}
        confirmText="确认撤单"
        danger
      />
    </PageContainer>
  );
}