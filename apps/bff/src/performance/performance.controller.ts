import { Controller, Get, Query, Req } from '@nestjs/common';
import { IsNumberString, IsOptional, IsString } from 'class-validator';
import { PerformanceService } from './performance.service';

class PerformanceQueryDto {
  @IsOptional()
  @IsNumberString({}, { message: 'portfolioId 必须为数字字符串' })
  portfolioId?: string;

  @IsOptional()
  @IsNumberString({}, { message: 'lookbackDays 必须为数字字符串' })
  lookbackDays?: string;

  @IsOptional()
  @IsString()
  benchmark?: string;
}

@Controller('performance')
export class PerformanceController {
  constructor(private readonly performanceService: PerformanceService) {}

  private userId(req: { user?: { id?: string; sub?: string } }) {
    return String(req.user?.sub ?? req.user?.id ?? 'default');
  }

  @Get('attribution')
  async attribution(
    @Query() query: PerformanceQueryDto,
    @Req() req: { traceId?: string; headers?: Record<string, string | undefined>; user?: { id?: string; sub?: string } },
  ) {
    const data = await this.performanceService.attribution(
      this.userId(req),
      query.portfolioId ? Number(query.portfolioId) : undefined,
      query.lookbackDays ? Number(query.lookbackDays) : undefined,
      query.benchmark ?? '000300',
    );
    const traceId =
      req.traceId || req.headers?.['x-trace-id'] || req.headers?.['x-request-id'] || 'UNKNOWN';
    return { success: true, data, traceId: String(traceId) };
  }

  @Get('benchmark-comparison')
  async benchmarkComparison(
    @Query() query: PerformanceQueryDto,
    @Req() req: { traceId?: string; headers?: Record<string, string | undefined>; user?: { id?: string; sub?: string } },
  ) {
    const data = await this.performanceService.benchmarkComparison(
      this.userId(req),
      query.portfolioId ? Number(query.portfolioId) : undefined,
      query.lookbackDays ? Number(query.lookbackDays) : undefined,
      query.benchmark ?? '000300',
    );
    const traceId =
      req.traceId || req.headers?.['x-trace-id'] || req.headers?.['x-request-id'] || 'UNKNOWN';
    return { success: true, data, traceId: String(traceId) };
  }
}
