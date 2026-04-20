import { Body, Controller, Get, Param, Post, Req } from '@nestjs/common';
import { Roles } from '../rbac/roles.decorator';
import { CreateMcpToolJobDto } from './mcp-jobs.dto';
import { McpJobsService } from './mcp-jobs.service';

type Req_ = {
  headers?: Record<string, string | string[] | undefined>;
};

function tid(req: Req_) {
  const candidate = req?.headers?.['x-trace-id'];
  return Array.isArray(candidate) ? candidate[0] : candidate;
}

@Controller('mcp/jobs')
export class McpJobsController {
  constructor(private readonly jobs: McpJobsService) {}

  @Post()
  @Roles('admin')
  async createToolJob(@Body() body: CreateMcpToolJobDto, @Req() req: Req_) {
    const data = await this.jobs.createToolJob(body);
    return { success: true, data, traceId: tid(req) };
  }

  @Get(':jobId')
  @Roles('admin')
  async getJob(@Param('jobId') jobId: string, @Req() req: Req_) {
    const data = await this.jobs.getJobOrThrow(jobId);
    return { success: true, data, traceId: tid(req) };
  }
}
