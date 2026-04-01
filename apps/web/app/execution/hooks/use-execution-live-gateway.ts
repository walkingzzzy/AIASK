'use client';

import { useMemo, useState, type FormEvent } from 'react';
import { useApiMutation } from '@/hooks/use-api-mutation';
import { useApiQuery } from '@/hooks/use-api-query';
import { briefDateTime } from '@/lib/execution-normalizers';
import type { ExecutionLiveGatewayPanelProps } from '@/app/execution/components/execution-live-gateway-panel';
import type {
  LiveTradingAccountResponse,
  LiveTradingBrokerReceiptResponse,
  LiveTradingCancelOrderResponse,
  LiveTradingFillsResponse,
  LiveTradingGatewayStatusResponse,
  LiveTradingMirrorToPaperResponse,
  LiveTradingOrderEventsResponse,
  LiveTradingOrdersResponse,
  LiveTradingOrderStatusResponse,
  LiveTradingPositionsResponse,
  LiveTradingSubmitOrderResponse,
  LiveTradingSyncOrderEventsResponse,
} from '@aiask/shared-types';

type UseExecutionLiveGatewayArgs = {
  accountId: string;
};

type UseExecutionLiveGatewayResult = {
  liveGatewayReady: boolean;
  liveOrderCount: number;
  liveFillCount: number;
  panelProps: Omit<ExecutionLiveGatewayPanelProps, 'onOpenArtifactDetail' | 'onUseArtifactForQuery'>;
};

