import { BadRequestException, Body, Controller, Get, Param, Post, Req } from '@nestjs/common';
import { Roles } from '../rbac/roles.decorator';
import { CreateMcpToolJobDto, GetMcpJobDto } from './mcp-jobs.dto';
import { McpJobsService } from './mcp-jobs.service';

type Req_ = {
  traceId?: string;
  headers?: Record<string, string | string[] | undefined>;
};

function header(req: Req_, name: string) {
  const candidate = req?.headers?.[name];
  return Array.isArray(candidate) ? candidate[0] : candidate;
}

function tid(req: Req_) {
  return String(
    req.traceId ||
    header(req, 'x-trace-id') ||
    header(req, 'x-request-id') ||
    'UNKNOWN',
  );
}

function normalizeOptionalString(value: string | undefined) {
  const normalized = String(value ?? '').trim();
  return normalized.length > 0 ? normalized : null;
}

function requestIdempotencyKey(req: Req_) {
  return normalizeOptionalString(
    header(req, 'idempotency-key') || header(req, 'x-idempotency-key'),
  );
}

@Controller('mcp/jobs')
export class McpJobsController {
  constructor(private readonly jobs: McpJobsService) {}

  @Post()
  @Roles('admin')
  async createToolJob(@Body() body: CreateMcpToolJobDto, @Req() req: Req_) {
    const traceId = tid(req);
    const bodyIdempotencyKey = normalizeOptionalString(body.idempotency_key);
    const headerIdempotencyKey = requestIdempotencyKey(req);

    if (
      bodyIdempotencyKey &&
      headerIdempotencyKey &&
      bodyIdempotencyKey !== headerIdempotencyKey
    ) {
      throw new BadRequestException({
        code: 'MCP_JOB_IDEMPOTENCY_KEY_MISMATCH',
        message: '请求体与请求头中的 idempotency key 不一致',
        detail: {
          body_idempotency_key: bodyIdempotencyKey,
          header_idempotency_key: headerIdempotencyKey,
        },
      });
    }

    const data = await this.jobs.createToolJob(
      {
        ...body,
        idempotency_key: bodyIdempotencyKey ?? headerIdempotencyKey ?? undefined,
      },
      { traceId },
    );
    return { success: true, data, traceId };
  }

  @Get(':jobId')
  @Roles('admin')
  async getJob(@Param() params: GetMcpJobDto, @Req() req: Req_) {
    const traceId = tid(req);
    const data = await this.jobs.getJobOrThrow(params.jobId);
    return { success: true, data, traceId };
  }
}
