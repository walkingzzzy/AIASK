import { Body, Controller, Get, Post, Query, Req } from '@nestjs/common';
import { IsNumberString, IsOptional, IsString, Matches } from 'class-validator';
import { BacktestService } from './backtest.service';

class RunBacktestDto {
  @IsString()
  @Matches(/^\d{6}$/, { message: 'code 必须为 6 位数字' })
  code!: string;

  @IsOptional()
  @IsString()
  strategy?: string;

  @IsOptional()
  @IsString()
  @Matches(/^\d{4}-\d{2}-\d{2}$/, { message: 'startDate 格式必须为 YYYY-MM-DD' })
  startDate?: string;

  @IsOptional()
  @IsString()
  @Matches(/^\d{4}-\d{2}-\d{2}$/, { message: 'endDate 格式必须为 YYYY-MM-DD' })
  endDate?: string;

  @IsOptional()
  @IsNumberString({}, { message: 'initialCapital 必须为数字字符串' })
  initialCapital?: string;

  @IsOptional()
  @IsNumberString({}, { message: 'shortPeriod 必须为数字字符串' })
  shortPeriod?: string;

  @IsOptional()
  @IsNumberString({}, { message: 'longPeriod 必须为数字字符串' })
  longPeriod?: string;

  @IsOptional()
  @IsString()
  artifactId?: string;
}

class ListBacktestDto {
  @IsOptional()
  @IsNumberString({}, { message: 'limit 必须为数字字符串' })
  limit?: string;
}

class ArtifactQueryDto {
  @IsString()
  artifactId!: string;
}

@Controller('backtest')
export class BacktestController {
  constructor(private readonly backtestService: BacktestService) {}

  @Post('run')
  async run(
    @Body() body: RunBacktestDto,
    @Req() req: { traceId?: string; headers?: Record<string, string | undefined> },
  ) {
    const data = await this.backtestService.run({
      code: body.code,
      strategy: body.strategy ?? 'ma_cross',
      startDate: body.startDate,
      endDate: body.endDate,
      initialCapital: body.initialCapital ? Number(body.initialCapital) : undefined,
      shortPeriod: body.shortPeriod ? Number(body.shortPeriod) : undefined,
      longPeriod: body.longPeriod ? Number(body.longPeriod) : undefined,
      artifactId: body.artifactId,
    });

    const traceId =
      req.traceId || req.headers?.['x-trace-id'] || req.headers?.['x-request-id'] || 'UNKNOWN';
    return { success: true, data, traceId: String(traceId) };
  }

  @Get('list')
  async list(
    @Query() query: ListBacktestDto,
    @Req() req: { traceId?: string; headers?: Record<string, string | undefined> },
  ) {
    const data = await this.backtestService.list(query.limit ? Number(query.limit) : 10);
    const traceId =
      req.traceId || req.headers?.['x-trace-id'] || req.headers?.['x-request-id'] || 'UNKNOWN';
    return { success: true, data, traceId: String(traceId) };
  }

  @Get('metrics')
  async metrics(
    @Query() query: ArtifactQueryDto,
    @Req() req: { traceId?: string; headers?: Record<string, string | undefined> },
  ) {
    const data = await this.backtestService.metricsByArtifact(query.artifactId);
    const traceId =
      req.traceId || req.headers?.['x-trace-id'] || req.headers?.['x-request-id'] || 'UNKNOWN';
    return { success: true, data, traceId: String(traceId) };
  }
}