export function useExecutionLiveGateway({
  accountId,
}: UseExecutionLiveGatewayArgs): UseExecutionLiveGatewayResult {
  const [liveFormError, setLiveFormError] = useState<string | null>(null);
  const [liveSymbol, setLiveSymbol] = useState('AAPL');
  const [liveSide, setLiveSide] = useState<'buy' | 'sell'>('buy');
  const [liveQty, setLiveQty] = useState('1');
  const [liveOrderType, setLiveOrderType] = useState<'market' | 'limit' | 'stop'>('market');
  const [liveLimitPrice, setLiveLimitPrice] = useState('');
  const [liveStopPrice, setLiveStopPrice] = useState('');
  const [liveDryRun, setLiveDryRun] = useState(true);
  const [liveOrdersStatus, setLiveOrdersStatus] = useState('open');
  const [liveOrderIdInput, setLiveOrderIdInput] = useState('');
  const [submittedLiveOrderId, setSubmittedLiveOrderId] = useState('');
  const [liveMirrorExecute, setLiveMirrorExecute] = useState(false);

  const liveGatewayQ = useApiQuery<LiveTradingGatewayStatusResponse>('/execution/live/gateway-status', {
    staleTime: 15_000,
  });
  const liveGatewayReady = Boolean(liveGatewayQ.data?.configured && liveGatewayQ.data?.connected);
  const liveAccountQ = useApiQuery<LiveTradingAccountResponse>(liveGatewayReady ? '/execution/live/account' : null, {
    staleTime: 15_000,
  });
  const livePositionsQ = useApiQuery<LiveTradingPositionsResponse>(
    liveGatewayReady ? '/execution/live/positions' : null,
    { staleTime: 15_000 },
  );
  const liveOrdersPath = useMemo(() => {
    if (!liveGatewayReady) return null;
    const params = new URLSearchParams();
    params.set('status', liveOrdersStatus);
    params.set('limit', '20');
    return `/execution/live/orders?${params.toString()}`;
  }, [liveGatewayReady, liveOrdersStatus]);
  const liveOrdersQ = useApiQuery<LiveTradingOrdersResponse>(liveOrdersPath, { staleTime: 10_000 });
  const liveOrderStatusPath = useMemo(() => {
    const orderId = submittedLiveOrderId.trim();
    if (!liveGatewayReady || !orderId) return null;
    return `/execution/live/orders/${encodeURIComponent(orderId)}`;
  }, [liveGatewayReady, submittedLiveOrderId]);
  const liveOrderStatusQ = useApiQuery<LiveTradingOrderStatusResponse>(liveOrderStatusPath, {
    staleTime: 10_000,
  });
  const liveOrderEventsPath = useMemo(() => {
    const orderId = submittedLiveOrderId.trim();
    if (!liveGatewayReady || !orderId) return null;
    return `/execution/live/orders/${encodeURIComponent(orderId)}/events?limit=50`;
  }, [liveGatewayReady, submittedLiveOrderId]);
  const liveOrderEventsQ = useApiQuery<LiveTradingOrderEventsResponse>(liveOrderEventsPath, {
    staleTime: 10_000,
  });
  const liveReceiptPath = useMemo(() => {
    const orderId = submittedLiveOrderId.trim();
    if (!liveGatewayReady || !orderId) return null;
    return `/execution/live/orders/${encodeURIComponent(orderId)}/receipt`;
  }, [liveGatewayReady, submittedLiveOrderId]);
  const liveReceiptQ = useApiQuery<LiveTradingBrokerReceiptResponse>(liveReceiptPath, {
    staleTime: 10_000,
  });
  const liveFillsPath = useMemo(() => {
    if (!liveGatewayReady) return null;
    const params = new URLSearchParams();
    params.set('limit', '20');
    const orderId = submittedLiveOrderId.trim();
    if (orderId) params.set('order_id', orderId);
    return `/execution/live/fills?${params.toString()}`;
  }, [liveGatewayReady, submittedLiveOrderId]);
  const liveFillsQ = useApiQuery<LiveTradingFillsResponse>(liveFillsPath, {
    staleTime: 10_000,
  });

  const liveSubmitApi = useApiMutation<LiveTradingSubmitOrderResponse>({
    onSuccess: (payload) => {
      const orderId = String(payload.order?.order_id ?? '').trim();
      if (orderId) {
        setLiveOrderIdInput(orderId);
        setSubmittedLiveOrderId(orderId);
      }
      if (liveGatewayReady) {
        void liveOrdersQ.refetch();
      }
      if (orderId) {
        void liveOrderStatusQ.refetch();
        void liveOrderEventsQ.refetch();
        void liveReceiptQ.refetch();
        void liveFillsQ.refetch();
      }
    },
  });
  const liveCancelApi = useApiMutation<LiveTradingCancelOrderResponse>({
    onSuccess: () => {
      if (liveGatewayReady) {
        void liveOrdersQ.refetch();
      }
      if (submittedLiveOrderId.trim()) {
        void liveOrderStatusQ.refetch();
        void liveOrderEventsQ.refetch();
        void liveReceiptQ.refetch();
        void liveFillsQ.refetch();
      }
    },
  });
  const liveMirrorApi = useApiMutation<LiveTradingMirrorToPaperResponse>();
  const liveSyncEventsApi = useApiMutation<LiveTradingSyncOrderEventsResponse>({
    onSuccess: () => {
      if (submittedLiveOrderId.trim()) {
        void liveOrderEventsQ.refetch();
        void liveReceiptQ.refetch();
        void liveFillsQ.refetch();
      }
    },
  });

  const liveGateway = liveGatewayQ.data ?? null;
  const liveAccount = liveAccountQ.data?.account ?? liveGateway?.account ?? null;
  const livePositions = livePositionsQ.data?.positions ?? [];
  const liveOrders = liveOrdersQ.data?.orders ?? [];
  const liveOrderStatus = liveOrderStatusQ.data?.order ?? null;
  const liveOrderEvents = useMemo(() => liveOrderEventsQ.data?.events ?? [], [liveOrderEventsQ.data?.events]);
  const liveReceipt = liveReceiptQ.data?.receipt ?? null;
  const liveFills = useMemo(() => liveFillsQ.data?.fills ?? [], [liveFillsQ.data?.fills]);
  const liveEventArtifactId = String(liveSyncEventsApi.data?.artifact_id ?? '').trim();
  const liveEventArtifactCount = Number(liveSyncEventsApi.data?.collection?.count ?? liveOrderEvents.length ?? 0);
  const liveGatewayRefreshing =
    liveGatewayQ.isFetching ||
    liveAccountQ.isFetching ||
    livePositionsQ.isFetching ||
    liveOrdersQ.isFetching ||
    liveFillsQ.isFetching;
  const liveEventCurrentStatus = liveOrderEventsQ.data?.state_machine?.current_status || liveOrderStatus?.status || '-';
  const liveEventRows = useMemo(
    () =>
      liveOrderEvents.map((event, index) => ({
        id: `${event.event_type ?? 'event'}-${index + 1}`,
        occurred_at: briefDateTime(event.occurred_at),
        event_type: event.event_type,
        event_category: event.event_category,
        event_status: event.event_status ?? event.status,
        from_status: event.state_transition?.from_status ?? '-',
        to_status: event.state_transition?.to_status ?? '-',
        fill_qty: event.fill_event?.qty ?? event.fill_event?.shares ?? null,
        fill_price: event.fill_event?.price ?? null,
        receipt_reason: event.brokerage_event?.reason ?? null,
      })),
    [liveOrderEvents],
  );
  const liveFillRows = useMemo(
    () =>
      liveFills.map((fill, index) => ({
        id: fill.fill_id ?? `${fill.order_id ?? 'fill'}-${index + 1}`,
        occurred_at: briefDateTime(fill.occurred_at),
        symbol: fill.symbol,
        side: fill.side,
        qty: fill.qty ?? fill.shares,
        price: fill.price,
        amount: fill.amount,
        commission: fill.commission,
        source: fill.source,
      })),
    [liveFills],
  );

  async function refreshLiveGateway() {
    await liveGatewayQ.refetch();
    if (liveGatewayReady) {
      await Promise.all([
        liveAccountQ.refetch(),
        livePositionsQ.refetch(),
        liveOrdersQ.refetch(),
        liveFillsQ.refetch(),
      ]);
      if (submittedLiveOrderId.trim()) {
        await Promise.all([liveOrderStatusQ.refetch(), liveOrderEventsQ.refetch(), liveReceiptQ.refetch()]);
      }
    }
  }

  function handleLiveOrderQuery(event?: FormEvent<HTMLFormElement>) {
    event?.preventDefault();
    const nextId = liveOrderIdInput.trim();
    if (!nextId) {
      setLiveFormError('请输入真实订单 order_id');
      return;
    }
    setLiveFormError(null);
    setSubmittedLiveOrderId(nextId);
  }

  async function handleSelectLiveOrder(row: Record<string, unknown>) {
    const orderId = String(row.order_id ?? '').trim();
    if (!orderId) return;
    setLiveFormError(null);
    setLiveOrderIdInput(orderId);
    if (submittedLiveOrderId.trim() === orderId) {
      await Promise.all([
        liveOrderStatusQ.refetch(),
        liveOrderEventsQ.refetch(),
        liveReceiptQ.refetch(),
        liveFillsQ.refetch(),
      ]);
      return;
    }
    setSubmittedLiveOrderId(orderId);
  }

  async function handleLiveSubmitOrder() {
    setLiveFormError(null);
    const symbol = liveSymbol.trim().toUpperCase();
    const qty = Number(liveQty);
    if (!symbol) {
      setLiveFormError('请输入真实网关标的代码，例如 AAPL');
      return;
    }
    if (!(qty > 0)) {
      setLiveFormError('真实订单数量必须大于 0');
      return;
    }
    if (liveOrderType === 'limit' && !(Number(liveLimitPrice) > 0)) {
      setLiveFormError('限价单需要有效的 limit price');
      return;
    }
    if (liveOrderType === 'stop' && !(Number(liveStopPrice) > 0)) {
      setLiveFormError('止损单需要有效的 stop price');
      return;
    }
    try {
      await liveSubmitApi.triggerAsync(
        '/execution/live/orders',
        { method: 'POST' },
        {
          symbol,
          side: liveSide,
          qty,
          type: liveOrderType,
          limit_price: liveOrderType === 'limit' ? Number(liveLimitPrice) : undefined,
          stop_price: liveOrderType === 'stop' ? Number(liveStopPrice) : undefined,
          dry_run: liveDryRun,
        },
      );
    } catch {
      // Errors are surfaced by useApiMutation via toast + liveSubmitApi.error.
    }
  }

  async function handleLiveCancelOrder() {
    setLiveFormError(null);
    const orderId = liveOrderIdInput.trim();
    if (!orderId) {
      setLiveFormError('撤单前请先输入真实订单 order_id');
      return;
    }
    try {
      await liveCancelApi.triggerAsync(
        '/execution/live/orders/cancel',
        { method: 'POST' },
        {
          order_id: orderId,
          dry_run: liveDryRun,
        },
      );
    } catch {
      return;
    }
    setSubmittedLiveOrderId(orderId);
  }

  async function handleLiveMirrorToPaper() {
    setLiveFormError(null);
    try {
      await liveMirrorApi.triggerAsync(
        '/execution/live/mirror-to-paper',
        { method: 'POST' },
        {
          execute: liveMirrorExecute,
          paper_account_id: accountId || undefined,
        },
      );
    } catch {
      // Keep the UI responsive; the mutation hook already stores the surfaced error text.
    }
  }

  async function handleLiveSyncEvents() {
    setLiveFormError(null);
    const orderId = submittedLiveOrderId.trim() || liveOrderIdInput.trim();
    if (!orderId) {
      setLiveFormError('同步事件快照前请先指定真实订单 order_id');
      return;
    }
    try {
      await liveSyncEventsApi.triggerAsync(
        '/execution/live/order-events/sync',
        { method: 'POST' },
        {
          order_id: orderId,
          persist_artifact: true,
        },
      );
    } catch {
      // Errors are surfaced by useApiMutation via toast + liveSyncEventsApi.error.
    }
  }

  return {
    liveGatewayReady,
    liveOrderCount: liveOrders.length,
    liveFillCount: liveFillRows.length,
    panelProps: {
      liveGateway,
      liveAccount,
      liveGatewayReady,
      liveGatewayRefreshing,
      livePositions: livePositions as unknown as Record<string, unknown>[],
      liveOrders: liveOrders as unknown as Record<string, unknown>[],
      liveOrdersStatus,
      liveFillRows: liveFillRows as unknown as Record<string, unknown>[],
      liveEventRows: liveEventRows as unknown as Record<string, unknown>[],
      liveOrderStatus,
      liveReceipt,
      liveSubmitResult: liveSubmitApi.data,
      liveMirrorResult: liveMirrorApi.data,
      liveSyncEventsResult: liveSyncEventsApi.data,
      liveEventArtifactId,
      liveEventArtifactCount,
      liveEventCurrentStatus,
      submittedLiveOrderId,
      liveForm: {
        symbol: liveSymbol,
        side: liveSide,
        qty: liveQty,
        orderType: liveOrderType,
        limitPrice: liveLimitPrice,
        stopPrice: liveStopPrice,
        dryRun: liveDryRun,
        mirrorExecute: liveMirrorExecute,
        orderIdInput: liveOrderIdInput,
      },
      pending: {
        submit: liveSubmitApi.isPending,
        cancel: liveCancelApi.isPending,
        mirror: liveMirrorApi.isPending,
        sync: liveSyncEventsApi.isPending,
      },
      errors: {
        gateway: liveGatewayQ.error,
        account: liveAccountQ.error,
        positions: livePositionsQ.error,
        orders: liveOrdersQ.error,
        fills: liveFillsQ.error,
        orderStatus: liveOrderStatusQ.error,
        receipt: liveReceiptQ.error,
        events: liveOrderEventsQ.error,
        form: liveFormError,
        submit: liveSubmitApi.error,
        cancel: liveCancelApi.error,
        mirror: liveMirrorApi.error,
        sync: liveSyncEventsApi.error,
      },
      onRefresh: () => void refreshLiveGateway(),
      onSymbolChange: setLiveSymbol,
      onSideChange: setLiveSide,
      onQtyChange: setLiveQty,
      onOrderTypeChange: setLiveOrderType,
      onLiveOrdersStatusChange: setLiveOrdersStatus,
      onLimitPriceChange: setLiveLimitPrice,
      onStopPriceChange: setLiveStopPrice,
      onDryRunChange: setLiveDryRun,
      onMirrorExecuteChange: setLiveMirrorExecute,
      onOrderIdInputChange: setLiveOrderIdInput,
      onSubmitOrder: () => void handleLiveSubmitOrder(),
      onMirrorToPaper: () => void handleLiveMirrorToPaper(),
      onOrderQuery: handleLiveOrderQuery,
      onCancelOrder: () => void handleLiveCancelOrder(),
      onSelectLiveOrder: (row) => {
        void handleSelectLiveOrder(row);
      },
      onSyncEvents: () => void handleLiveSyncEvents(),
    },
  };
}
