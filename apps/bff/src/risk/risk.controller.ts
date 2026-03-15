import { Controller, Get, Query, Req } from '@nestjs/common';
import { IsIn, IsNumberString, IsOptional } from 'class-validator';
import { RiskService } from './risk.service';

class RiskQueryDto {
  @IsOptional()
  @IsNumberString({}, { message: 'portfolioId 必须为数字字符串' })
  portfolioId?: string;

  @IsOptional()
  @IsNumberString({}, { message: 'lookbackDays 必须为数字字符串' })
  lookbackDays?: string;

  @IsOptional()
  @IsIn(['var', 'stress', 'exposure'], { message: 'injectFail 仅支持 var/stress/exposure' })
  injectFail?: 'var' | 'stress' | 'exposure';
}

@Controller('risk')
export class RiskController {
  constructor(private readonly riskService: RiskService) {}

  private userId(req: { user?: { id?: string; sub?: string } }) {
    return String(req.user?.sub ?? req.user?.id ?? 'default');
  }

  @Get('summary')
  async summary(
    @Query() query: RiskQueryDto,
    @Req() req: { traceId?: string; headers?: Record<string, string | undefined>; user?: { id?: string; sub?: string } },
  ) {
    const data = await this.riskService.getSummary({
      userId: this.userId(req),
      portfolioId: query.portfolioId ? Number(query.portfolioId) : undefined,
      lookbackDays: query.lookbackDays ? Number(query.lookbackDays) : undefined,
      injectFail: query.injectFail,
    });
    const traceId =
      req.traceId || req.headers?.['x-trace-id'] || req.headers?.['x-request-id'] || 'UNKNOWN';

    return { success: true, data, traceId: String(traceId) };
  }

  @Get('var')
  async varOnly(
    @Query() query: RiskQueryDto,
    @Req() req: { traceId?: string; headers?: Record<string, string | undefined>; user?: { id?: string; sub?: string } },
  ) {
    const data = await this.riskService.getVarOnly({
      userId: this.userId(req),
      portfolioId: query.portfolioId ? Number(query.portfolioId) : undefined,
      lookbackDays: query.lookbackDays ? Number(query.lookbackDays) : undefined,
      injectFail: query.injectFail,
    });
    const traceId =
      req.traceId || req.headers?.['x-trace-id'] || req.headers?.['x-request-id'] || 'UNKNOWN';

    return { success: true, data, traceId: String(traceId) };
  }
}
