'use client';

import { FormEvent, useEffect, useMemo, useRef, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import WorkspaceSplitLayout from '@/components/workspace-split-layout';
import WorkspaceToolbar from '@/components/workspace-toolbar';
import { PageContainer, SectionCard, KpiCard, KpiGrid, StockCodeInput, DataTable, Badge } from '@/components/ui';
import { useApiMutation } from '@/hooks/use-api-mutation';
import { useApiQuery } from '@/hooks/use-api-query';
import { useStockCode } from '@/hooks/use-stock-code';
import { usePageActions } from '@/hooks/use-page-actions';
import { usePageContext } from '@/hooks/use-page-context';
import { extractArray, fmtNum } from '@/lib/data-utils';
import { selectActiveWorkspace, useWorkbenchStore } from '@/store/workbench-store';
import type {
  ExecutionArtifactResponse,
  ExecutionTaskDetailResponse,
  ExecutionTasksResponse,
  ExecutionWorkbenchResponse,
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
  PaperTradingAccountsResponse,
  PaperTradingPendingOrdersResponse,
  PaperTradingRouteExecutionInput,
} from '@aiask/shared-types';

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === 'object' && !Array.isArray(value) ? (value as Record<string, unknown>) : {};
}

function toFiniteNumber(value: unknown): number | null {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function briefDateTime(value: unknown): string {
  const text = String(value ?? '').trim();
  return text ? text.slice(0, 19).replace('T', ' ') : '-';
}

function findExecutionId(payload: unknown): string {
  if (!payload || typeof payload !== 'object') return '';
  const root = payload as Record<string, unknown>;
  const candidates = [
    root.execution_id,
    root.executionId,
    root.task_id,
    root.taskId,
    root.id,
    (root.execution as Record<string, unknown> | undefined)?.task_id,
    (root.execution as Record<string, unknown> | undefined)?.taskId,
    (root.execution as Record<string, unknown> | undefined)?.execution_id,
    (root.execution as Record<string, unknown> | undefined)?.executionId,
    (root.execution as Record<string, unknown> | undefined)?.id,
  ];
  const hit =
    candidates.find((item) => typeof item === 'string' && item.trim()) ??
    candidates.find((item) => typeof item === 'number');
  return hit == null ? '' : String(hit);
}

function briefSummary(payload: unknown): string {
  if (!payload || typeof payload !== 'object') return '暂无执行返回';
  const record = payload as Record<string, unknown>;
  const parts = [
    record.status ? `状态 ${String(record.status)}` : null,
    record.profile ? `策略 ${String(record.profile)}` : null,
    record.warning_count != null ? `告警 ${String(record.warning_count)}` : null,
    record.has_high_severity != null ? `高严重级 ${record.has_high_severity ? '是' : '否'}` : null,
  ].filter(Boolean);
  return parts.length ? parts.join(' · ') : '已生成执行结果';
}

function isTransientMutationError(error: unknown): boolean {
  const message = error instanceof Error ? error.message : String(error ?? '');
  return /failed to fetch|networkerror|load failed/i.test(message);
}

type ExecutionInsight = {
  taskId: string;
  code: string;
  status: string;
  algorithm: string;
  totalShares: number | null;
  durationMinutes: number | null;
  slices: number | null;
  warningCount: number;
  hasHighSeverity: boolean;
  estimatedCostTotal: number | null;
  lifecycleCount: number | null;
  softGateProfile: string;
};

function readExecutionInsight(payload: unknown): ExecutionInsight | null {
  if (!payload || typeof payload !== 'object') return null;

  const root = asRecord(payload);
  const task = asRecord(root.task);
  const plan = asRecord(task.plan);
  const softGate = asRecord(root.soft_gate ?? root.softGate ?? task.soft_gate ?? task.softGate);
  const costModel = asRecord(root.cost_model ?? root.costModel ?? task.cost_model ?? task.costModel);
  const estimated = asRecord(costModel.estimated);
  const warnings = Array.isArray(root.warnings)
    ? root.warnings
    : Array.isArray(task.pretrade_warnings)
      ? task.pretrade_warnings
      : [];
  const warningCount = Number(
    softGate.warning_count ?? softGate.warningCount ?? root.warning_count ?? root.warningCount ?? warnings.length,
  );

  return {
    taskId: findExecutionId(root) || findExecutionId(task),
    code: String(task.code ?? root.code ?? '').trim(),
    status: String(task.status ?? root.status ?? '').trim(),
    algorithm: String(task.algorithm ?? root.algorithm ?? '').trim(),
    totalShares: toFiniteNumber(task.total_shares ?? task.total_quantity ?? root.total_shares ?? root.total_quantity),
    durationMinutes: toFiniteNumber(plan.duration_minutes ?? plan.duration ?? root.duration_minutes ?? root.duration),
    slices: toFiniteNumber(plan.slices ?? root.slices),
    warningCount: Number.isFinite(warningCount) ? warningCount : warnings.length,
    hasHighSeverity: Boolean(
      softGate.has_high_severity ?? softGate.hasHighSeverity ?? root.has_high_severity ?? root.hasHighSeverity,
    ),
    estimatedCostTotal: toFiniteNumber(root.estimated_cost_total ?? root.estimatedCostTotal ?? estimated.total),
    lifecycleCount: toFiniteNumber(
      root.lifecycle_count ?? root.lifecycleCount ?? (Array.isArray(task.lifecycle) ? task.lifecycle.length : null),
    ),
    softGateProfile: String(softGate.profile ?? root.profile ?? '').trim(),
  };
}

export default function ExecutionPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const workbenchHydrated = useWorkbenchStore((state) => state.hydrated);
  const activeWorkspaceId = useWorkbenchStore((state) => state.activeWorkspaceId);
  const workbenchContext = useWorkbenchStore((state) => selectActiveWorkspace(state).context);
  const updateWorkbenchContext = useWorkbenchStore((state) => state.updateContext);
  const addWorkbenchTask = useWorkbenchStore((state) => state.addTask);
  const initialAccountId = searchParams.get('account_id') ?? '';
  const initialExecutionId = searchParams.get('execution_id') ?? '';
  const initialArtifactId = searchParams.get('artifact_id') ?? '';
  const { code, setCode, codeError, validate, trimmedCode } = useStockCode(searchParams.get('code') ?? '600519');
  const [direction, setDirection] = useState<'buy' | 'sell'>('buy');
  const [quantity, setQuantity] = useState('100');
  const [price, setPrice] = useState('');
  const [urgency, setUrgency] = useState<'normal' | 'high'>('normal');
  const [orderType, setOrderType] = useState<'market' | 'limit' | 'stop'>('market');
  const [stopPrice, setStopPrice] = useState('');
  const [accountId, setAccountId] = useState(initialAccountId);
  const [executionIdInput, setExecutionIdInput] = useState(initialExecutionId);
  const [submittedExecutionId, setSubmittedExecutionId] = useState(initialExecutionId);
  const [artifactIdInput, setArtifactIdInput] = useState(initialArtifactId);
  const [submittedArtifactId, setSubmittedArtifactId] = useState(initialArtifactId);
  const [formError, setFormError] = useState<string | null>(null);
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
  const lastWorkspaceIdRef = useRef<string | null>(null);

  const accountsQ = useApiQuery<PaperTradingAccountsResponse | unknown[]>('/paper-trading/accounts');
  const pendingQ = useApiQuery<PaperTradingPendingOrdersResponse>(
    accountId
      ? `/paper-trading/pending-orders?account_id=${encodeURIComponent(accountId)}`
      : '/paper-trading/pending-orders',
  );
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
  const routeExecutionApi = useApiMutation<Record<string, unknown>>();
  const workbenchPath = useMemo(() => {
    const params = new URLSearchParams();
    if (submittedExecutionId) return null;
    if (accountId) params.set('accountId', accountId);
    return params.toString() ? `/execution/workbench?${params.toString()}` : null;
  }, [accountId, submittedExecutionId]);
  const executionWorkbenchQ = useApiQuery<ExecutionWorkbenchResponse>(workbenchPath);
  const tasksQ = useApiQuery<ExecutionTasksResponse>('/execution/tasks');
  const taskDetailPath = useMemo(() => {
    const taskId = (submittedExecutionId || '').trim();
    if (!taskId) return null;
    const params = new URLSearchParams();
    if (accountId) params.set('accountId', accountId);
    return `/execution/tasks/${encodeURIComponent(taskId)}${params.toString() ? `?${params.toString()}` : ''}`;
  }, [accountId, submittedExecutionId]);
  const taskDetailQ = useApiQuery<ExecutionTaskDetailResponse>(taskDetailPath);
  const artifactPath = useMemo(() => {
    const artifactId = (submittedArtifactId || '').trim();
    if (!artifactId) return null;
    const params = new URLSearchParams();
    if (accountId) params.set('accountId', accountId);
    return `/execution/artifact/${encodeURIComponent(artifactId)}${params.toString() ? `?${params.toString()}` : ''}`;
  }, [accountId, submittedArtifactId]);
  const artifactQ = useApiQuery<ExecutionArtifactResponse>(artifactPath);

  const accounts = useMemo(
    () => extractArray(accountsQ.data, 'accounts', 'items', 'data') as Array<{ account_id?: string }>,
    [accountsQ.data],
  );
  const pendingOrders = useMemo(() => pendingQ.data?.orders ?? [], [pendingQ.data]);
  const latestExecution = routeExecutionApi.data ?? null;
  const currentExecutionId = useMemo(
    () => findExecutionId(latestExecution) || submittedExecutionId,
    [latestExecution, submittedExecutionId],
  );
  const currentArtifactId = useMemo(() => {
    const latestPayload = asRecord(latestExecution);
    const executionPayload = asRecord(latestPayload.execution ?? latestPayload);
    const candidates = [
      executionPayload.artifact_id,
      executionPayload.artifactId,
      latestPayload.artifact_id,
      latestPayload.artifactId,
      taskDetailQ.data?.artifactId,
      taskDetailQ.data?.overview?.artifactId,
      artifactQ.data?.artifactId,
      submittedArtifactId,
    ];
    const hit = candidates.find((item) => typeof item === 'string' && item.trim());
    return hit == null ? '' : String(hit);
  }, [
    artifactQ.data?.artifactId,
    latestExecution,
    submittedArtifactId,
    taskDetailQ.data?.artifactId,
    taskDetailQ.data?.overview?.artifactId,
  ]);
  const quantityValue = Number.parseInt(quantity, 10);
  const unitPrice = orderType === 'stop' ? Number(stopPrice || 0) : Number(price || 0);
  const estimatedAmount =
    Number.isFinite(quantityValue) && quantityValue > 0 && unitPrice > 0 ? quantityValue * unitPrice : null;
  const executionWorkbench = taskDetailQ.data ?? executionWorkbenchQ.data;
  const statusPayload =
    executionWorkbench?.result && typeof executionWorkbench.result === 'object'
      ? asRecord((executionWorkbench.result as Record<string, unknown>).execution)
      : null;
  const executionInsight = useMemo(() => {
    if (executionWorkbench?.overview) {
      return {
        taskId: executionWorkbench.overview.executionId ?? '',
        code: executionWorkbench.overview.code ?? '',
        status: executionWorkbench.overview.status ?? '',
        algorithm: executionWorkbench.overview.algorithm ?? '',
        totalShares: executionWorkbench.overview.totalShares ?? null,
        durationMinutes: executionWorkbench.overview.durationMinutes ?? null,
        slices: executionWorkbench.overview.slices ?? null,
        warningCount: executionWorkbench.overview.warningCount ?? executionWorkbench.warnings?.length ?? 0,
        hasHighSeverity: executionWorkbench.overview.hasHighSeverity ?? false,
        estimatedCostTotal: executionWorkbench.cost?.estimatedTotal ?? null,
        lifecycleCount: executionWorkbench.overview.lifecycleCount ?? null,
        softGateProfile: executionWorkbench.overview.softGateProfile ?? '',
      };
    }
    if (statusPayload && Object.keys(statusPayload).length > 0) return readExecutionInsight(statusPayload);
    const latestPayload = asRecord(latestExecution);
    return readExecutionInsight(latestPayload.execution ?? latestPayload);
  }, [executionWorkbench, latestExecution, statusPayload]);
  const activeExecutionCode = executionInsight?.code || trimmedCode;
  const workbenchWarnings = executionWorkbench?.warnings ?? [];
  const workbenchOrders = executionWorkbench?.orderContext?.recentOrders ?? [];
  const workbenchMessage = executionWorkbench?.message ?? null;
  const executionTasks = tasksQ.data?.tasks ?? [];
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
  const reviewParams = new URLSearchParams();
  reviewParams.set('mode', 'account');
  reviewParams.set('days', '30');
  if (accountId) reviewParams.set('account_id', accountId);
  if (executionInsight?.taskId) reviewParams.set('execution_id', executionInsight.taskId);
  const reviewHref = `/performance?${reviewParams.toString()}`;

  const riskParams = new URLSearchParams();
  riskParams.set('lookbackDays', '30');
  if (accountId) riskParams.set('account_id', accountId);
  const riskHref = `/risk?${riskParams.toString()}`;

  const artifactDetailParams = new URLSearchParams();
  if (accountId) artifactDetailParams.set('account_id', accountId);
  const artifactDetailHref = currentArtifactId
    ? `/execution/artifacts/${encodeURIComponent(currentArtifactId)}${artifactDetailParams.toString() ? `?${artifactDetailParams.toString()}` : ''}`
    : '';

  const executionGuidance = (() => {
    if (!executionInsight) {
      return [
        '先提交一笔执行任务，系统才会形成可复盘的执行摘要。',
        '如果已有 execution_id，可直接查询状态并进入绩效中心做后续复盘。',
      ];
    }

    const notes = [
      executionInsight.hasHighSeverity
        ? '存在高严重级软闸门告警，建议优先去风险中心核查约束。'
        : '当前执行未触发高严重级软闸门告警，可继续做收益与风险联动复盘。',
      executionInsight.warningCount > 0
        ? `本次执行共有 ${executionInsight.warningCount} 条执行告警，适合结合绩效中心检查成本与收益是否匹配。`
        : '本次执行未出现显式告警，建议直接进入绩效中心观察执行后收益表现。',
    ];

    if (executionInsight.estimatedCostTotal != null) {
      notes.push(
        `当前预估执行成本约 ${fmtNum(executionInsight.estimatedCostTotal)}，复盘时要重点核对收益是否覆盖冲击成本。`,
      );
    }

    if (executionWorkbench?.nextActions?.length) {
      notes.push(...executionWorkbench.nextActions.slice(0, 2).map((item) => item.reason));
    }

    return notes;
  })();

  const heroPrimaryButtonCls =
    'inline-flex cursor-pointer items-center justify-center rounded-full bg-primary px-4 py-2 text-sm font-medium text-white shadow-[0_20px_40px_-24px_rgba(11,107,203,0.52)] transition hover:-translate-y-0.5 hover:shadow-[0_24px_46px_-24px_rgba(11,107,203,0.58)] disabled:cursor-not-allowed disabled:opacity-50';
  const heroSecondaryButtonCls =
    'action-chip cursor-pointer text-sm text-text-primary shadow-[0_16px_32px_-24px_rgba(15,23,42,0.28)]';
  const chipButtonCls = 'action-chip cursor-pointer text-xs text-text-primary';
  const noteCardCls = 'metric-tile rounded-[22px] p-3 text-xs text-text-secondary';
  const sidePanelCls = 'panel-soft rounded-[28px] p-4 sm:p-5';

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

  useEffect(() => {
    if (!workbenchHydrated) return;

    const workspaceChanged = lastWorkspaceIdRef.current !== activeWorkspaceId;
    lastWorkspaceIdRef.current = activeWorkspaceId;
    if (!workspaceChanged && searchParams.toString()) return;

    queueMicrotask(() => {
      if (workbenchContext.stockCode) setCode(workbenchContext.stockCode);
      if (workbenchContext.accountId) setAccountId(workbenchContext.accountId);
      if (workbenchContext.executionId) {
        setExecutionIdInput(workbenchContext.executionId);
        setSubmittedExecutionId(workbenchContext.executionId);
      }
      if (workbenchContext.artifactId) {
        setArtifactIdInput(workbenchContext.artifactId);
        setSubmittedArtifactId(workbenchContext.artifactId);
      }
    });
  }, [activeWorkspaceId, searchParams, setCode, workbenchContext, workbenchHydrated]);

  useEffect(() => {
    if (!workbenchHydrated) return;
    updateWorkbenchContext({
      stockCode: activeExecutionCode || null,
      accountId: accountId || null,
      executionId: currentExecutionId || null,
      artifactId: currentArtifactId || null,
    });
  }, [
    accountId,
    activeExecutionCode,
    currentArtifactId,
    currentExecutionId,
    updateWorkbenchContext,
    workbenchHydrated,
  ]);

  useEffect(() => {
    const params = new URLSearchParams(searchParams.toString());
    if (trimmedCode) params.set('code', trimmedCode);
    else params.delete('code');
    if (accountId) params.set('account_id', accountId);
    else params.delete('account_id');
    const nextExecutionId = currentExecutionId || executionIdInput.trim();
    if (nextExecutionId) params.set('execution_id', nextExecutionId);
    else params.delete('execution_id');
    const nextArtifactId = currentArtifactId || artifactIdInput.trim();
    if (nextArtifactId) params.set('artifact_id', nextArtifactId);
    else params.delete('artifact_id');

    const nextQs = params.toString();
    if (nextQs !== searchParams.toString()) {
      router.replace(`/execution${nextQs ? `?${nextQs}` : ''}`, { scroll: false });
    }
  }, [
    accountId,
    artifactIdInput,
    currentArtifactId,
    currentExecutionId,
    executionIdInput,
    router,
    searchParams,
    trimmedCode,
  ]);

  async function handleRouteExecution(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setFormError(null);
    if (!validate()) return;
    if (!Number.isFinite(quantityValue) || quantityValue <= 0) {
      setFormError('数量必须为正整数');
      return;
    }
    if (orderType === 'limit' && !(Number(price) > 0)) {
      setFormError('限价单必须填写有效价格');
      return;
    }
    if (orderType === 'stop' && !(Number(stopPrice) > 0)) {
      setFormError('止损单必须填写有效止损价');
      return;
    }

    const body: PaperTradingRouteExecutionInput = {
      code: trimmedCode,
      direction,
      quantity: quantityValue,
      urgency,
      order_type: orderType,
      account_id: accountId || undefined,
      artifact_id: artifactIdInput.trim() || undefined,
    };
    if (price && Number(price) > 0) body.price = Number(price);
    if (stopPrice && Number(stopPrice) > 0) body.stop_price = Number(stopPrice);

    let result: Record<string, unknown> | null = null;
    for (let attempt = 0; attempt < 2; attempt += 1) {
      try {
        result = await routeExecutionApi.triggerAsync('/paper-trading/route-execution', { method: 'POST' }, body);
        break;
      } catch (error) {
        if (attempt === 1 || !isTransientMutationError(error)) {
          return;
        }
        await new Promise((resolve) => setTimeout(resolve, 800));
      }
    }
    if (!result) return;

    const nextExecutionId = findExecutionId(result);
    const nextArtifactId = String(
      asRecord(asRecord(result).execution ?? result).artifact_id ??
        asRecord(asRecord(result).execution ?? result).artifactId ??
        '',
    ).trim();
    if (nextExecutionId) {
      setExecutionIdInput(nextExecutionId);
      setSubmittedExecutionId(nextExecutionId);
    }
    if (nextArtifactId) {
      setArtifactIdInput(nextArtifactId);
      setSubmittedArtifactId(nextArtifactId);
    }
  }

  function handleStatusQuery(event?: FormEvent<HTMLFormElement>) {
    event?.preventDefault();
    const nextId = executionIdInput.trim();
    if (!nextId) {
      setFormError('请输入 execution_id');
      return;
    }
    setFormError(null);
    setSubmittedExecutionId(nextId);
  }

  function handleArtifactQuery(event?: FormEvent<HTMLFormElement>) {
    event?.preventDefault();
    const nextId = artifactIdInput.trim();
    if (!nextId) {
      setFormError('请输入 artifact_id');
      return;
    }
    setFormError(null);
    setSubmittedArtifactId(nextId);
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

  function loadExample(nextCode: string) {
    setCode(nextCode);
    setDirection('buy');
    setQuantity('100');
    setOrderType('market');
    setPrice('');
    setStopPrice('');
    setUrgency('normal');
    setFormError(null);
  }

  function applyExecutionPayload(payload?: Record<string, unknown>) {
    if (!payload) {
      return { message: '未提供可更新的执行参数' };
    }

    const nextCode = typeof payload.code === 'string' ? payload.code.trim() : '';
    if (nextCode) {
      setCode(nextCode);
    }

    const nextDirection = payload.direction === 'buy' || payload.direction === 'sell' ? payload.direction : null;
    if (nextDirection) {
      setDirection(nextDirection);
    }

    const nextQuantity = toFiniteNumber(payload.quantity);
    if (nextQuantity != null && nextQuantity > 0) {
      setQuantity(String(Math.trunc(nextQuantity)));
    }

    const nextUrgency = payload.urgency === 'high' || payload.urgency === 'normal' ? payload.urgency : null;
    if (nextUrgency) {
      setUrgency(nextUrgency);
    }

    const nextOrderType =
      payload.orderType === 'market' || payload.orderType === 'limit' || payload.orderType === 'stop'
        ? payload.orderType
        : payload.order_type === 'market' || payload.order_type === 'limit' || payload.order_type === 'stop'
          ? payload.order_type
          : null;
    if (nextOrderType) {
      setOrderType(nextOrderType);
    }

    const nextPrice = toFiniteNumber(payload.price);
    if (nextPrice != null && nextPrice > 0) {
      setPrice(String(nextPrice));
    }

    const nextStopPrice = toFiniteNumber(payload.stopPrice ?? payload.stop_price);
    if (nextStopPrice != null && nextStopPrice > 0) {
      setStopPrice(String(nextStopPrice));
    }

    const nextAccountId =
      typeof payload.accountId === 'string'
        ? payload.accountId.trim()
        : typeof payload.account_id === 'string'
          ? payload.account_id.trim()
          : '';
    if (nextAccountId) {
      setAccountId(nextAccountId);
    }

    const nextExecutionId =
      typeof payload.executionId === 'string'
        ? payload.executionId.trim()
        : typeof payload.execution_id === 'string'
          ? payload.execution_id.trim()
          : '';
    if (nextExecutionId) {
      setExecutionIdInput(nextExecutionId);
      setSubmittedExecutionId(nextExecutionId);
    }

    const nextArtifactId =
      typeof payload.artifactId === 'string'
        ? payload.artifactId.trim()
        : typeof payload.artifact_id === 'string'
          ? payload.artifact_id.trim()
          : '';
    if (nextArtifactId) {
      setArtifactIdInput(nextArtifactId);
      setSubmittedArtifactId(nextArtifactId);
    }

    setFormError(null);
    return {
      message: `已更新执行参数${nextCode ? `，标的 ${nextCode}` : ''}${nextDirection ? `，方向 ${nextDirection === 'buy' ? '买入' : '卖出'}` : ''}${nextQuantity != null ? `，数量 ${Math.trunc(nextQuantity)} 股` : ''}${nextArtifactId ? `，artifact ${nextArtifactId}` : ''}`,
    };
  }

  function openPerformanceReview() {
    updateWorkbenchContext({
      stockCode: activeExecutionCode || null,
      accountId: accountId || null,
      executionId: currentExecutionId || null,
      artifactId: currentArtifactId || null,
      mode: 'account',
      days: 30,
    });
    addWorkbenchTask({
      pageKey: 'execution',
      title: currentExecutionId ? `去绩效中心复盘执行 ${currentExecutionId}` : '去绩效中心查看执行后收益',
      href: reviewHref,
      kind: 'performance-review',
      payload: { accountId, executionId: currentExecutionId, artifactId: currentArtifactId },
    });
    router.push(reviewHref);
  }

  function openRiskReview() {
    updateWorkbenchContext({
      stockCode: activeExecutionCode || null,
      accountId: accountId || null,
      executionId: currentExecutionId || null,
      artifactId: currentArtifactId || null,
      lookbackDays: 30,
    });
    addWorkbenchTask({
      pageKey: 'execution',
      title: currentExecutionId ? `去风险中心复盘执行 ${currentExecutionId}` : '去风险中心核查执行风险',
      href: riskHref,
      kind: 'risk-review',
      payload: { accountId, executionId: currentExecutionId, artifactId: currentArtifactId },
    });
    router.push(riskHref);
  }

  function openStockDetail(nextCode = activeExecutionCode) {
    if (!nextCode) {
      throw new Error('当前没有可打开的股票代码');
    }
    updateWorkbenchContext({ stockCode: nextCode });
    addWorkbenchTask({
      pageKey: 'execution',
      title: `查看 ${nextCode} 个股详情`,
      href: `/stock?code=${encodeURIComponent(nextCode)}`,
      kind: 'stock-review',
      payload: { code: nextCode },
    });
    router.push(`/stock?code=${encodeURIComponent(nextCode)}`);
  }

  function openArtifactDetail(nextArtifactId = currentArtifactId) {
    if (!nextArtifactId) {
      throw new Error('当前没有可打开的 artifact');
    }
    const params = new URLSearchParams();
    if (accountId) params.set('account_id', accountId);
    const href = `/execution/artifacts/${encodeURIComponent(nextArtifactId)}${params.toString() ? `?${params.toString()}` : ''}`;
    updateWorkbenchContext({
      stockCode: activeExecutionCode || null,
      accountId: accountId || null,
      executionId: currentExecutionId || null,
      artifactId: nextArtifactId,
    });
    addWorkbenchTask({
      pageKey: 'execution',
      title: `查看 artifact ${nextArtifactId}`,
      href,
      kind: 'artifact-review',
      payload: { accountId, executionId: currentExecutionId, artifactId: nextArtifactId },
    });
    router.push(href);
  }

  const currentView = useMemo(
    () => ({
      code: trimmedCode,
      direction,
      quantity,
      urgency,
      orderType,
      price,
      stopPrice,
      accountId,
      executionId: executionIdInput,
      artifactId: artifactIdInput,
    }),
    [
      accountId,
      artifactIdInput,
      direction,
      executionIdInput,
      orderType,
      price,
      quantity,
      stopPrice,
      trimmedCode,
      urgency,
    ],
  );

  usePageContext({
    pageKey: 'execution',
    title: '执行中心',
    summary: `当前执行标的为 ${trimmedCode || '未输入'}，方向 ${direction === 'buy' ? '买入' : '卖出'}，数量 ${quantity || '未输入'} 股，执行模式 ${urgency === 'high' ? '高优先级 VWAP' : '标准 TWAP'}。当前执行单号 ${currentExecutionId || '未查询'}。`,
    stockCode: trimmedCode || undefined,
    tags: [
      urgency === 'high' ? '高优先级' : '标准执行',
      orderType === 'market' ? '市价单' : orderType === 'limit' ? '限价单' : '止损单',
      `${pendingOrders.length} 挂单`,
    ],
    suggestions: [
      '载入一笔示例执行参数',
      urgency === 'high' ? '切回标准执行模式' : '切换到高优先级执行',
      executionInsight ? '打开执行复盘摘要并继续联动' : '查询最新执行状态',
    ],
    raw: {
      code: trimmedCode,
      direction,
      quantity: quantityValue,
      urgency,
      orderType,
      executionId: currentExecutionId || null,
      pendingOrders: pendingOrders.length,
    },
  });

  const pageActions = [
    {
      id: 'execution.load-example',
      label: '载入茅台执行示例',
      description: '填充 600519 的执行参数',
      keywords: ['示例', '执行', '600519'],
      scope: 'page' as const,
      pageKey: 'execution',
      run: () => {
        loadExample('600519');
        return { message: '已载入 600519 执行示例' };
      },
    },
    {
      id: 'execution.update-form',
      label: '更新执行参数',
      description:
        '支持 payload: code, direction, quantity, urgency, orderType, price, stopPrice, accountId, executionId, artifactId，用于让 Copilot 直接改中间执行表单。',
      keywords: ['更新参数', '表单联动', 'payload'],
      scope: 'page' as const,
      pageKey: 'execution',
      run: (payload: Record<string, unknown> | undefined) => applyExecutionPayload(payload),
    },
    {
      id: 'execution.toggle-urgency',
      label: urgency === 'high' ? '切换为标准执行' : '切换为高优先级执行',
      description: '切换 TWAP / VWAP 执行偏好',
      keywords: ['TWAP', 'VWAP', '优先级'],
      scope: 'page' as const,
      pageKey: 'execution',
      run: () => {
        setUrgency((prev) => (prev === 'high' ? 'normal' : 'high'));
        return { message: urgency === 'high' ? '已切换为标准执行' : '已切换为高优先级执行' };
      },
    },
    {
      id: 'execution.query-status',
      label: '查询执行状态',
      description: '按当前 execution_id 查询执行状态',
      keywords: ['查询状态', 'execution_id'],
      scope: 'page' as const,
      pageKey: 'execution',
      run: () => {
        handleStatusQuery();
        return { message: '已查询执行状态' };
      },
    },
    {
      id: 'execution.open-paper',
      label: '打开模拟交易',
      description: '回到模拟交易页查看订单与持仓',
      keywords: ['模拟交易', '订单'],
      scope: 'page' as const,
      pageKey: 'execution',
      run: () => {
        router.push('/paper-trading');
        return { message: '已打开模拟交易页' };
      },
    },
    {
      id: 'execution.open-performance',
      label: '打开绩效中心',
      description: '进入绩效中心查看执行后收益表现',
      keywords: ['绩效中心', '收益'],
      scope: 'page' as const,
      pageKey: 'execution',
      run: () => {
        openPerformanceReview();
        return { message: '已打开绩效中心' };
      },
    },
    {
      id: 'execution.open-risk',
      label: '打开风险中心',
      description: '支持 payload: lookbackDays, accountId。用于从执行结果继续核查风险暴露与异常来源。',
      keywords: ['风险中心', '风险复盘'],
      scope: 'page' as const,
      pageKey: 'execution',
      run: (payload: Record<string, unknown> | undefined) => {
        const nextLookback = String(Math.max(30, Number(payload?.lookbackDays ?? 30) || 30));
        const nextAccountId = typeof payload?.accountId === 'string' ? payload.accountId.trim() : accountId;
        updateWorkbenchContext({
          stockCode: activeExecutionCode || null,
          accountId: nextAccountId || null,
          executionId: currentExecutionId || null,
          artifactId: currentArtifactId || null,
          lookbackDays: Number(nextLookback),
        });
        addWorkbenchTask({
          pageKey: 'execution',
          title: currentExecutionId ? `去风险中心复盘执行 ${currentExecutionId}` : '去风险中心核查执行风险',
          href: `/risk?lookbackDays=${encodeURIComponent(nextLookback)}${nextAccountId ? `&account_id=${encodeURIComponent(nextAccountId)}` : ''}`,
          kind: 'risk-review',
          payload: {
            accountId: nextAccountId,
            executionId: currentExecutionId,
            artifactId: currentArtifactId,
            lookbackDays: Number(nextLookback),
          },
        });
        router.push(
          `/risk?lookbackDays=${encodeURIComponent(nextLookback)}${nextAccountId ? `&account_id=${encodeURIComponent(nextAccountId)}` : ''}`,
        );
        return { message: '已打开风险中心' };
      },
    },
    {
      id: 'execution.open-stock',
      label: '打开个股详情',
      description: '支持 payload: code。默认打开当前执行标的的个股详情。',
      keywords: ['个股详情', '标的'],
      scope: 'page' as const,
      pageKey: 'execution',
      run: (payload: Record<string, unknown> | undefined) => {
        const nextCode =
          typeof payload?.code === 'string' && payload.code.trim() ? payload.code.trim() : activeExecutionCode;
        openStockDetail(nextCode);
        return { message: `已打开 ${nextCode} 个股详情` };
      },
    },
    {
      id: 'execution.query-artifact',
      label: '查询 artifact',
      description: '按当前 artifact_id 查询对应执行任务和详情',
      keywords: ['artifact', '任务联动'],
      scope: 'page' as const,
      pageKey: 'execution',
      run: () => {
        handleArtifactQuery();
        return { message: '已查询 artifact' };
      },
    },
    {
      id: 'execution.open-artifact',
      label: '打开 artifact 详情页',
      description: '进入 artifact 独立详情页查看关联任务和执行链路',
      keywords: ['artifact 详情', '任务链路'],
      scope: 'page' as const,
      pageKey: 'execution',
      run: () => {
        openArtifactDetail();
        return { message: `已打开 artifact ${currentArtifactId}` };
      },
    },
  ];

  usePageActions(pageActions);

  return (
    <PageContainer>
      <section className="page-hero p-5 sm:p-6">
        <div className="grid gap-5 xl:grid-cols-[minmax(0,1.2fr)_380px]">
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <Badge variant="info">Execution Workspace</Badge>
              <Badge variant={urgency === 'high' ? 'warning' : 'neutral'}>
                {urgency === 'high' ? '高优先级 VWAP' : '标准 TWAP'}
              </Badge>
              <Badge variant={liveGatewayReady ? 'success' : 'neutral'}>
                {liveGatewayReady ? '真实网关已连接' : '仅工作台 / 模拟链路'}
              </Badge>
            </div>
            <h1 className="mb-0 mt-4 text-[2rem] font-semibold tracking-[-0.03em] text-text-primary sm:text-[2.4rem]">
              执行工作台
            </h1>
            <p className="mb-0 mt-3 max-w-3xl text-sm leading-7 text-text-secondary sm:text-[15px]">
              这里负责把下单参数、执行回执、实时网关和复盘入口收进一个操作面。重点不是替代模拟交易页，而是把一次执行后的状态、告警与后续动作压缩到可连续处理的首屏里。
            </p>
            <div className="mt-5 flex flex-wrap gap-2">
              <button type="button" onClick={() => openPerformanceReview()} className={heroPrimaryButtonCls}>
                去绩效中心复盘
              </button>
              <button type="button" onClick={() => openRiskReview()} className={heroSecondaryButtonCls}>
                去风险中心核查
              </button>
              {activeExecutionCode ? (
                <button
                  type="button"
                  onClick={() => openStockDetail(activeExecutionCode)}
                  className={heroSecondaryButtonCls}
                >
                  打开个股详情
                </button>
              ) : null}
              {currentArtifactId ? (
                <button
                  type="button"
                  onClick={() => openArtifactDetail(currentArtifactId)}
                  className={heroSecondaryButtonCls}
                >
                  查看 Artifact
                </button>
              ) : null}
            </div>

            <div className="mt-5 grid gap-3 sm:grid-cols-4">
              <div className="rounded-[24px] border border-white/45 bg-white/38 p-4 shadow-[inset_0_1px_0_rgba(255,255,255,0.55)]">
                <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">当前标的</div>
                <div className="mt-3 text-2xl font-semibold text-text-primary">{trimmedCode || '-'}</div>
                <div className="mt-1 text-xs text-text-secondary">
                  {direction === 'buy' ? '买入方向' : '卖出方向'} · {quantity || '-'} 股
                </div>
              </div>
              <div className="rounded-[24px] border border-white/45 bg-white/30 p-4 shadow-[inset_0_1px_0_rgba(255,255,255,0.48)]">
                <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">预估成交额</div>
                <div className="mt-3 text-2xl font-semibold text-text-primary">
                  {estimatedAmount != null ? fmtNum(estimatedAmount) : '-'}
                </div>
                <div className="mt-1 text-xs text-text-secondary">
                  {orderType === 'market'
                    ? '市价单以实时价格成交'
                    : orderType === 'limit'
                      ? '按限价约束成交'
                      : '按止损条件触发'}
                </div>
              </div>
              <div className="rounded-[24px] border border-white/45 bg-white/26 p-4 shadow-[inset_0_1px_0_rgba(255,255,255,0.42)]">
                <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">执行单号</div>
                <div className="mt-3 text-2xl font-semibold text-text-primary">{currentExecutionId || '-'}</div>
                <div className="mt-1 text-xs text-text-secondary">
                  {executionInsight?.status ? `状态 ${executionInsight.status}` : '提交后会自动回填执行状态'}
                </div>
              </div>
              <div className="rounded-[24px] border border-white/45 bg-white/24 p-4 shadow-[inset_0_1px_0_rgba(255,255,255,0.38)]">
                <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">软闸门</div>
                <div className="mt-3 text-2xl font-semibold text-text-primary">
                  {executionInsight?.warningCount ?? workbenchWarnings.length}
                </div>
                <div className="mt-1 text-xs text-text-secondary">
                  {executionInsight?.hasHighSeverity ? '存在高严重级告警' : '当前没有高严重级告警'}
                </div>
              </div>
            </div>
          </div>

          <div className="grid gap-3">
            <div className={sidePanelCls}>
              <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">当前执行摘要</div>
              <div className="mt-3 text-base font-semibold text-text-primary">
                {executionInsight
                  ? briefSummary(executionWorkbench?.result ?? latestExecution ?? executionInsight)
                  : '尚未形成执行结果'}
              </div>
              <div className="mt-4 grid gap-3 sm:grid-cols-3 xl:grid-cols-1">
                <div className={noteCardCls}>
                  挂单数量：<span className="font-medium text-text-primary">{pendingOrders.length}</span>
                </div>
                <div className={noteCardCls}>
                  最近 Artifact：<span className="font-medium text-text-primary">{currentArtifactId || '-'}</span>
                </div>
                <div className={noteCardCls}>
                  真实订单 / 成交：
                  <span className="font-medium text-text-primary">
                    {liveOrders.length} / {liveFills.length}
                  </span>
                </div>
              </div>
            </div>

            <div className={sidePanelCls}>
              <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">复盘建议</div>
              <div className="mt-4 space-y-3">
                {executionGuidance.slice(0, 3).map((item) => (
                  <div key={item} className={noteCardCls}>
                    {item}
                  </div>
                ))}
              </div>
              <div className="mt-3 flex flex-wrap gap-2">
                <button type="button" onClick={() => handleStatusQuery()} className={chipButtonCls}>
                  查询执行状态
                </button>
                <button type="button" onClick={() => void refreshLiveGateway()} className={chipButtonCls}>
                  刷新网关
                </button>
              </div>
            </div>
          </div>
        </div>
      </section>

      <WorkspaceToolbar
        pageKey="execution"
        currentView={currentView}
        onApplyView={(snapshot) => {
          applyExecutionPayload(snapshot);
        }}
        supportsPagePanels
      />

      <KpiGrid cols={5} className="mb-4">
        <KpiCard title="当前标的" value={trimmedCode || '-'} />
        <KpiCard title="执行模式" value={urgency === 'high' ? '高优先级 VWAP' : '标准 TWAP'} />
        <KpiCard title="挂单数量" value={pendingOrders.length} />
        <KpiCard title="执行单号" value={currentExecutionId || '-'} />
        <KpiCard title="Artifact" value={currentArtifactId || '-'} />
      </KpiGrid>

      <WorkspaceSplitLayout
        pageKey="execution"
        primary={
          <div className="space-y-4 xl:h-full xl:overflow-y-auto xl:pr-1">
            <SectionCard className="mb-4">
              <div className="flex items-center justify-between gap-3 flex-wrap">
                <div>
                  <h3 className="m-0 font-medium">Live Gateway</h3>
                  <p className="mb-0 mt-1 text-xs text-text-secondary">
                    当前产品侧已接入真实券商网关主入口。默认只读预览，只有在网关显式开启写权限时才会真正下单或撤单。
                  </p>
                </div>
                <button type="button" onClick={() => void refreshLiveGateway()} className={chipButtonCls}>
                  {liveGatewayQ.isFetching ||
                  liveAccountQ.isFetching ||
                  livePositionsQ.isFetching ||
                  liveOrdersQ.isFetching ||
                  liveFillsQ.isFetching
                    ? '刷新中...'
                    : '刷新网关'}
                </button>
              </div>

              <KpiGrid cols={6} className="mt-4">
                <KpiCard title="Provider" value={liveGateway?.provider || '-'} />
                <KpiCard title="配置状态" value={liveGateway?.configured ? '已配置' : '未配置'} />
                <KpiCard title="连接状态" value={liveGateway?.connected ? '已连接' : '未连接'} />
                <KpiCard title="模式" value={liveGateway?.read_only ? '只读/预览' : '可写'} />
                <KpiCard title="真实订单" value={liveOrders.length} />
                <KpiCard title="成交回报" value={liveFills.length} />
              </KpiGrid>

              <div className="mt-4 grid gap-4 2xl:grid-cols-[minmax(0,1.15fr)_minmax(320px,0.85fr)]">
                <div className="panel-soft rounded-[24px] p-4">
                  <div className="text-sm font-medium text-text-primary">网关状态与账户</div>
                  <div className="mt-2 grid gap-2 text-xs text-text-secondary sm:grid-cols-2">
                    <div>Base URL：{liveGateway?.base_url || '-'}</div>
                    <div>Paper：{liveGateway?.paper ? '是' : '否'}</div>
                    <div>账户：{liveAccount?.account_id || '-'}</div>
                    <div>状态：{liveAccount?.status || '-'}</div>
                    <div>现金：{liveAccount?.cash != null ? fmtNum(liveAccount.cash) : '-'}</div>
                    <div>净值：{liveAccount?.portfolio_value != null ? fmtNum(liveAccount.portfolio_value) : '-'}</div>
                  </div>
                  {liveGateway?.error ? <p className="mt-3 mb-0 text-xs text-danger">{liveGateway.error}</p> : null}
                  {liveAccountQ.error ? <p className="mt-2 mb-0 text-xs text-danger">{liveAccountQ.error}</p> : null}
                </div>

                <div className="panel-soft rounded-[26px] p-4 sm:p-5">
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div>
                      <div className="text-sm font-medium text-text-primary">真实订单预览 / 提交</div>
                      <p className="mb-0 mt-2 text-xs leading-6 text-text-secondary">
                        把真实网关的订单参数、dry-run 和镜像动作收在一块更松弛的 glass 表单里，减少“配置区 +
                        结果区”割裂感。
                      </p>
                    </div>
                    <Badge variant={liveDryRun ? 'info' : 'warning'}>
                      {liveDryRun ? '当前为预览模式' : '当前允许真实动作'}
                    </Badge>
                  </div>
                  <div className="mt-4 grid gap-3 md:grid-cols-2">
                    <label className="flex flex-col gap-2 text-xs text-text-secondary">
                      <span>标的</span>
                      <input
                        value={liveSymbol}
                        onChange={(event) => setLiveSymbol(event.target.value)}
                        className="text-sm"
                      />
                    </label>
                    <label className="flex flex-col gap-2 text-xs text-text-secondary">
                      <span>方向</span>
                      <select
                        value={liveSide}
                        onChange={(event) => setLiveSide(event.target.value as 'buy' | 'sell')}
                        className="text-sm"
                      >
                        <option value="buy">buy</option>
                        <option value="sell">sell</option>
                      </select>
                    </label>
                    <label className="flex flex-col gap-2 text-xs text-text-secondary">
                      <span>数量</span>
                      <input
                        type="number"
                        min={1}
                        value={liveQty}
                        onChange={(event) => setLiveQty(event.target.value)}
                        className="text-sm"
                      />
                    </label>
                    <label className="flex flex-col gap-2 text-xs text-text-secondary">
                      <span>订单类型</span>
                      <select
                        value={liveOrderType}
                        onChange={(event) => setLiveOrderType(event.target.value as 'market' | 'limit' | 'stop')}
                        className="text-sm"
                      >
                        <option value="market">market</option>
                        <option value="limit">limit</option>
                        <option value="stop">stop</option>
                      </select>
                    </label>
                    {liveOrderType === 'limit' ? (
                      <label className="flex flex-col gap-2 text-xs text-text-secondary">
                        <span>Limit Price</span>
                        <input
                          type="number"
                          step="0.01"
                          value={liveLimitPrice}
                          onChange={(event) => setLiveLimitPrice(event.target.value)}
                          className="text-sm"
                        />
                      </label>
                    ) : null}
                    {liveOrderType === 'stop' ? (
                      <label className="flex flex-col gap-2 text-xs text-text-secondary">
                        <span>Stop Price</span>
                        <input
                          type="number"
                          step="0.01"
                          value={liveStopPrice}
                          onChange={(event) => setLiveStopPrice(event.target.value)}
                          className="text-sm"
                        />
                      </label>
                    ) : null}
                  </div>
                  <div className="mt-4 grid gap-3 sm:grid-cols-2">
                    <label className={`${noteCardCls} flex items-center gap-2`}>
                      <input
                        type="checkbox"
                        checked={liveDryRun}
                        onChange={(event) => setLiveDryRun(event.target.checked)}
                      />
                      dry_run / 预览模式
                    </label>
                    <label className={`${noteCardCls} flex items-center gap-2`}>
                      <input
                        type="checkbox"
                        checked={liveMirrorExecute}
                        onChange={(event) => setLiveMirrorExecute(event.target.checked)}
                      />
                      mirror 执行到 paper
                    </label>
                  </div>
                  <div className="mt-3 flex flex-wrap gap-2">
                    <button
                      type="button"
                      onClick={() => void handleLiveSubmitOrder()}
                      disabled={liveSubmitApi.isPending}
                      className={heroPrimaryButtonCls}
                    >
                      {liveSubmitApi.isPending ? '处理中...' : '预览 / 提交订单'}
                    </button>
                    <button
                      type="button"
                      onClick={() => void handleLiveMirrorToPaper()}
                      disabled={liveMirrorApi.isPending}
                      className={chipButtonCls}
                    >
                      {liveMirrorApi.isPending ? '镜像中...' : '镜像到 Paper'}
                    </button>
                  </div>
                  <form onSubmit={handleLiveOrderQuery} className="mt-3 flex flex-wrap items-end gap-2">
                    <label className="flex min-w-[220px] flex-1 flex-col gap-2 text-xs text-text-secondary">
                      <span>order_id</span>
                      <input
                        value={liveOrderIdInput}
                        onChange={(event) => setLiveOrderIdInput(event.target.value)}
                        className="text-sm"
                      />
                    </label>
                    <button type="submit" className={chipButtonCls}>
                      查询订单
                    </button>
                    <button
                      type="button"
                      onClick={() => void handleLiveCancelOrder()}
                      disabled={liveCancelApi.isPending}
                      className={chipButtonCls}
                    >
                      {liveCancelApi.isPending ? '处理中...' : '预览 / 撤单'}
                    </button>
                  </form>
                  {liveFormError ? <p className="mt-2 mb-0 text-xs text-danger">{liveFormError}</p> : null}
                  {liveSubmitApi.error ? <p className="mt-2 mb-0 text-xs text-danger">{liveSubmitApi.error}</p> : null}
                  {liveCancelApi.error ? <p className="mt-2 mb-0 text-xs text-danger">{liveCancelApi.error}</p> : null}
                  {liveMirrorApi.error ? <p className="mt-2 mb-0 text-xs text-danger">{liveMirrorApi.error}</p> : null}
                  {liveSyncEventsApi.error ? (
                    <p className="mt-2 mb-0 text-xs text-danger">{liveSyncEventsApi.error}</p>
                  ) : null}
                </div>
              </div>

              <div className="mt-4 grid gap-4 2xl:grid-cols-2">
                <div>
                  <div className="mb-2 flex items-center justify-between gap-2">
                    <div className="text-sm font-medium text-text-primary">真实持仓</div>
                    <Badge variant={liveGatewayReady ? 'success' : 'neutral'}>
                      {liveGatewayReady ? `${livePositions.length} 条` : '网关未就绪'}
                    </Badge>
                  </div>
                  <DataTable
                    rows={livePositions as unknown as Record<string, unknown>[]}
                    emptyText="暂无真实持仓"
                    columns={[
                      { key: 'symbol', label: '标的' },
                      { key: 'side', label: '方向' },
                      { key: 'qty', label: '数量' },
                      {
                        key: 'avg_entry_price',
                        label: '成本价',
                        render: (value: unknown) => (value == null ? '-' : fmtNum(Number(value), 2)),
                      },
                      {
                        key: 'market_value',
                        label: '市值',
                        render: (value: unknown) => (value == null ? '-' : fmtNum(Number(value), 2)),
                      },
                    ]}
                  />
                  {livePositionsQ.error ? (
                    <p className="mt-2 mb-0 text-xs text-danger">{livePositionsQ.error}</p>
                  ) : null}
                </div>
                <div>
                  <div className="mb-2 flex items-center justify-between gap-2">
                    <div className="flex items-center gap-2">
                      <div className="text-sm font-medium text-text-primary">真实订单</div>
                      <select
                        value={liveOrdersStatus}
                        onChange={(event) => setLiveOrdersStatus(event.target.value)}
                        className="w-auto min-w-[92px] text-xs"
                      >
                        <option value="open">open</option>
                        <option value="closed">closed</option>
                        <option value="all">all</option>
                      </select>
                    </div>
                    <Badge variant={liveGatewayReady ? 'success' : 'neutral'}>
                      {liveGatewayReady ? `${liveOrders.length} 条` : '网关未就绪'}
                    </Badge>
                  </div>
                  <DataTable
                    rows={liveOrders as unknown as Record<string, unknown>[]}
                    emptyText="暂无真实订单"
                    onRowClick={(row) => {
                      void handleSelectLiveOrder(row);
                    }}
                    columns={[
                      { key: 'order_id', label: '订单 ID' },
                      { key: 'symbol', label: '标的' },
                      { key: 'side', label: '方向' },
                      { key: 'status', label: '状态' },
                      { key: 'qty', label: '数量' },
                      {
                        key: 'submitted_at',
                        label: '提交时间',
                        render: (value: unknown) => String(value ?? '').slice(0, 16) || '-',
                      },
                    ]}
                  />
                  <p className="mt-2 mb-0 text-xs text-text-secondary">
                    点击订单行可直接切换下方的回执、成交回报和事件链。
                  </p>
                  {liveOrdersQ.error ? <p className="mt-2 mb-0 text-xs text-danger">{liveOrdersQ.error}</p> : null}
                  {liveOrderStatus ? (
                    <div className={`${noteCardCls} mt-3`}>
                      订单 {liveOrderStatus.order_id || '-'} · {liveOrderStatus.symbol || '-'} ·{' '}
                      {liveOrderStatus.status || '-'} · 已成交 {liveOrderStatus.filled_qty ?? '-'}
                    </div>
                  ) : null}
                  {liveReceipt ? (
                    <div className={`${noteCardCls} mt-3`}>
                      券商回执 {liveReceipt.message_type || '-'} · {liveReceipt.status || '-'} ·{' '}
                      {liveReceipt.reason || '无补充原因'}
                    </div>
                  ) : null}
                  {liveOrderStatusQ.error ? (
                    <p className="mt-2 mb-0 text-xs text-danger">{liveOrderStatusQ.error}</p>
                  ) : null}
                  {liveReceiptQ.error ? <p className="mt-2 mb-0 text-xs text-danger">{liveReceiptQ.error}</p> : null}
                  {liveSubmitApi.data ? (
                    <div className={`${noteCardCls} mt-3`}>
                      {liveSubmitApi.data.submitted
                        ? `真实订单已提交：${liveSubmitApi.data.order?.order_id || '-'}`
                        : `当前返回为 ${liveSubmitApi.data.mode || 'preview'}，未真正提交真实订单。`}
                    </div>
                  ) : null}
                  {liveMirrorApi.data ? (
                    <div className={`${noteCardCls} mt-3`}>
                      {liveMirrorApi.data.message ? (
                        <span>{liveMirrorApi.data.message}</span>
                      ) : (
                        <>
                          镜像候选 {liveMirrorApi.data.mirrorable_count ?? 0} 条，已下发到 paper{' '}
                          {liveMirrorApi.data.placed_order_count ?? 0} 条，paper 账户{' '}
                          {liveMirrorApi.data.paper_account_id || '-'}。
                        </>
                      )}
                    </div>
                  ) : null}
                  {liveSyncEventsApi.data?.artifact_id ? (
                    <div className={`${noteCardCls} mt-3`}>
                      事件快照已同步，artifact {liveSyncEventsApi.data.artifact_id}。
                    </div>
                  ) : null}
                </div>
              </div>

              <div className="mt-4 grid gap-4 2xl:grid-cols-2">
                <div>
                  <div className="mb-2 flex items-center justify-between gap-2">
                    <div className="text-sm font-medium text-text-primary">成交回报</div>
                    <Badge variant={liveGatewayReady ? 'success' : 'neutral'}>
                      {liveGatewayReady ? `${liveFillRows.length} 条` : '网关未就绪'}
                    </Badge>
                  </div>
                  <DataTable
                    rows={liveFillRows as unknown as Record<string, unknown>[]}
                    emptyText={submittedLiveOrderId.trim() ? '当前订单暂无成交回报' : '暂无成交回报'}
                    columns={[
                      { key: 'occurred_at', label: '成交时间' },
                      { key: 'symbol', label: '标的' },
                      { key: 'side', label: '方向' },
                      { key: 'qty', label: '数量' },
                      {
                        key: 'price',
                        label: '成交价',
                        render: (value: unknown) => (value == null ? '-' : fmtNum(Number(value), 2)),
                      },
                      {
                        key: 'amount',
                        label: '成交额',
                        render: (value: unknown) => (value == null ? '-' : fmtNum(Number(value), 2)),
                      },
                      {
                        key: 'commission',
                        label: '佣金',
                        render: (value: unknown) => (value == null ? '-' : fmtNum(Number(value), 2)),
                      },
                    ]}
                  />
                  {liveFillsQ.error ? <p className="mt-2 mb-0 text-xs text-danger">{liveFillsQ.error}</p> : null}
                </div>
                <div>
                  <div className="mb-2 flex items-center justify-between gap-2">
                    <div className="flex items-center gap-2">
                      <div className="text-sm font-medium text-text-primary">订单事件链</div>
                      <Badge variant={submittedLiveOrderId.trim() ? 'info' : 'neutral'}>
                        {submittedLiveOrderId.trim() || '未选择订单'}
                      </Badge>
                    </div>
                    <div className="flex flex-wrap items-center gap-2">
                      {liveEventArtifactId ? (
                        <button
                          type="button"
                          onClick={() => openArtifactDetail(liveEventArtifactId)}
                          className={chipButtonCls}
                        >
                          查看 artifact 详情
                        </button>
                      ) : null}
                      <button
                        type="button"
                        onClick={() => void handleLiveSyncEvents()}
                        disabled={liveSyncEventsApi.isPending}
                        className={chipButtonCls}
                      >
                        {liveSyncEventsApi.isPending ? '同步中...' : '同步事件快照'}
                      </button>
                    </div>
                  </div>
                  {submittedLiveOrderId.trim() ? (
                    <>
                      <KpiGrid cols={4} className="mb-3">
                        <KpiCard title="事件数" value={liveOrderEvents.length} />
                        <KpiCard title="回执" value={liveReceipt?.message_type || '-'} />
                        <KpiCard
                          title="当前状态"
                          value={liveOrderEventsQ.data?.state_machine?.current_status || liveOrderStatus?.status || '-'}
                        />
                        <KpiCard title="同步 artifact" value={liveSyncEventsApi.data?.artifact_id || '-'} />
                      </KpiGrid>
                      {liveEventArtifactId ? (
                        <div className={`${noteCardCls} mb-3`}>
                          <div className="flex flex-wrap items-center justify-between gap-2">
                            <div>
                              当前事件链快照已写入 artifact {liveEventArtifactId}，已收集 {liveEventArtifactCount}{' '}
                              条事件，可跳转独立详情页查看完整链路。
                            </div>
                            <div className="flex flex-wrap gap-2">
                              <button
                                type="button"
                                onClick={() => {
                                  setArtifactIdInput(liveEventArtifactId);
                                  setSubmittedArtifactId(liveEventArtifactId);
                                }}
                                className={chipButtonCls}
                              >
                                回填到 artifact 查询
                              </button>
                              <button
                                type="button"
                                onClick={() => openArtifactDetail(liveEventArtifactId)}
                                className={chipButtonCls}
                              >
                                打开详情页
                              </button>
                            </div>
                          </div>
                        </div>
                      ) : null}
                      <DataTable
                        rows={liveEventRows as unknown as Record<string, unknown>[]}
                        emptyText="当前订单暂无事件记录"
                        columns={[
                          { key: 'occurred_at', label: '时间' },
                          { key: 'event_type', label: '事件' },
                          { key: 'event_category', label: '类别' },
                          { key: 'event_status', label: '状态' },
                          { key: 'from_status', label: '前状态' },
                          { key: 'to_status', label: '后状态' },
                          { key: 'fill_qty', label: '成交量' },
                          {
                            key: 'fill_price',
                            label: '成交价',
                            render: (value: unknown) => (value == null ? '-' : fmtNum(Number(value), 2)),
                          },
                        ]}
                      />
                    </>
                  ) : (
                    <div className={`${noteCardCls} p-4`}>
                      输入 `order_id` 并查询订单后，这里会显示提交、回执、成交、撤单的完整事件链。
                    </div>
                  )}
                  {liveOrderEventsQ.error ? (
                    <p className="mt-2 mb-0 text-xs text-danger">{liveOrderEventsQ.error}</p>
                  ) : null}
                </div>
              </div>
            </SectionCard>

            <SectionCard className="mb-4">
              <div className="grid gap-4 2xl:grid-cols-[minmax(0,1.1fr)_minmax(320px,0.9fr)]">
                <div>
                  <h3 className="m-0 font-medium">智能执行参数</h3>
                  <p className="mb-0 mt-2 text-xs leading-6 text-text-secondary">
                    这里把模拟执行的输入参数、账户上下文和 artifact 关联一起整理成更松弛的表单栅格，减少旧式后台感。
                  </p>
                  <form onSubmit={handleRouteExecution} className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
                    <StockCodeInput
                      id="execution-code"
                      label="股票代码"
                      value={code}
                      onChange={setCode}
                      error={codeError}
                    />
                    <label className="flex flex-col gap-2 text-xs text-text-secondary">
                      <span>方向</span>
                      <select
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
                        type="number"
                        min={1}
                        value={quantity}
                        onChange={(event) => setQuantity(event.target.value)}
                        className="text-sm"
                      />
                    </label>
                    <label className="flex flex-col gap-2 text-xs text-text-secondary">
                      <span>执行模式</span>
                      <select
                        value={urgency}
                        onChange={(event) => setUrgency(event.target.value as 'normal' | 'high')}
                        className="text-sm"
                      >
                        <option value="normal">标准 TWAP</option>
                        <option value="high">高优先级 VWAP</option>
                      </select>
                    </label>
                    <label className="flex flex-col gap-2 text-xs text-text-secondary">
                      <span>订单类型</span>
                      <select
                        value={orderType}
                        onChange={(event) => setOrderType(event.target.value as 'market' | 'limit' | 'stop')}
                        className="text-sm"
                      >
                        <option value="market">市价单</option>
                        <option value="limit">限价单</option>
                        <option value="stop">止损单</option>
                      </select>
                    </label>
                    {orderType === 'market' || orderType === 'limit' ? (
                      <label className="flex flex-col gap-2 text-xs text-text-secondary">
                        <span>价格</span>
                        <input
                          type="number"
                          step="0.01"
                          value={price}
                          onChange={(event) => setPrice(event.target.value)}
                          className="text-sm"
                        />
                      </label>
                    ) : null}
                    {orderType === 'stop' ? (
                      <label className="flex flex-col gap-2 text-xs text-text-secondary">
                        <span>止损价</span>
                        <input
                          type="number"
                          step="0.01"
                          value={stopPrice}
                          onChange={(event) => setStopPrice(event.target.value)}
                          className="text-sm"
                        />
                      </label>
                    ) : null}
                    <label className="flex flex-col gap-2 text-xs text-text-secondary">
                      <span>账户</span>
                      <select
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
                    <label className="flex flex-col gap-2 text-xs text-text-secondary">
                      <span>artifact_id</span>
                      <input
                        value={artifactIdInput}
                        onChange={(event) => setArtifactIdInput(event.target.value)}
                        placeholder="可选，用于任务编排追踪"
                        className="text-sm"
                      />
                    </label>
                    <div className="col-span-2 flex items-end gap-2 sm:col-span-4">
                      <button type="submit" disabled={routeExecutionApi.isPending} className={heroPrimaryButtonCls}>
                        {routeExecutionApi.isPending ? '执行中...' : '提交执行'}
                      </button>
                      <button type="button" onClick={() => loadExample('600519')} className={chipButtonCls}>
                        载入示例
                      </button>
                    </div>
                  </form>
                  {formError ? <p className="mt-2 text-xs font-medium text-danger">{formError}</p> : null}
                  {routeExecutionApi.error ? (
                    <p className="mt-2 text-xs font-medium text-danger">{routeExecutionApi.error}</p>
                  ) : null}
                </div>

                <div className={sidePanelCls}>
                  <div className="text-sm font-medium text-text-primary">提交前提醒</div>
                  <div className="mt-4 space-y-3">
                    <div className={noteCardCls}>
                      执行中心会同时调用智能路由和模拟盘下单，所以它属于真实的交易模拟动作，不建议让 AI 自动提交。
                    </div>
                    <div className={noteCardCls}>高优先级模式会优先走 `VWAP`，标准模式走 `TWAP`。</div>
                    <div className={noteCardCls}>执行结果中的 `execution_id` 可继续用于查询状态。</div>
                    <div className={noteCardCls}>
                      预估金额：{estimatedAmount != null ? fmtNum(estimatedAmount) : '待输入价格后计算'}。
                    </div>
                  </div>
                </div>
              </div>
            </SectionCard>
          </div>
        }
        secondary={
          <div className="space-y-4 xl:h-full xl:overflow-y-auto xl:pl-1">
            <SectionCard className="mb-4">
              <div className="flex items-center justify-between gap-3 flex-wrap">
                <h3 className="m-0 font-medium">执行状态</h3>
                <Badge variant={executionWorkbench?.overview ? 'success' : 'neutral'}>
                  {currentExecutionId ? '可查询' : '等待 execution_id'}
                </Badge>
              </div>
              <form onSubmit={handleStatusQuery} className="mt-3 flex flex-wrap items-end gap-3">
                <label className="flex min-w-[280px] flex-col gap-1 text-xs text-text-secondary">
                  <span>execution_id</span>
                  <input
                    value={executionIdInput}
                    onChange={(event) => setExecutionIdInput(event.target.value)}
                    className="text-sm"
                  />
                </label>
                <button type="submit" className={chipButtonCls}>
                  查询状态
                </button>
              </form>
              <form onSubmit={handleArtifactQuery} className="mt-3 flex flex-wrap items-end gap-3">
                <label className="flex min-w-[280px] flex-col gap-1 text-xs text-text-secondary">
                  <span>artifact_id</span>
                  <input
                    value={artifactIdInput}
                    onChange={(event) => setArtifactIdInput(event.target.value)}
                    className="text-sm"
                  />
                </label>
                <button type="submit" className={chipButtonCls}>
                  查询 artifact
                </button>
              </form>
              {executionWorkbenchQ.error ? (
                <p className="mt-2 text-xs font-medium text-danger">{executionWorkbenchQ.error}</p>
              ) : null}
              {taskDetailQ.error ? <p className="mt-2 text-xs font-medium text-danger">{taskDetailQ.error}</p> : null}
              {artifactQ.error ? <p className="mt-2 text-xs font-medium text-danger">{artifactQ.error}</p> : null}
              {workbenchMessage && !executionWorkbench?.overview ? (
                <div className={`${noteCardCls} mt-3`}>{workbenchMessage}</div>
              ) : null}
              {latestExecution ? (
                <div className={`${sidePanelCls} mt-3`}>
                  <div className="text-sm font-medium text-text-primary">最近一次执行返回</div>
                  <div className="mt-2 text-xs text-text-secondary">
                    {briefSummary((latestExecution as Record<string, unknown>).execution ?? latestExecution)}
                  </div>
                  <details className="mt-2">
                    <summary className="cursor-pointer text-xs text-text-secondary">查看原始返回</summary>
                    <pre className="mb-0 mt-2 max-h-56 overflow-auto whitespace-pre-wrap text-[11px]">
                      {JSON.stringify(latestExecution, null, 2)}
                    </pre>
                  </details>
                </div>
              ) : null}
              {executionWorkbench?.overview ? (
                <div className={`${sidePanelCls} mt-3`}>
                  <div className="text-sm font-medium text-text-primary">执行工作台结果</div>
                  <div className="mt-2 text-xs text-text-secondary">
                    {workbenchMessage || briefSummary(statusPayload)}
                  </div>
                  <div className="mt-3 grid gap-3 2xl:grid-cols-[minmax(0,1fr)_minmax(280px,0.9fr)]">
                    <div className={noteCardCls}>
                      <div className="text-xs font-medium text-text-primary">结构化摘要</div>
                      <div className="mt-2 text-xs leading-6 text-text-secondary">
                        任务 {executionWorkbench.overview.executionId || '-'}，状态{' '}
                        {executionWorkbench.overview.status || '-'}，算法 {executionWorkbench.overview.algorithm || '-'}
                        ，告警 {executionWorkbench.overview.warningCount ?? 0} 条。
                      </div>
                      {workbenchWarnings.length > 0 ? (
                        <div className="mt-3 space-y-2">
                          {workbenchWarnings.slice(0, 3).map((item) => (
                            <div key={item.id} className="panel-soft rounded-[18px] px-3 py-2">
                              <div className="flex items-center justify-between gap-2">
                                <div className="text-xs font-medium text-text-primary">{item.title}</div>
                                <Badge
                                  variant={
                                    item.severity === 'high'
                                      ? 'warning'
                                      : item.severity === 'medium'
                                        ? 'neutral'
                                        : 'success'
                                  }
                                >
                                  {item.severity || 'unknown'}
                                </Badge>
                              </div>
                              {item.message ? (
                                <div className="mt-1 text-xs text-text-secondary">{item.message}</div>
                              ) : null}
                            </div>
                          ))}
                        </div>
                      ) : null}
                    </div>
                    <div className={noteCardCls}>
                      <div className="text-xs font-medium text-text-primary">账户上下文</div>
                      <div className="mt-2 space-y-2 text-xs text-text-secondary">
                        <div>账户：{executionWorkbench.orderContext?.accountId || '-'}</div>
                        <div>挂单：{executionWorkbench.orderContext?.pendingOrderCount ?? pendingOrders.length}</div>
                        <div>持仓：{executionWorkbench.orderContext?.positionsCount ?? '-'}</div>
                        <div>
                          总资产：
                          {executionWorkbench.orderContext?.totalValue != null
                            ? fmtNum(executionWorkbench.orderContext.totalValue)
                            : '-'}
                        </div>
                      </div>
                      {workbenchOrders.length > 0 ? (
                        <div className="panel-soft mt-3 rounded-[18px] p-2">
                          <div className="text-xs font-medium text-text-primary">最近订单</div>
                          <div className="mt-2 space-y-2">
                            {workbenchOrders.slice(0, 3).map((item) => (
                              <div
                                key={item.id}
                                className="flex items-center justify-between gap-2 text-xs text-text-secondary"
                              >
                                <span>
                                  {item.code || '-'} · {item.direction || '-'}
                                </span>
                                <span>{item.status || '-'}</span>
                              </div>
                            ))}
                          </div>
                        </div>
                      ) : null}
                    </div>
                  </div>
                  {statusPayload && Object.keys(statusPayload).length > 0 ? (
                    <details className="mt-3">
                      <summary className="cursor-pointer text-xs text-text-secondary">查看状态原始数据</summary>
                      <pre className="mb-0 mt-2 max-h-56 overflow-auto whitespace-pre-wrap text-[11px]">
                        {JSON.stringify(statusPayload, null, 2)}
                      </pre>
                    </details>
                  ) : null}
                </div>
              ) : executionWorkbenchQ.isFetching ? (
                <p className="mt-3 text-sm text-text-secondary">查询执行状态中...</p>
              ) : null}
              {artifactQ.data ? (
                <div className={`${sidePanelCls} mt-3`}>
                  <div className="flex items-center justify-between gap-2">
                    <div className="text-sm font-medium text-text-primary">Artifact 关联执行</div>
                    <Badge variant={artifactQ.data.count > 0 ? 'success' : 'neutral'}>
                      {artifactQ.data.count > 0 ? `${artifactQ.data.count} 条任务` : '暂无任务'}
                    </Badge>
                  </div>
                  <div className="mt-2 text-xs text-text-secondary">
                    artifact {artifactQ.data.artifactId}，最新任务 {artifactQ.data.latestTaskId || '-'}。
                  </div>
                  {artifactQ.data.count > 0 && artifactDetailHref ? (
                    <div className="mt-3">
                      <button
                        type="button"
                        onClick={() => openArtifactDetail(artifactQ.data?.artifactId || currentArtifactId)}
                        className={chipButtonCls}
                      >
                        打开 artifact 详情页
                      </button>
                    </div>
                  ) : null}
                  {artifactQ.data.latestTask ? (
                    <div className="mt-3 grid gap-2 text-xs text-text-secondary sm:grid-cols-2">
                      <div>标的：{artifactQ.data.latestTask.code || '-'}</div>
                      <div>状态：{artifactQ.data.latestTask.status || '-'}</div>
                      <div>算法：{artifactQ.data.latestTask.algorithm || '-'}</div>
                      <div>告警：{artifactQ.data.latestTask.warningCount ?? 0}</div>
                    </div>
                  ) : null}
                </div>
              ) : null}
            </SectionCard>

            <SectionCard className="mb-4">
              <div className="flex items-center justify-between gap-3 flex-wrap">
                <div>
                  <h3 className="m-0 font-medium">执行任务列表</h3>
                  <p className="mb-0 mt-1 text-xs text-text-secondary">
                    这里直接映射 execution_manager.list，点选任务后会刷新当前详情和 artifact 结果。
                  </p>
                </div>
                <button type="button" onClick={() => tasksQ.refetch()} className={chipButtonCls}>
                  刷新任务
                </button>
              </div>
              <DataTable
                rows={executionTasks as unknown as Record<string, unknown>[]}
                emptyText="暂无执行任务"
                searchable
                rowKey="taskId"
                onRowClick={(row) => {
                  const nextTaskId = String(row.taskId ?? '').trim();
                  const nextArtifactId = String(row.artifactId ?? '').trim();
                  if (nextTaskId) {
                    setExecutionIdInput(nextTaskId);
                    setSubmittedExecutionId(nextTaskId);
                  }
                  if (nextArtifactId) {
                    setArtifactIdInput(nextArtifactId);
                    setSubmittedArtifactId(nextArtifactId);
                  }
                }}
                columns={[
                  { key: 'taskId', label: '任务 ID' },
                  { key: 'artifactId', label: 'Artifact' },
                  { key: 'code', label: '标的' },
                  { key: 'algorithm', label: '算法' },
                  { key: 'status', label: '状态' },
                  { key: 'warningCount', label: '告警' },
                  {
                    key: 'createdAt',
                    label: '创建时间',
                    render: (value: unknown) => String(value ?? '').slice(0, 16) || '-',
                  },
                ]}
                mobileCardRender={(row) => (
                  <div className="space-y-2">
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <div className="text-sm font-medium text-text-primary">{String(row.taskId ?? '-')}</div>
                        <div className="text-xs text-text-secondary">
                          {String(row.code ?? '-')} · {String(row.algorithm ?? '-')}
                        </div>
                      </div>
                      <Badge variant={String(row.status ?? '').includes('completed') ? 'success' : 'neutral'}>
                        {String(row.status ?? '-')}
                      </Badge>
                    </div>
                    <div className="grid grid-cols-2 gap-2 text-xs text-text-secondary">
                      <div>Artifact：{String(row.artifactId ?? '-')}</div>
                      <div>告警：{String(row.warningCount ?? 0)}</div>
                    </div>
                  </div>
                )}
              />
            </SectionCard>

            <SectionCard className="mb-4">
              <div className="flex items-center justify-between gap-3 flex-wrap">
                <div>
                  <h3 className="m-0 font-medium">执行复盘摘要</h3>
                  <p className="mb-0 mt-1 text-xs text-text-secondary">
                    把执行结果直接串到绩效、风险和个股详情，避免执行完成后链路中断。
                  </p>
                </div>
                <Badge
                  variant={executionInsight?.hasHighSeverity ? 'warning' : executionInsight ? 'success' : 'neutral'}
                >
                  {executionInsight?.hasHighSeverity ? '高严重级告警' : executionInsight ? '可复盘' : '等待执行结果'}
                </Badge>
              </div>

              <KpiGrid cols={5} className="mt-4">
                <KpiCard title="执行算法" value={executionInsight?.algorithm || '-'} />
                <KpiCard title="计划分片" value={executionInsight?.slices ?? '-'} />
                <KpiCard title="执行状态" value={executionInsight?.status || '-'} />
                <KpiCard title="告警数量" value={executionInsight?.warningCount ?? '-'} />
                <KpiCard
                  title="预估成本"
                  value={
                    executionInsight?.estimatedCostTotal != null ? fmtNum(executionInsight.estimatedCostTotal) : '-'
                  }
                />
              </KpiGrid>

              <div className="mt-4 grid gap-4 2xl:grid-cols-[minmax(0,1.1fr)_minmax(280px,0.9fr)]">
                <div className="panel-soft rounded-[24px] p-4">
                  <div className="text-sm font-medium text-text-primary">当前摘要</div>
                  <div className="mt-2 text-xs leading-6 text-text-secondary">
                    {executionInsight
                      ? `任务 ${executionInsight.taskId || '-'}，标的 ${executionInsight.code || activeExecutionCode || '-'}，总量 ${executionInsight.totalShares ?? '-'} 股，计划时长 ${executionInsight.durationMinutes ?? '-'} 分钟，软闸门画像 ${executionInsight.softGateProfile || '-'}。`
                      : '提交执行或输入 execution_id 后，这里会汇总执行计划、告警和复盘入口。'}
                  </div>
                  <div className="mt-3 flex flex-wrap gap-2">
                    <button type="button" onClick={() => openPerformanceReview()} className={chipButtonCls}>
                      打开绩效复盘
                    </button>
                    <button type="button" onClick={() => openRiskReview()} className={chipButtonCls}>
                      打开风险中心
                    </button>
                    {activeExecutionCode ? (
                      <button
                        type="button"
                        onClick={() => openStockDetail(activeExecutionCode)}
                        className={chipButtonCls}
                      >
                        打开个股详情
                      </button>
                    ) : null}
                  </div>
                </div>

                <div className="panel-soft rounded-[24px] p-4">
                  <div className="text-sm font-medium text-text-primary">下一步建议</div>
                  <ul className="mb-0 mt-2 space-y-2 pl-4 text-xs leading-5 text-text-secondary">
                    {executionGuidance.map((item) => (
                      <li key={item}>{item}</li>
                    ))}
                  </ul>
                </div>
              </div>
            </SectionCard>

            <SectionCard>
              <div className="flex items-center justify-between gap-3 flex-wrap">
                <h3 className="m-0 font-medium">当前挂单</h3>
                <button type="button" onClick={() => pendingQ.refetch()} className={chipButtonCls}>
                  刷新挂单
                </button>
              </div>
              <DataTable
                rows={pendingOrders as unknown as Record<string, unknown>[]}
                emptyText="暂无挂单"
                columns={[
                  {
                    key: 'created_at',
                    label: '时间',
                    render: (value: unknown) => String(value ?? '').slice(0, 16) || '-',
                  },
                  { key: 'code', label: '代码' },
                  { key: 'direction', label: '方向' },
                  { key: 'shares', label: '数量' },
                  {
                    key: 'price',
                    label: '价格',
                    render: (value: unknown) => (value == null ? '-' : fmtNum(Number(value), 2)),
                  },
                  { key: 'status', label: '状态' },
                ]}
                mobileCardRender={(row) => (
                  <div className="space-y-2">
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <div className="text-sm font-medium text-text-primary">
                          {String(row.code ?? '-')} · {String(row.direction ?? '-')}
                        </div>
                        <div className="text-xs text-text-secondary">
                          {String(row.created_at ?? '').slice(0, 16) || '-'}
                        </div>
                      </div>
                      <Badge variant={String(row.status ?? '').includes('fill') ? 'success' : 'warning'}>
                        {String(row.status ?? '-')}
                      </Badge>
                    </div>
                    <div className="grid grid-cols-2 gap-2 text-xs text-text-secondary">
                      <div>数量：{String(row.shares ?? '-')}</div>
                      <div>价格：{row.price == null ? '-' : fmtNum(Number(row.price), 2)}</div>
                    </div>
                  </div>
                )}
              />
            </SectionCard>
          </div>
        }
      />
    </PageContainer>
  );
}
