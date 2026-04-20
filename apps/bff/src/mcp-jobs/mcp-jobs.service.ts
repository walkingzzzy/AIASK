import { Injectable, Logger, NotFoundException } from '@nestjs/common';
import { randomUUID } from 'node:crypto';
import type { McpJobAcceptedResponse, McpJobRecord } from '@aiask/shared-types';
import { CommonCacheService } from '../common/cache.service';
import { McpGatewayService } from '../mcp-gateway/mcp-gateway.service';
import type { CreateMcpToolJobDto } from './mcp-jobs.dto';

@Injectable()
export class McpJobsService {
  private static readonly JOB_TTL_SECONDS = 15 * 60;
  private readonly logger = new Logger(McpJobsService.name);
  private readonly activeJobs = new Map<string, Promise<void>>();

  constructor(
    private readonly mcp: McpGatewayService,
    private readonly cache: CommonCacheService,
  ) {}

  async createToolJob(input: CreateMcpToolJobDto): Promise<McpJobAcceptedResponse> {
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
        timeout_ms: input.timeout_ms ?? null,
      },
      result: null,
      error: null,
      error_code: null,
      trace_id: null,
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
    await this.persistJob({
      ...job,
      status: 'running',
      started_at: startedAt,
      completed_at: null,
    });

    try {
      const result = await this.mcp.callTool(
        job.target.name,
        (job.target.arguments ?? {}) as Record<string, unknown>,
        {
          timeoutMs: Number(job.target.timeout_ms) || undefined,
        },
      );
      await this.persistJob({
        ...job,
        status: 'succeeded',
        started_at: startedAt,
        completed_at: new Date().toISOString(),
        result,
        error: null,
        error_code: null,
      });
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      this.logger.warn(`MCP job failed job_id=${job.job_id} tool=${job.target.name}: ${message}`);
      await this.persistJob({
        ...job,
        status: 'failed',
        started_at: startedAt,
        completed_at: new Date().toISOString(),
        result: null,
        error: message,
        error_code: 'MCP_JOB_EXECUTION_FAILED',
      });
    }
  }

  private async persistJob(job: McpJobRecord): Promise<void> {
    await this.cache.set(this.jobCacheKey(job.job_id), job, this.resolveJobTtlSeconds());
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
