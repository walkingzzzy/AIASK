import { Controller, Get, Header, Req, Res } from '@nestjs/common';
import type { Response } from 'express';
import { HealthService } from '../health/health.service';
import { ObservabilityService } from './observability.service';
import { Public } from '../rbac/public.decorator';

@Public()
@Controller()
export class ObservabilityController {
  constructor(
    private readonly observability: ObservabilityService,
    private readonly healthService: HealthService,
  ) {}

  @Get('metrics')
  @Header('Cache-Control', 'no-store')
  async metrics(
    @Res({ passthrough: true }) res: Response,
    @Req() req: { traceId?: string; headers?: Record<string, string | undefined> },
  ) {
    await this.healthService.getHealth().catch(() => null);
    const body = await this.observability.metrics();
    res.setHeader('Content-Type', this.observability.contentType());
    res.setHeader('X-Trace-Id', String(
      req.traceId || req.headers?.['x-trace-id'] || req.headers?.['x-request-id'] || 'UNKNOWN',
    ));
    return body;
  }
}
