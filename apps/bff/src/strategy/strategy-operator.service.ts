import { BadGatewayException, BadRequestException, Injectable, NotFoundException } from '@nestjs/common';
import type {
  McpJobRecord,
  StrategyManagerAction,
  StrategyOperatorJobRecord,
  StrategyOperatorJobRequest,
  StrategyOperatorParityResponse,
} from '@aiask/shared-types';
import { McpGatewayService } from '../mcp-gateway/mcp-gateway.service';
import { McpJobsService } from '../mcp-jobs/mcp-jobs.service';
import { DbService } from '../db/db.service';
import {
  buildStrategyOperatorParity,
  isStrategyOperatorJobAction,
} from './strategy.operator-contract';

const STRATEGY_FACTORY_WORKER_TASK_SCOPE = 'strategy_factory.worker';
const STRATEGY_FACTORY_WORKER_ACTIONS = new Set<StrategyManagerAction>([
  'factory_run_once',
  'factory_dispatch_run',
  'incubation_sync_run',
  'incubation_pipeline_run',
  'promotion_review_run',
  'risk_scan_run',
  'runtime_cycle_run',
  'vector_rebuild',
  'vector_reconcile',
  'vector_cleanup',
  'domain_projection_rebuild',
  'ai_generate',
]);

@Injectable()
export class StrategyOperatorService {
  constructor(
    private readonly mcp: McpGatewayService,
    private readonly jobs: McpJobsService,
    private readonly db: DbService,
  ) {}

  parity(): StrategyOperatorParityResponse {
    return buildStrategyOperatorParity();
  }

  async executionAuditVerification(params: { strategy_id?: string | null } = {}) {
    const strategyId = String(params.strategy_id ?? '').trim();
    try {
      const result = await this.callStrategyManager('execution_audit_verification', {
        ...(strategyId ? { strategy_id: strategyId } : {}),
      });
      return {
        strategy_id: strategyId || null,
        verification: result,
        read_only: true,
        source_action: 'execution_audit_verification',
        available: true,
        degraded: false,
      };
    } catch (error) {
      return {
        strategy_id: strategyId || null,
        verification: null,
        read_only: true,
        source_action: 'execution_audit_verification',
        available: false,
        degraded: true,
        error: this.toReadDegradation('execution_audit_verification', error),
      };
    }
  }

  async createOperatorJob(
    input: StrategyOperatorJobRequest,
    context: { traceId?: string | null } = {},
  ): Promise<StrategyOperatorJobRecord> {
    const action = String(input.action ?? '').trim() as StrategyManagerAction;
    if (!isStrategyOperatorJobAction(action)) {
      throw new BadRequestException({
        code: 'STRATEGY_OPERATOR_ACTION_NOT_ALLOWED',
        message: `动作 ${action || '<empty>'} 不允许通过运营任务触发`,
        detail: {
          action,
          allowed_actions: this.allowedActions(),
        },
      });
    }

    if (!input.confirmed || String(input.confirmation_text ?? '').trim() !== action) {
      throw new BadRequestException({
        code: 'STRATEGY_OPERATOR_CONFIRMATION_REQUIRED',
        message: '高权限策略工厂动作需要二次确认',
        detail: {
          action,
          required_confirmation_text: action,
        },
      });
    }

    const strategyId = String(input.strategy_id ?? '').trim();
    const params = {
      ...(input.params && typeof input.params === 'object' && !Array.isArray(input.params) ? input.params : {}),
      ...(strategyId ? { strategy_id: strategyId } : {}),
      ...(input.reason ? { operator_reason: String(input.reason).trim() } : {}),
      source: String((input.params as Record<string, unknown> | undefined)?.source ?? 'strategy_operator_console'),
    };

    if (STRATEGY_FACTORY_WORKER_ACTIONS.has(action)) {
      return this.enqueueStrategyFactoryWorkerTaskRun(action, {
        ...params,
        ...(input.idempotency_key ? { idempotency_key: input.idempotency_key } : {}),
        ...(context.traceId ? { trace_id: context.traceId } : {}),
      });
    }

    const accepted = await this.jobs.createToolJob(
      {
        tool_name: 'strategy_manager',
        arguments: {
          action,
          params,
        },
        timeout_ms: input.timeout_ms ?? undefined,
        idempotency_key: input.idempotency_key ?? undefined,
      },
      { traceId: context.traceId ?? undefined },
    );

    return this.toOperatorJobRecord(accepted.job, {
      accepted: accepted.accepted,
      deduplicated: accepted.deduplicated,
    });
  }

  async getOperatorJob(jobId: string): Promise<StrategyOperatorJobRecord> {
    const normalizedJobId = String(jobId ?? '').trim();
    if (/^\d+$/.test(normalizedJobId)) {
      const taskRun = await this.getStrategyTaskRunFromDb(Number(normalizedJobId));
      return this.toOperatorTaskRunRecord(taskRun, {
        accepted: true,
        deduplicated: false,
      });
    }
    const job = await this.jobs.getJobOrThrow(jobId);
    return this.toOperatorJobRecord(job, { accepted: true, deduplicated: false });
  }

