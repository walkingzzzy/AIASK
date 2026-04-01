'use client';

import { FormEvent, useEffect, useMemo, useRef, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import WorkspaceSplitLayout from '@/components/workspace-split-layout';
import WorkspaceToolbar from '@/components/workspace-toolbar';
import ExecutionHero from '@/app/execution/components/execution-hero';
import ExecutionLiveGatewayPanel from '@/app/execution/components/execution-live-gateway-panel';
import ExecutionOrderForm from '@/app/execution/components/execution-order-form';
import ExecutionPendingOrdersPanel from '@/app/execution/components/execution-pending-orders-panel';
import ExecutionReviewPanel from '@/app/execution/components/execution-review-panel';
import ExecutionStatusPanel from '@/app/execution/components/execution-status-panel';
import ExecutionTasksPanel from '@/app/execution/components/execution-tasks-panel';
import { useExecutionLiveGateway } from '@/app/execution/hooks/use-execution-live-gateway';
import { PageContainer, KpiCard, KpiGrid } from '@/components/ui';
import { useApiMutation } from '@/hooks/use-api-mutation';
import { useApiQuery } from '@/hooks/use-api-query';
import { useStockCode } from '@/hooks/use-stock-code';
import { usePageActions } from '@/hooks/use-page-actions';
import { usePageContext } from '@/hooks/use-page-context';
import { extractArray, fmtNum } from '@/lib/data-utils';
import {
  asRecord,
  briefSummary,
  findExecutionId,
  isTransientMutationError,
  readExecutionInsight,
  toFiniteNumber,
} from '@/lib/execution-normalizers';
import { selectActiveWorkspace, useWorkbenchStore } from '@/store/workbench-store';
import type {
  ExecutionArtifactResponse,
  ExecutionTaskDetailResponse,
  ExecutionTasksResponse,
  ExecutionWorkbenchResponse,
  PaperTradingAccountsResponse,
  PaperTradingPendingOrdersResponse,
  PaperTradingRouteExecutionInput,
} from '@aiask/shared-types';

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
  const lastWorkspaceIdRef = useRef<string | null>(null);

  const accountsQ = useApiQuery<PaperTradingAccountsResponse | unknown[]>('/paper-trading/accounts');
  const pendingQ = useApiQuery<PaperTradingPendingOrdersResponse>(
    accountId
      ? `/paper-trading/pending-orders?account_id=${encodeURIComponent(accountId)}`
      : '/paper-trading/pending-orders',
  );
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
  const { liveGatewayReady, liveOrderCount, liveFillCount, panelProps: liveGatewayPanelProps } =
    useExecutionLiveGateway({ accountId });

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
  const workbenchMessage = executionWorkbench?.message ?? null;
  const executionTasks = tasksQ.data?.tasks ?? [];
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
  const executionSummaryText = executionInsight
    ? briefSummary(executionWorkbench?.result ?? latestExecution ?? executionInsight)
    : '尚未形成执行结果';

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

  function selectExecutionTask(nextTaskId: string, nextArtifactId: string) {
    if (nextTaskId) {
      setExecutionIdInput(nextTaskId);
      setSubmittedExecutionId(nextTaskId);
    }
    if (nextArtifactId) {
      setArtifactIdInput(nextArtifactId);
      setSubmittedArtifactId(nextArtifactId);
    }
  }

  function useArtifactForQuery(nextArtifactId: string) {
    if (!nextArtifactId) return;
    setArtifactIdInput(nextArtifactId);
    setSubmittedArtifactId(nextArtifactId);
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
      <ExecutionHero
        urgency={urgency}
        liveGatewayReady={liveGatewayReady}
        activeExecutionCode={activeExecutionCode}
        currentArtifactId={currentArtifactId}
        trimmedCode={trimmedCode}
        direction={direction}
        quantity={quantity}
        estimatedAmount={estimatedAmount}
        orderType={orderType}
        currentExecutionId={currentExecutionId}
        executionInsight={executionInsight}
        workbenchWarningCount={executionWorkbench?.warnings?.length ?? 0}
        pendingOrderCount={pendingOrders.length}
        liveOrderCount={liveOrderCount}
        liveFillCount={liveFillCount}
        summaryText={executionSummaryText}
        executionGuidance={executionGuidance}
        onOpenPerformanceReview={() => openPerformanceReview()}
        onOpenRiskReview={() => openRiskReview()}
        onOpenStockDetail={openStockDetail}
        onOpenArtifactDetail={openArtifactDetail}
        onStatusQuery={() => handleStatusQuery()}
        onRefreshLiveGateway={liveGatewayPanelProps.onRefresh}
      />

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
            <ExecutionLiveGatewayPanel
              {...liveGatewayPanelProps}
              onOpenArtifactDetail={openArtifactDetail}
              onUseArtifactForQuery={useArtifactForQuery}
            />

            <ExecutionOrderForm
              code={code}
              codeError={codeError}
              onCodeChange={setCode}
              direction={direction}
              onDirectionChange={setDirection}
              quantity={quantity}
              onQuantityChange={setQuantity}
              urgency={urgency}
              onUrgencyChange={setUrgency}
              orderType={orderType}
              onOrderTypeChange={setOrderType}
              price={price}
              onPriceChange={setPrice}
              stopPrice={stopPrice}
              onStopPriceChange={setStopPrice}
              accountId={accountId}
              onAccountIdChange={setAccountId}
              accounts={accounts}
              artifactIdInput={artifactIdInput}
              onArtifactIdChange={setArtifactIdInput}
              estimatedAmount={estimatedAmount}
              formError={formError}
              routeExecutionError={routeExecutionApi.error}
              routeExecutionPending={routeExecutionApi.isPending}
              onSubmit={handleRouteExecution}
              onLoadExample={loadExample}
            />
          </div>
        }
        secondary={
          <div className="space-y-4 xl:h-full xl:overflow-y-auto xl:pl-1">
            <ExecutionStatusPanel
              currentExecutionId={currentExecutionId}
              executionIdInput={executionIdInput}
              onExecutionIdChange={setExecutionIdInput}
              artifactIdInput={artifactIdInput}
              onArtifactIdChange={setArtifactIdInput}
              onStatusSubmit={handleStatusQuery}
              onArtifactSubmit={handleArtifactQuery}
              executionWorkbench={executionWorkbench}
              latestExecution={latestExecution}
              workbenchMessage={workbenchMessage}
              statusPayload={statusPayload}
              pendingOrderCount={pendingOrders.length}
              artifactData={artifactQ.data}
              currentArtifactId={currentArtifactId}
              executionWorkbenchError={executionWorkbenchQ.error}
              taskDetailError={taskDetailQ.error}
              artifactError={artifactQ.error}
              onOpenArtifactDetail={openArtifactDetail}
            />

            <ExecutionTasksPanel
              executionTasks={executionTasks}
              onRefresh={() => void tasksQ.refetch()}
              onSelectTask={selectExecutionTask}
            />

            <ExecutionReviewPanel
              executionInsight={executionInsight}
              activeExecutionCode={activeExecutionCode}
              executionGuidance={executionGuidance}
              onOpenPerformanceReview={openPerformanceReview}
              onOpenRiskReview={openRiskReview}
              onOpenStockDetail={openStockDetail}
            />

            <ExecutionPendingOrdersPanel
              pendingOrders={pendingOrders}
              onRefresh={() => void pendingQ.refetch()}
            />
          </div>
        }
      />
    </PageContainer>
  );
}
