import { Injectable, Logger, NotFoundException } from '@nestjs/common';
import { randomUUID } from 'node:crypto';
import type {
  CreateMcpToolJobInput,
  McpJobAcceptedResponse,
  McpJobErrorCode,
  McpJobRecord,
  McpJobStatus,
} from '@aiask/shared-types';
import { CommonCacheService } from '../common/cache.service';
import { McpGatewayService } from '../mcp-gateway/mcp-gateway.service';
import { McpGatewayTimeoutError } from '../mcp-gateway/mcp-gateway.errors';
import { toMcpTransportSnapshot } from '../mcp-gateway/mcp-transport.contract';

const ALLOWED_JOB_TRANSITIONS: Record<McpJobStatus, readonly McpJobStatus[]> = {
  queued: ['queued', 'running', 'failed'],
  running: ['running', 'succeeded', 'failed'],
  succeeded: ['succeeded'],
  failed: ['failed'],
};

@Injectable()
export class McpJobsService {
  private static readonly JOB_TTL_SECONDS = 15 * 60;
  private readonly logger = new Logger(McpJobsService.name);
  private readonly activeJobs = new Map<string, Promise<void>>();

  constructor(
    private readonly mcp: McpGatewayService,
    private readonly cache: CommonCacheService,
  ) {}

  async createToolJob(
    input: CreateMcpToolJobInput,
    options: {
      traceId?: string | null;
    } = {},
  ): Promise<McpJobAcceptedResponse> {
    const normalizedKey = String(input.idempotency_key ?? '').trim();
    if (normalizedKey) {
      const existingJobId = await this.cache.get<string>(this.idempotencyCacheKey(normalizedKey));
      if (existingJobId) {
        const existingJob = await this.getJob(existingJobId);
        if (existingJob) {
          return {
            accepted: true,
            deduplicated: true,
            job: existingJob,
          };
        }
      }
    }

    const jobId = randomUUID();
    const now = new Date().toISOString();
    const timeoutMs = this.mcp.resolveToolTimeoutMs(input.timeout_ms);
    const job: McpJobRecord = {
      job_id: jobId,
      status: 'queued',
      submitted_at: now,
      started_at: null,
      completed_at: null,
      poll_path: `/api/mcp/jobs/${jobId}`,
      idempotency_key: normalizedKey || null,
      target: {
        kind: 'tool',
        name: String(input.tool_name || '').trim(),
        arguments: input.arguments ?? {},
        timeout_ms: timeoutMs,
      },
      result: null,
      error: null,
      error_code: null,
      trace_id: options.traceId ?? null,
      meta: {
        transport: toMcpTransportSnapshot(this.mcp.getTransportSnapshot()),
      },
    };

    await this.persistJob(job);
    if (normalizedKey) {
      await this.cache.set(
        this.idempotencyCacheKey(normalizedKey),
        job.job_id,
        this.resolveJobTtlSeconds(),
      );
    }

    const runner = this.runToolJob(job);
    this.activeJobs.set(job.job_id, runner);
    void runner.finally(() => {
      this.activeJobs.delete(job.job_id);
    });

    return {
      accepted: true,
      deduplicated: false,
      job,
    };
  }

  async getJobOrThrow(jobId: string): Promise<McpJobRecord> {
    const job = await this.getJob(jobId);
    if (!job) {
      throw new NotFoundException(`MCP job ${jobId} 不存在`);
    }
    return job;
  }

  async getJob(jobId: string): Promise<McpJobRecord | null> {
    return this.cache.get<McpJobRecord>(this.jobCacheKey(jobId));
  }