  allowedActions() {
    return this.parity().coverage
      .filter((item) => item.job_action)
      .map((item) => item.action);
  }

  private async callStrategyManager(action: StrategyManagerAction, params: Record<string, unknown>) {
    try {
      const payload = await this.mcp.callTool('strategy_manager', { action, params });
      if (!payload || typeof payload !== 'object') return payload;
      const record = payload as Record<string, unknown>;
      if (record.success === false) {
        const message = String(record.error || record.message || `${action} failed`);
        if (String(record.error_code ?? '') === 'STRATEGY_MANAGER_NOT_FOUND') {
          throw new NotFoundException(message);
        }
        throw new BadGatewayException({
          code: record.error_code || 'STRATEGY_MANAGER_BACKEND_ERROR',
          message,
          detail: record.detail,
        });
      }
      return 'data' in record ? record.data : record;
    } catch (error) {
      if (
        error instanceof NotFoundException ||
        error instanceof BadGatewayException ||
        error instanceof BadRequestException
      ) {
        throw error;
      }
      throw new BadGatewayException({
        code: 'STRATEGY_OPERATOR_MCP_CALL_FAILED',
        message: `调用 strategy_manager.${action} 失败`,
        detail: String(error instanceof Error ? error.message : error),
      });
    }
  }

  private async enqueueStrategyFactoryWorkerTaskRun(
    action: StrategyManagerAction,
    params: Record<string, unknown>,
  ): Promise<StrategyOperatorJobRecord> {
    const idempotencyKey = String(params.idempotency_key ?? '').trim();
    if (idempotencyKey) {
      const existing = await this.db.query<Record<string, unknown>>(
        `
          SELECT *
            FROM strategy_task_runs
           WHERE task_scope = $1
             AND task_name = $2
             AND task_key = $3
           ORDER BY id DESC
           LIMIT 1
        `,
        [STRATEGY_FACTORY_WORKER_TASK_SCOPE, action, idempotencyKey],
      );
      const row = existing.rows[0];
      if (row) {
        return this.toOperatorTaskRunRecord(row, {
          fallbackAction: action,
          fallbackParams: params,
          accepted: true,
          deduplicated: true,
        });
      }
    }

    const strategyId = String(params.strategy_id ?? params.id ?? '').trim() || null;
    const traceId = String(params.trace_id ?? params.request_id ?? '').trim() || null;
    const submittedAt = new Date().toISOString();
    const payload = {
      action,
      params,
      queue_backend: 'db',
      task_scope: STRATEGY_FACTORY_WORKER_TASK_SCOPE,
      submitted_at: submittedAt,
      source: String(params.source ?? 'strategy_operator_console'),
    };
    const inserted = await this.db.query<Record<string, unknown>>(
      `
        INSERT INTO strategy_task_runs (
          strategy_id,
          task_name,
          task_scope,
          task_key,
          status,
          trace_id,
          payload,
          result,
          started_at
        )
        VALUES ($1, $2, $3, $4, 'queued', $5, $6::jsonb, '{}'::jsonb, $7)
        RETURNING *
      `,
      [
        strategyId,
        action,
        STRATEGY_FACTORY_WORKER_TASK_SCOPE,
        idempotencyKey || null,
        traceId,
        JSON.stringify(payload),
        submittedAt,
      ],
    );
    const taskRun = inserted.rows[0];
    if (!taskRun) {
      throw new BadGatewayException({
        code: 'STRATEGY_OPERATOR_TASK_RUN_INSERT_FAILED',
        message: '策略工厂任务入队失败',
        detail: { action },
      });
    }
    return this.toOperatorTaskRunRecord(taskRun, {
      fallbackAction: action,
      fallbackParams: params,
      accepted: true,
      deduplicated: false,
    });
  }

  private async getStrategyTaskRunFromDb(taskRunId: number): Promise<Record<string, unknown>> {
    const result = await this.db.query<Record<string, unknown>>(
      'SELECT * FROM strategy_task_runs WHERE id = $1',
      [taskRunId],
    );
    const row = result.rows[0];
    if (!row) {
      throw new NotFoundException({
        code: 'STRATEGY_OPERATOR_TASK_RUN_NOT_FOUND',
        message: `策略工厂任务 ${taskRunId} 不存在`,
      });
    }
    return row;
  }

  private toReadDegradation(action: StrategyManagerAction, error: unknown) {
    const response =
      error && typeof error === 'object' && 'getResponse' in error && typeof error.getResponse === 'function'
        ? error.getResponse()
        : null;
    const responseRecord =
      response && typeof response === 'object' && !Array.isArray(response)
        ? (response as Record<string, unknown>)
        : {};
    return {
      code: String(responseRecord.code ?? 'STRATEGY_OPERATOR_READ_DEGRADED'),
      message: String(responseRecord.message ?? `读取 strategy_manager.${action} 失败`),
      detail: responseRecord.detail ?? (error instanceof Error ? error.message : String(error)),
    };
  }

  private asRecord(value: unknown): Record<string, unknown> {
    return value && typeof value === 'object' && !Array.isArray(value)
      ? (value as Record<string, unknown>)
      : {};
  }

