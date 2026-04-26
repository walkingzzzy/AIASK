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
import {
  buildStrategyOperatorParity,
  isStrategyOperatorJobAction,
} from './strategy.operator-contract';

@Injectable()
export class StrategyOperatorService {
  constructor(
    private readonly mcp: McpGatewayService,
    private readonly jobs: McpJobsService,
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
