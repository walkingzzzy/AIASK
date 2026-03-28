import { BadGatewayException, Injectable } from '@nestjs/common';
import type {
  ExecutionArtifactResponse,
  ExecutionWorkbenchCost,
  ExecutionWorkbenchNextAction,
  ExecutionWorkbenchOrderContext,
  ExecutionWorkbenchOrderItem,
  ExecutionWorkbenchResponse,
  ExecutionTaskDetailResponse,
  ExecutionTaskListItem,
  ExecutionTasksResponse,
  ExecutionWorkbenchWarning,
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
import { McpGatewayService } from '../mcp-gateway/mcp-gateway.service';
import { PaperTradingService } from '../paper-trading/paper-trading.service';

@Injectable()
export class ExecutionService {
  constructor(
    private readonly paperTradingService: PaperTradingService,
    private readonly mcpGatewayService: McpGatewayService,
  ) {}

  async workbench(userId: string, executionId?: string, accountId?: string): Promise<ExecutionWorkbenchResponse> {
    const normalizedExecutionId = String(executionId ?? '').trim();
    const normalizedAccountId = String(accountId ?? '').trim();

    const [executionPayload, summaryPayload, pendingPayload, ordersPayload, positionsPayload] = await Promise.all([
      normalizedExecutionId ? this.paperTradingService.executionStatus(userId, normalizedExecutionId) : Promise.resolve(null),
      normalizedAccountId ? this.paperTradingService.summary(userId, normalizedAccountId) : Promise.resolve(null),
      normalizedAccountId ? this.paperTradingService.pendingOrders(userId, normalizedAccountId) : Promise.resolve(null),
      normalizedAccountId ? this.paperTradingService.orders(userId, normalizedAccountId) : Promise.resolve(null),
      normalizedAccountId ? this.paperTradingService.positions(userId, normalizedAccountId) : Promise.resolve(null),
    ]);

    const executionRoot = this.asRecord(executionPayload);
    const task = this.asRecord(executionRoot.task);
    const plan = this.asRecord(task.plan);
    const softGate = this.asRecord(executionRoot.soft_gate ?? executionRoot.softGate ?? task.soft_gate ?? task.softGate);
    const costModel = this.asRecord(task.cost_model ?? task.costModel ?? executionRoot.cost_model ?? executionRoot.costModel);
    const estimatedCost = this.asRecord(costModel.estimated);
    const executionFeasibility = this.asRecord(executionRoot.execution_feasibility ?? task.execution_feasibility);
    const warnings = this.normalizeWarnings(
      this.asRecordArray(executionRoot.warnings ?? task.pretrade_warnings),
    );

    const summary = this.asRecord(summaryPayload);
    const account = this.asRecord(summary.account);
    const pendingOrders = this.asRecordArray(this.asRecord(pendingPayload).orders ?? pendingPayload);
    const orders = this.asRecordArray(this.asRecord(ordersPayload).orders ?? ordersPayload);
    const positions = this.asRecordArray(this.asRecord(positionsPayload).positions ?? positionsPayload);

    const resolvedExecutionId = this.toStringValue(
      task.task_id ?? task.taskId ?? executionRoot.execution_id ?? executionRoot.executionId,
    ) ?? (normalizedExecutionId || null);
    const resolvedAccountId = this.toStringValue(
      summary.account_id ?? summary.accountId ?? account.account_id ?? account.accountId,
    ) ?? (normalizedAccountId || null);
    const code = this.toStringValue(task.code ?? executionRoot.code) ?? null;
    const warningCount = this.toInt(softGate.warning_count ?? softGate.warningCount) ?? warnings.length;
    const hasHighSeverity = Boolean(
      softGate.has_high_severity
      ?? softGate.hasHighSeverity
      ?? warnings.some((item) => item.severity === 'high'),
    );

    const overview = resolvedExecutionId || code || resolvedAccountId
      ? {
          executionId: resolvedExecutionId,
          artifactId: this.toStringValue(task.artifact_id ?? task.artifactId ?? executionRoot.artifact_id ?? executionRoot.artifactId),
          accountId: resolvedAccountId,
          code,
          status: this.toStringValue(task.status ?? executionRoot.status),
          algorithm: this.toStringValue(task.algorithm ?? executionRoot.algorithm),
          createdAt: this.toStringValue(task.created_at ?? executionRoot.created_at),
          totalShares: this.toNum(task.total_shares ?? task.total_quantity ?? executionRoot.total_shares ?? executionRoot.total_quantity),
          durationMinutes: this.toNum(plan.duration_minutes ?? plan.duration ?? executionRoot.duration_minutes ?? executionRoot.duration),
          slices: this.toNum(plan.slices ?? executionRoot.slices),
          lifecycleCount: this.toNum(executionRoot.lifecycle_count ?? executionRoot.lifecycleCount ?? (Array.isArray(task.lifecycle) ? task.lifecycle.length : null)),
          softGateProfile: this.toStringValue(softGate.profile ?? executionRoot.profile),
          warningCount,
          hasHighSeverity,
          executionFeasible: this.toBoolean(executionFeasibility.feasible),
          executionBlocking: this.toBoolean(executionFeasibility.blocking),
        }
      : null;

    const cost: ExecutionWorkbenchCost | null = overview
      ? {
          estimatedTotal: this.toNum(executionRoot.estimated_cost_total ?? executionRoot.estimatedCostTotal ?? estimatedCost.total),
          commission: this.toNum(estimatedCost.commission ?? estimatedCost.brokerage),
          marketImpact: this.toNum(estimatedCost.impact ?? estimatedCost.market_impact ?? estimatedCost.marketImpact),
          slippage: this.toNum(estimatedCost.slippage),
          participationRate: this.toNum(
            executionFeasibility.participation_rate
            ?? executionFeasibility.participationRate
            ?? this.asRecord(executionFeasibility.metrics).participation_rate,
          ),
          riskBudgetProfile: this.toStringValue(executionFeasibility.risk_budget_profile ?? executionFeasibility.riskBudgetProfile ?? softGate.profile),
        }
      : null;

    const orderContext: ExecutionWorkbenchOrderContext | null = resolvedAccountId || pendingOrders.length > 0 || orders.length > 0 || positions.length > 0
      ? {
          accountId: resolvedAccountId,
          pendingOrderCount: this.toInt(summary.pending_orders_count ?? summary.pendingOrdersCount) ?? pendingOrders.length,
          positionsCount: this.toInt(summary.positions_count ?? summary.positionsCount) ?? positions.length,
          totalValue: this.toNum(summary.total_value ?? summary.totalValue ?? account.total_value ?? account.totalValue),
          totalReturnPct: this.toNum(summary.total_return_pct ?? summary.totalReturnPct),
          recentOrders: this.normalizeOrders(orders),
        }
      : null;

    const nextActions = this.buildNextActions({
      code,
      executionId: resolvedExecutionId,
      accountId: resolvedAccountId,
      warningCount,
      hasHighSeverity,
      pendingOrderCount: orderContext?.pendingOrderCount ?? 0,
    });

    const sourceTools = {
      ...(normalizedExecutionId ? { execution: 'execution_manager.summary' as const } : {}),
      ...(normalizedAccountId ? { summary: 'paper_trading_manager.summary' as const } : {}),
      ...(normalizedAccountId ? { pendingOrders: 'paper_trading_manager.pending_orders' as const } : {}),
      ...(normalizedAccountId ? { orders: 'paper_trading_manager.orders' as const } : {}),
      ...(normalizedAccountId ? { positions: 'paper_trading_manager.positions' as const } : {}),
    };

    return {
      message: this.buildMessage({
        executionId: resolvedExecutionId,
        accountId: resolvedAccountId,
        warningCount,
        hasHighSeverity,
      }),
      empty: !overview && !orderContext,
      executionId: resolvedExecutionId,
      accountId: resolvedAccountId,
      overview,
      warnings,
      cost,
      orderContext,
      nextActions,
      sourceTools: Object.keys(sourceTools).length > 0 ? sourceTools : undefined,
      argsMatched: {
        executionId: normalizedExecutionId || undefined,
        accountId: normalizedAccountId || undefined,
      },
      result: {
        execution: executionPayload,
        summary: summaryPayload,
        pendingOrders: pendingPayload,
        orders: ordersPayload,
        positions: positionsPayload,
      },
    };
  }

  async tasks(userId: string, status?: string): Promise<ExecutionTasksResponse> {
    const normalizedStatus = String(status ?? '').trim().toLowerCase() || null;
    const params = normalizedStatus ? { user_id: userId, status: normalizedStatus } : { user_id: userId };
    const payload = await this.callManager('list', params);
    const record = this.extractDataRecord(payload);
    const tasks = this.normalizeTaskList(record.tasks ?? []);
    const pendingOrders = this.normalizeTaskList(record.pending_orders ?? record.pendingOrders ?? []);
    const completedOrders = this.normalizeTaskList(record.completed_orders ?? record.completedOrders ?? []);

    return {
      count: this.toInt(record.count) ?? tasks.length,
      status: normalizedStatus,
      tasks,
      pendingOrders,
      completedOrders,
      sourceTool: 'execution_manager.list',
      argsMatched: { action: 'list', params },
      result: payload,
    };
  }

  async taskDetail(userId: string, taskId: string, accountId?: string): Promise<ExecutionTaskDetailResponse> {
    const normalizedTaskId = String(taskId).trim();
    const normalizedAccountId = String(accountId ?? '').trim() || undefined;
    let payload: unknown;
    try {
      payload = await this.callManager('summary', { user_id: userId, task_id: normalizedTaskId });
    } catch (error) {
      if (this.isTaskNotFoundError(error)) {
        return this.buildMissingTaskDetail(normalizedTaskId, normalizedAccountId);
      }
      throw error;
    }
    const taskRecord = this.extractDataRecord(payload);
    const workbench = await this.workbench(userId, normalizedTaskId, normalizedAccountId);
    const task = this.normalizeTaskBrief(taskRecord);
    const sourceTools = {
      ...(workbench.sourceTools ?? {}),
      taskSummary: 'execution_manager.summary' as const,
    };

    return {
      ...workbench,
      taskId: normalizedTaskId,
      artifactId: task.artifactId ?? workbench.overview?.artifactId ?? null,
      task,
      sourceTools,
      result: {
        taskSummary: payload,
        workbench: workbench.result,
      },
    };
  }

  async artifact(userId: string, artifactId: string, accountId?: string): Promise<ExecutionArtifactResponse> {
    const normalizedArtifactId = String(artifactId).trim();
    const taskList = await this.tasks(userId);
    const matches = taskList.tasks
      .filter((task) => task.artifactId === normalizedArtifactId)
      .sort((left, right) => this.toTime(right.createdAt) - this.toTime(left.createdAt));
    const latestTask = matches[0] ?? null;
    const detail = latestTask?.taskId
      ? await this.taskDetail(userId, latestTask.taskId, accountId)
      : null;

    return {
      artifactId: normalizedArtifactId,
      count: matches.length,
      latestTaskId: latestTask?.taskId ?? null,
      latestTask,
      taskIds: matches.map((task) => task.taskId),
      detail,
      sourceTools: {
        tasks: 'execution_manager.list',
        detail: detail ? 'execution_manager.summary' : undefined,
      },
      argsMatched: {
        artifactId: normalizedArtifactId,
        accountId: accountId?.trim() || undefined,
      },
      result: {
        tasks: taskList.result,
        detail: detail?.result ?? null,
      },
    };
  }

  async listArtifacts(userId: string, accountId?: string): Promise<{
    artifacts: Array<{ artifactId: string; taskId: string; code?: string | null; algorithm?: string | null; status?: string | null; createdAt?: string | null; warningCount: number; hasHighSeverity: boolean }>;
    count: number;
  }> {
    const taskList = await this.tasks(userId, undefined);
    const seenArtifacts = new Map<string, typeof taskList.tasks[0]>();
    for (const task of taskList.tasks) {
      if (!task.artifactId) continue;
      const existing = seenArtifacts.get(task.artifactId);
      if (!existing || this.toTime(task.createdAt) > this.toTime(existing.createdAt)) {
        seenArtifacts.set(task.artifactId, task);
      }
    }
    const artifacts = Array.from(seenArtifacts.values())
      .sort((a, b) => this.toTime(b.createdAt) - this.toTime(a.createdAt))
      .map((task) => ({
        artifactId: task.artifactId!,
        taskId: task.taskId,
        code: task.code ?? null,
        algorithm: task.algorithm ?? null,
        status: task.status ?? null,
        createdAt: task.createdAt ?? null,
        warningCount: task.warningCount ?? 0,
        hasHighSeverity: task.hasHighSeverity ?? false,
      }));
    return { artifacts, count: artifacts.length };
  }

  async liveGatewayStatus(): Promise<LiveTradingGatewayStatusResponse> {
    return this.callLiveManager('gateway_status');
  }

  async liveAccount(): Promise<LiveTradingAccountResponse> {
    return this.callLiveManager('account');
  }

  async livePositions(): Promise<LiveTradingPositionsResponse> {
    return this.callLiveManager('positions');
  }

  async liveOrders(params: { status?: string; limit?: number; symbols?: string } = {}): Promise<LiveTradingOrdersResponse> {
    return this.callLiveManager('orders', params);
  }

  async liveOrderStatus(orderId: string): Promise<LiveTradingOrderStatusResponse> {
    return this.callLiveManager('order_status', { order_id: orderId });
  }

  async liveOrderEvents(orderId: string, params: { limit?: number } = {}): Promise<LiveTradingOrderEventsResponse> {
    return this.callLiveManager('order_events', { order_id: orderId, ...params });
  }

  async liveFills(params: { order_id?: string; limit?: number; symbols?: string } = {}): Promise<LiveTradingFillsResponse> {
    return this.callLiveManager('fills', params);
  }

  async liveBrokerReceipt(orderId: string): Promise<LiveTradingBrokerReceiptResponse> {
    return this.callLiveManager('broker_receipts', { order_id: orderId });
  }

  async liveSyncOrderEvents(params: {
    order_id: string;
    limit?: number;
    persist_artifact?: boolean;
    output_artifact_id?: string;
  }): Promise<LiveTradingSyncOrderEventsResponse> {
    return this.callLiveManager('sync_order_events', params);
  }

  async liveSubmitOrder(params: {
    symbol?: string;
    code?: string;
    side?: string;
    direction?: string;
    qty?: number;
    quantity?: number;
    notional?: number;
    type?: string;
    order_type?: string;
    time_in_force?: string;
    limit_price?: number;
    stop_price?: number;
    client_order_id?: string;
    extended_hours?: boolean;
    dry_run?: boolean;
  }): Promise<LiveTradingSubmitOrderResponse> {
    return this.callLiveManager('submit_order', {
      dry_run: params.dry_run ?? true,
      ...params,
    });
  }

  async liveCancelOrder(params: {
    order_id: string;
    dry_run?: boolean;
  }): Promise<LiveTradingCancelOrderResponse> {
    return this.callLiveManager('cancel_order', {
      dry_run: params.dry_run ?? true,
      ...params,
    });
  }

  async liveMirrorToPaper(
    userId: string,
    params: {
      execute?: boolean;
      paper_account_id?: string;
      paper_account_name?: string;
      initial_capital?: number;
    } = {},
  ): Promise<LiveTradingMirrorToPaperResponse> {
    try {
      return await this.callLiveManager('mirror_to_paper', {
        paper_user_id: userId,
        ...params,
      });
    } catch (error) {
      return {
        mirrored: false,
        executed: Boolean(params.execute),
        paper_account_id: params.paper_account_id ?? null,
        mirrorable_count: 0,
        placed_order_count: 0,
        message: this.extractExceptionDetail(error) ?? '上游能力暂不可用',
        raw: {
          degraded: true,
          fallback_reason: 'live_manager_unavailable',
        },
      };
    }
  }

  private buildMessage(input: {
    executionId: string | null;
    accountId: string | null;
    warningCount: number;
    hasHighSeverity: boolean;
  }) {
    if (!input.executionId && !input.accountId) {
      return '请提供 executionId 或 accountId 以加载执行工作台。';
    }

    if (!input.executionId && input.accountId) {
      return `已加载账户 ${input.accountId} 的执行上下文，当前未指定 executionId。`;
    }

    if (!input.executionId) {
      return '已加载执行上下文。';
    }

    if (input.hasHighSeverity) {
      return `执行单 ${input.executionId} 存在高严重级告警，建议优先联动风险中心复核。`;
    }

    if (input.warningCount > 0) {
      return `执行单 ${input.executionId} 已加载，共 ${input.warningCount} 条执行告警。`;
    }

    return `执行单 ${input.executionId} 已加载，可继续查看绩效与风险联动结果。`;
  }

  private buildNextActions(input: {
    code: string | null;
    executionId: string | null;
    accountId: string | null;
    warningCount: number;
    hasHighSeverity: boolean;
    pendingOrderCount: number;
  }): ExecutionWorkbenchNextAction[] {
    const actions: ExecutionWorkbenchNextAction[] = [];

    if (input.hasHighSeverity) {
      actions.push({
        id: 'open-risk',
        label: '打开风险中心',
        reason: '当前执行存在高严重级软闸门告警，需要优先复核风险暴露与约束。',
        targetPage: 'risk',
        payload: {
          accountId: input.accountId,
          executionId: input.executionId,
          lookbackDays: 30,
        },
      });
    }

    if (input.accountId) {
      actions.push({
        id: 'open-performance',
        label: '打开绩效中心',
        reason: input.warningCount > 0 ? '结合告警与收益结果做执行复盘。' : '继续检查执行后收益表现与回撤变化。',
        targetPage: 'performance',
        payload: {
          accountId: input.accountId,
          executionId: input.executionId,
          days: 30,
        },
      });
    }

    if (input.code) {
      actions.push({
        id: 'open-stock',
        label: '打开个股详情',
        reason: '回到标的详情页复核行情、资金流和基本面。',
        targetPage: 'stock',
        payload: { code: input.code },
      });
    }

    if (input.accountId && input.pendingOrderCount > 0) {
      actions.push({
        id: 'open-paper-trading',
        label: '打开模拟交易',
        reason: '账户仍有挂单，适合继续查看订单状态与持仓变动。',
        targetPage: 'paper-trading',
        payload: { accountId: input.accountId },
      });
    }

    return actions;
  }

  private buildMissingTaskDetail(taskId: string, accountId?: string): ExecutionTaskDetailResponse {
    return {
      message: `执行单 ${taskId} 当前不可用，可能已过期、已被清理，或服务刚完成重启。`,
      empty: true,
      executionId: taskId,
      accountId: accountId ?? null,
      overview: null,
      warnings: [],
      cost: null,
      orderContext: null,
      nextActions: this.buildNextActions({
        code: null,
        executionId: taskId,
        accountId: accountId ?? null,
        warningCount: 0,
        hasHighSeverity: false,
        pendingOrderCount: 0,
      }),
      sourceTools: {
        taskSummary: 'execution_manager.summary',
      },
      argsMatched: {
        executionId: taskId,
        accountId,
      },
      result: {
        missing: true,
        taskSummary: null,
      },
      taskId,
      artifactId: null,
      task: {
        taskId,
        status: 'missing',
        warningCount: 0,
        hasHighSeverity: false,
      },
    };
  }

  private normalizeWarnings(rows: Record<string, unknown>[]): ExecutionWorkbenchWarning[] {
    return rows.map((row, index) => {
      const severityRaw = String(row.severity ?? row.level ?? '').trim().toLowerCase();
      const severity = severityRaw === 'high' || severityRaw === 'medium' || severityRaw === 'low'
        ? severityRaw
        : 'unknown';
      const title = this.toStringValue(row.title ?? row.reason ?? row.metric ?? row.type)
        ?? `执行告警 ${index + 1}`;
      return {
        id: this.toStringValue(row.id) ?? `warning-${index + 1}`,
        severity,
        title,
        message: this.toStringValue(row.message ?? row.detail ?? row.description ?? row.note),
        metric: this.toStringValue(row.metric ?? row.type),
        actual: this.toNum(row.actual ?? row.value ?? row.current ?? row.participation_rate ?? row.cost_ratio),
        threshold: this.toNum(row.threshold ?? row.limit ?? row.max ?? row.max_participation_rate ?? row.max_cost_ratio),
        suggestedAction: this.toStringValue(row.recommended_action ?? row.action ?? row.suggestion),
      };
    });
  }

  private normalizeTaskList(value: unknown): ExecutionTaskListItem[] {
    return this.asRecordArray(value).map((item) => this.normalizeTaskBrief(item));
  }

  private normalizeTaskBrief(task: Record<string, unknown>): ExecutionTaskListItem {
    return {
      taskId: this.toStringValue(task.task_id ?? task.taskId) ?? 'unknown-task',
      artifactId: this.toStringValue(task.artifact_id ?? task.artifactId),
      algorithm: this.toStringValue(task.algorithm),
      code: this.toStringValue(task.code),
      status: this.toStringValue(task.status),
      createdAt: this.toStringValue(task.created_at ?? task.createdAt),
      totalShares: this.toNum(task.total_shares ?? task.totalShares ?? task.total_quantity ?? task.totalQuantity),
      durationMinutes: this.toNum(task.duration_minutes ?? task.durationMinutes),
      softGateProfile: this.toStringValue(task.soft_gate_profile ?? task.softGateProfile),
      warningCount: this.toInt(task.warning_count ?? task.warningCount) ?? 0,
      hasHighSeverity: this.toBoolean(task.has_high_severity ?? task.hasHighSeverity) ?? false,
      executionFeasible: this.toBoolean(task.execution_feasible ?? task.executionFeasible),
      executionBlocking: this.toBoolean(task.execution_blocking ?? task.executionBlocking),
    };
  }

  private async callManager(action: string, params: Record<string, unknown>) {
    try {
      const result = await this.mcpGatewayService.callTool('execution_manager', {
        action,
        kwargs: JSON.stringify(params),
      });
      const toolError = this.extractToolError(result);
      if (toolError) {
        throw new Error(toolError);
      }
      return result;
    } catch (error) {
      throw new BadGatewayException({
        success: false,
        message: `调用 MCP execution_manager.${action} 失败`,
        detail: error instanceof Error ? error.message : String(error),
      });
    }
  }

  private async callLiveManager(action: string, params: Record<string, unknown> = {}) {
    try {
      const result = await this.mcpGatewayService.callTool('live_trading_manager', {
        action,
        kwargs: JSON.stringify(params),
      });
      const toolError = this.extractToolError(result);
      if (toolError) {
        throw new Error(toolError);
      }
      return this.extractDataRecord(result);
    } catch (error) {
      throw new BadGatewayException({
        success: false,
        message: `调用 MCP live_trading_manager.${action} 失败`,
        detail: error instanceof Error ? error.message : String(error),
      });
    }
  }

  private extractToolError(payload: unknown): string | null {
    if (typeof payload === 'string') {
      return /error executing tool|validation error/i.test(payload) ? payload : null;
    }
    if (!payload || typeof payload !== 'object') {
      return null;
    }
    const record = payload as Record<string, unknown>;
    if (record.success === false) {
      return String(record.error ?? record.message ?? 'execution manager error');
    }
    if (typeof record.data === 'string' && /error executing tool|validation error/i.test(record.data)) {
      return record.data;
    }
    return null;
  }

  private extractExceptionDetail(error: unknown): string | null {
    if (error instanceof BadGatewayException) {
      const response = error.getResponse();
      if (response && typeof response === 'object') {
        const detail = (response as { detail?: unknown }).detail;
        if (typeof detail === 'string' && detail.trim()) {
          return detail;
        }
        const message = (response as { message?: unknown }).message;
        if (typeof message === 'string' && message.trim()) {
          return message;
        }
      }
    }
    if (error instanceof Error && error.message.trim()) {
      return error.message;
    }
    return null;
  }

  private isTaskNotFoundError(error: unknown) {
    const detail = this.extractExceptionDetail(error);
    return typeof detail === 'string' && /task not found/i.test(detail);
  }

  private extractDataRecord(payload: unknown): Record<string, unknown> {
    if (!payload || typeof payload !== 'object' || Array.isArray(payload)) {
      return {};
    }
    const record = payload as Record<string, unknown>;
    const data = record.data;
    return data && typeof data === 'object' && !Array.isArray(data) ? data as Record<string, unknown> : record;
  }

  private normalizeOrders(rows: Record<string, unknown>[]): ExecutionWorkbenchOrderItem[] {
    return rows.slice(0, 5).map((row, index) => ({
      id: this.toStringValue(row.id ?? row.order_id) ?? `order-${index + 1}`,
      code: this.toStringValue(row.code ?? row.stock_code),
      direction: this.toStringValue(row.direction ?? row.trade_type ?? row.side),
      quantity: this.toNum(row.quantity ?? row.shares),
      price: this.toNum(row.price),
      status: this.toStringValue(row.status),
      createdAt: this.toStringValue(row.created_at ?? row.trade_time ?? row.updated_at),
    }));
  }

  private asRecord(value: unknown): Record<string, unknown> {
    if (!value || typeof value !== 'object' || Array.isArray(value)) {
      return {};
    }
    return value as Record<string, unknown>;
  }

  private asRecordArray(value: unknown): Record<string, unknown>[] {
    if (!Array.isArray(value)) return [];
    return value
      .filter((item): item is Record<string, unknown> => Boolean(item) && typeof item === 'object' && !Array.isArray(item));
  }

  private toStringValue(value: unknown): string | null {
    if (value == null) return null;
    const text = String(value).trim();
    return text ? text : null;
  }

  private toNum(value: unknown): number | null {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : null;
  }

  private toInt(value: unknown): number | null {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? Math.trunc(parsed) : null;
  }

  private toBoolean(value: unknown): boolean | undefined {
    return typeof value === 'boolean' ? value : undefined;
  }

  private toTime(value: unknown) {
    const text = this.toStringValue(value);
    if (!text) return 0;
    const parsed = Date.parse(text);
    return Number.isFinite(parsed) ? parsed : 0;
  }
}