  private mapTaskRunStatus(status: string): McpJobRecord['status'] {
    const normalized = String(status || '').trim().toLowerCase();
    if (normalized === 'queued') return 'queued';
    if (normalized === 'running') return 'running';
    if (['completed', 'complete', 'success', 'succeeded'].includes(normalized)) return 'succeeded';
    if (['failed', 'error', 'cancelled', 'canceled'].includes(normalized)) return 'failed';
    return 'running';
  }

  private terminalTaskRunStatus(status: McpJobRecord['status']) {
    return status === 'succeeded' || status === 'failed';
  }

  private normalizeTaskRunResult(result: unknown) {
    const root = this.asRecord(result);
    const nestedResult = this.asRecord(root.result);
    if (Object.keys(nestedResult).length === 0) {
      return result ?? null;
    }
    return {
      ...nestedResult,
      task_run_action: root.action ?? null,
      handler_action: root.handler_action ?? null,
    };
  }

  private toOperatorTaskRunRecord(
    payload: unknown,
    flags: {
      fallbackAction?: StrategyManagerAction;
      fallbackParams?: Record<string, unknown>;
      accepted: boolean;
      deduplicated: boolean;
    },
  ): StrategyOperatorJobRecord {
    const root = this.asRecord(payload);
    const taskRun = this.asRecord(root.task_run ?? root.item ?? root);
    const rawId = taskRun.id ?? root.task_run_id ?? root.job_id;
    const jobId = String(rawId ?? '').trim();
    if (!jobId) {
      throw new BadGatewayException({
        code: 'STRATEGY_OPERATOR_TASK_RUN_MISSING',
        message: 'strategy_manager 没有返回可轮询的 task_run/job_id',
        detail: root,
      });
    }

    const payloadRecord = this.asRecord(taskRun.payload);
    const params = {
      ...(flags.fallbackParams ?? {}),
      ...this.asRecord(payloadRecord.params),
    };
    const action = String(
      payloadRecord.action ?? taskRun.task_name ?? flags.fallbackAction ?? '',
    ).trim() as StrategyManagerAction;
    const status = this.mapTaskRunStatus(String(taskRun.status ?? root.status ?? 'queued'));
    const submittedAt = String(payloadRecord.submitted_at ?? taskRun.started_at ?? new Date().toISOString());
    const startedAt = status === 'queued' ? null : String(taskRun.started_at ?? submittedAt);
    const completedAt = this.terminalTaskRunStatus(status)
      ? String(taskRun.completed_at ?? new Date().toISOString())
      : null;
    const error = String(taskRun.error ?? root.error ?? '').trim() || null;
    const pollPath = String(root.poll_path ?? `/api/strategy-market/operator/jobs/${jobId}`);
    const job: McpJobRecord = {
      job_id: jobId,
      status,
      submitted_at: submittedAt,
      started_at: startedAt,
      completed_at: completedAt,
      poll_path: pollPath,
      idempotency_key: String(taskRun.task_key ?? params.idempotency_key ?? '').trim() || null,
      target: {
        kind: 'tool',
        name: 'strategy_manager',
        arguments: { action, params },
        timeout_ms: 0,
      },
      result: this.normalizeTaskRunResult(taskRun.result),
      error,
      error_code: status === 'failed' ? 'MCP_JOB_EXECUTION_FAILED' : null,
      trace_id: String(taskRun.trace_id ?? params.trace_id ?? '').trim() || null,
      meta: {
        queue_backend: 'db',
        task_scope: String(taskRun.task_scope ?? 'strategy_factory.worker'),
        task_run_id: Number(jobId),
        raw_task_status: taskRun.status ?? null,
      },
    };

    const strategyId = String(taskRun.strategy_id ?? params.strategy_id ?? '').trim() || null;
    return {
      job,
      action,
      strategy_id: strategyId,
      accepted: flags.accepted,
      deduplicated: flags.deduplicated,
      requires_admin: true,
      confirmation_required: true,
      poll_path: pollPath,
      submitted_params: params,
    };
  }

  private toOperatorJobRecord(
    job: McpJobRecord,
    flags: { accepted: boolean; deduplicated: boolean },
  ): StrategyOperatorJobRecord {
    const targetArguments =
      job.target.arguments && typeof job.target.arguments === 'object' && !Array.isArray(job.target.arguments)
        ? (job.target.arguments as Record<string, unknown>)
        : {};
    const action = String(targetArguments.action ?? '').trim() as StrategyManagerAction;
    const params =
      targetArguments.params && typeof targetArguments.params === 'object' && !Array.isArray(targetArguments.params)
        ? (targetArguments.params as Record<string, unknown>)
        : {};
    const strategyId = String(params.strategy_id ?? '').trim() || null;
    return {
      job,
      action,
      strategy_id: strategyId,
      accepted: flags.accepted,
      deduplicated: flags.deduplicated,
      requires_admin: true,
      confirmation_required: true,
      poll_path: `/api/strategy-market/operator/jobs/${job.job_id}`,
      submitted_params: params,
    };
  }
}
