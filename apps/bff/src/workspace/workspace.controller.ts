import { Body, Controller, Get, Put, Req } from '@nestjs/common';
import type { WorkspaceStateSnapshot } from '@aiask/shared-types';
import { WorkspaceService } from './workspace.service';

type RequestWithUser = {
  traceId?: string;
  headers?: Record<string, string | undefined>;
  user?: { id?: string; sub?: string };
};

@Controller('workspace')
export class WorkspaceController {
  constructor(private readonly workspaceService: WorkspaceService) {}

  private userId(req: RequestWithUser) {
    return String(req.user?.sub ?? req.user?.id ?? 'default');
  }

  private traceId(req: RequestWithUser) {
    return String(req.traceId || req.headers?.['x-trace-id'] || req.headers?.['x-request-id'] || 'UNKNOWN');
  }

  @Get('state')
  async getState(@Req() req: RequestWithUser) {
    const data = await this.workspaceService.getState(this.userId(req));
    return { success: true, data, traceId: this.traceId(req) };
  }

  @Put('state')
  async saveState(@Body() body: WorkspaceStateSnapshot | Record<string, unknown>, @Req() req: RequestWithUser) {
    const data = await this.workspaceService.saveState(this.userId(req), body);
    return { success: true, data, traceId: this.traceId(req) };
  }
}