  private async runToolJob(job: McpJobRecord): Promise<void> {
    const startedAt = new Date().toISOString();
    await this.persistJob(this.withTransportSnapshot({
      ...job,
      status: 'running',
      started_at: startedAt,
      completed_at: null,
    }));

    try {
      const result = await this.mcp.callTool(
        job.target.name,
        (job.target.arguments ?? {}) as Record<string, unknown>,
        {
          timeoutMs: job.target.timeout_ms,
        },
      );
      await this.persistJob(this.withTransportSnapshot({
        ...job,
        status: 'succeeded',
        started_at: startedAt,
        completed_at: new Date().toISOString(),
        result,
        error: null,
        error_code: null,
      }));
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      this.logger.warn(`MCP job failed job_id=${job.job_id} tool=${job.target.name}: ${message}`);
      await this.persistJob(this.withTransportSnapshot({
        ...job,
        status: 'failed',
        started_at: startedAt,
        completed_at: new Date().toISOString(),
        result: null,
        error: message,
        error_code: this.resolveJobErrorCode(error),
      }));
    }
  }

  private async persistJob(job: McpJobRecord): Promise<void> {
    const previous = await this.cache.get<McpJobRecord>(this.jobCacheKey(job.job_id));
    this.assertJobShape(job);
    this.assertJobTransition(previous, job);
    await this.cache.set(this.jobCacheKey(job.job_id), job, this.resolveJobTtlSeconds());
  }

  private withTransportSnapshot(job: McpJobRecord): McpJobRecord {
    return {
      ...job,
      meta: {
        ...(job.meta ?? {}),
        transport: toMcpTransportSnapshot(this.mcp.getTransportSnapshot()),
      },
    };
  }

  private resolveJobErrorCode(error: unknown): McpJobErrorCode {
    if (error instanceof McpGatewayTimeoutError && error.scope === 'tool_call') {
      return 'MCP_JOB_TIMEOUT';
    }

    const message = String(error instanceof Error ? error.message : error).toLowerCase();
    if (message.includes('timed out after')) {
      return 'MCP_JOB_TIMEOUT';
    }

    const transport = toMcpTransportSnapshot(this.mcp.getTransportSnapshot());
    if (
      transport.active_transport === 'none' ||
      message.includes('unable to establish mcp connection') ||
      message.includes('mcp not reachable') ||
      message.includes('econnrefused') ||
      message.includes('econnreset')
    ) {
      return 'MCP_JOB_TRANSPORT_UNAVAILABLE';
    }

    return 'MCP_JOB_EXECUTION_FAILED';
  }

  private assertJobShape(job: McpJobRecord) {
    if (job.status === 'queued' && (job.started_at || job.completed_at)) {
      throw new Error(`Queued MCP job ${job.job_id} cannot have lifecycle timestamps`);
    }
    if (job.status === 'running' && (!job.started_at || job.completed_at)) {
      throw new Error(`Running MCP job ${job.job_id} must have started_at and no completed_at`);
    }
    if ((job.status === 'succeeded' || job.status === 'failed') && !job.completed_at) {
      throw new Error(`Terminal MCP job ${job.job_id} must have completed_at`);
    }
    if ((job.status === 'succeeded' || job.status === 'failed') && !job.started_at) {
      throw new Error(`Terminal MCP job ${job.job_id} must preserve started_at`);
    }
  }

  private assertJobTransition(previous: McpJobRecord | null, next: McpJobRecord) {
    if (!previous) {
      if (next.status !== 'queued') {
        throw new Error(`Initial MCP job state must be queued, received ${next.status}`);
      }
      return;
    }

    if (!ALLOWED_JOB_TRANSITIONS[previous.status].includes(next.status)) {
      throw new Error(
        `Invalid MCP job transition ${previous.status} -> ${next.status} for ${next.job_id}`,
      );
    }
  }

  private resolveJobTtlSeconds() {
    return this.cache.resolveTtl('mcp.jobs', McpJobsService.JOB_TTL_SECONDS);
  }

  private jobCacheKey(jobId: string) {
    return `mcp:jobs:${jobId}`;
  }

  private idempotencyCacheKey(idempotencyKey: string) {
    return `mcp:jobs:idempotency:${idempotencyKey}`;
  }
}
