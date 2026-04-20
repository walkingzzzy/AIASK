import { Body, Controller, Get, Post, Query, Req } from '@nestjs/common';
import { IsArray, IsIn, IsNumberString, IsOptional, IsString, Matches } from 'class-validator';
import { BacktestService } from './backtest.service';

class RunBacktestDto {
  @IsString()
  @Matches(/^\d{6}$/, { message: 'code 必须为 6 位数字' })
  code!: string;

  @IsOptional() @IsString() strategy?: string;
  @IsOptional() @IsString() @Matches(/^\d{4}-\d{2}-\d{2}$/, { message: 'startDate 格式必须为 YYYY-MM-DD' }) startDate?: string;
  @IsOptional() @IsString() @Matches(/^\d{4}-\d{2}-\d{2}$/, { message: 'endDate 格式必须为 YYYY-MM-DD' }) endDate?: string;
  @IsOptional() @IsNumberString() initialCapital?: string;
  @IsOptional() @IsNumberString() shortPeriod?: string;
  @IsOptional() @IsNumberString() longPeriod?: string;
  @IsOptional() @IsNumberString() lookback?: string;
  @IsOptional() @IsNumberString() threshold?: string;
  @IsOptional() @IsNumberString() rsiPeriod?: string;
  @IsOptional() @IsNumberString() oversold?: string;
  @IsOptional() @IsNumberString() overbought?: string;
  @IsOptional() @IsNumberString() commission?: string;
  @IsOptional() @IsNumberString() slippage?: string;
  @IsOptional() @IsString() artifactId?: string;
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

class BatchBacktestDto {
  @IsArray()
  @Matches(/^\d{6}$/, { each: true, message: 'codes 必须为 6 位数字数组' })
  codes!: string[];

  @IsString()
  strategy!: string;

  @IsOptional() @IsString() @Matches(/^\d{4}-\d{2}-\d{2}$/, { message: 'startDate 格式必须为 YYYY-MM-DD' }) startDate?: string;
  @IsOptional() @IsString() @Matches(/^\d{4}-\d{2}-\d{2}$/, { message: 'endDate 格式必须为 YYYY-MM-DD' }) endDate?: string;
  @IsOptional() @IsNumberString() initialCapital?: string;
  @IsOptional() @IsNumberString() commission?: string;
  @IsOptional() @IsNumberString() shortPeriod?: string;
  @IsOptional() @IsNumberString() longPeriod?: string;
}

class OptimizeBacktestDto extends RunBacktestDto {
  @IsOptional() @IsString() @IsIn(['balanced', 'sharpe', 'total_return']) objective?: string;
  @IsOptional() @IsNumberString() topN?: string;
  @IsOptional() @IsNumberString() maxCandidates?: string;
}

class WalkForwardBacktestDto extends RunBacktestDto {
  @IsOptional() @IsString() @IsIn(['balanced', 'sharpe', 'total_return']) objective?: string;
  @IsOptional() @IsNumberString() trainDays?: string;
  @IsOptional() @IsNumberString() testDays?: string;
  @IsOptional() @IsNumberString() stepDays?: string;
  @IsOptional() @IsNumberString() maxFolds?: string;
}

@Controller('backtest')
export class BacktestController {
  constructor(private readonly backtestService: BacktestService) {}

  @Post('run')
  async run(
    @Body() body: RunBacktestDto,
    @Req() req: { traceId?: string; headers?: Record<string, string | undefined> },
  ) {
    const toNum = (v?: string) => v != null ? Number(v) : undefined;
    const data = await this.backtestService.run({
      code: body.code,
      strategy: body.strategy ?? 'ma_cross',
      startDate: body.startDate,
      endDate: body.endDate,
      initialCapital: toNum(body.initialCapital),
      shortPeriod: toNum(body.shortPeriod),
      longPeriod: toNum(body.longPeriod),
      lookback: toNum(body.lookback),
      threshold: toNum(body.threshold),
      rsiPeriod: toNum(body.rsiPeriod),
      oversold: toNum(body.oversold),
      overbought: toNum(body.overbought),
      commission: toNum(body.commission),
      slippage: toNum(body.slippage),
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

  /** P3-3: Batch backtest */
  @Post('batch')
  async batch(
    @Body() body: BatchBacktestDto,
    @Req() req: { traceId?: string; headers?: Record<string, string | undefined> },
  ) {
    const data = await this.backtestService.batch({
      codes: body.codes,
      strategy: body.strategy,
      startDate: body.startDate,
      endDate: body.endDate,
      initialCapital: body.initialCapital ? Number(body.initialCapital) : undefined,
      commission: body.commission ? Number(body.commission) : undefined,
      shortPeriod: body.shortPeriod ? Number(body.shortPeriod) : undefined,
      longPeriod: body.longPeriod ? Number(body.longPeriod) : undefined,
    });
    const traceId = req.traceId || req.headers?.['x-trace-id'] || 'UNKNOWN';
    return { success: true, data, traceId: String(traceId) };
  }

  @Post('optimize')
  async optimize(
    @Body() body: OptimizeBacktestDto,
    @Req() req: { traceId?: string; headers?: Record<string, string | undefined> },
  ) {
    const toNum = (v?: string) => v != null ? Number(v) : undefined;
    const data = await this.backtestService.optimize({
      code: body.code,
      strategy: body.strategy ?? 'ma_cross',
      startDate: body.startDate,
      endDate: body.endDate,
      initialCapital: toNum(body.initialCapital),
      shortPeriod: toNum(body.shortPeriod),
      longPeriod: toNum(body.longPeriod),
      lookback: toNum(body.lookback),
      threshold: toNum(body.threshold),
      rsiPeriod: toNum(body.rsiPeriod),
      oversold: toNum(body.oversold),
      overbought: toNum(body.overbought),
      commission: toNum(body.commission),
      slippage: toNum(body.slippage),
      objective: body.objective as 'balanced' | 'sharpe' | 'total_return' | undefined,
      topN: toNum(body.topN),
      maxCandidates: toNum(body.maxCandidates),
    });
    const traceId =
      req.traceId || req.headers?.['x-trace-id'] || req.headers?.['x-request-id'] || 'UNKNOWN';
    return { success: true, data, traceId: String(traceId) };
  }

  @Post('walk-forward')
  async walkForward(
    @Body() body: WalkForwardBacktestDto,
    @Req() req: { traceId?: string; headers?: Record<string, string | undefined> },
  ) {
    const toNum = (v?: string) => v != null ? Number(v) : undefined;
    const data = await this.backtestService.walkForward({
      code: body.code,
      strategy: body.strategy ?? 'ma_cross',
      startDate: body.startDate,
      endDate: body.endDate,
      initialCapital: toNum(body.initialCapital),
      shortPeriod: toNum(body.shortPeriod),
      longPeriod: toNum(body.longPeriod),
      lookback: toNum(body.lookback),
      threshold: toNum(body.threshold),
      rsiPeriod: toNum(body.rsiPeriod),
      oversold: toNum(body.oversold),
      overbought: toNum(body.overbought),
      commission: toNum(body.commission),
      slippage: toNum(body.slippage),
      objective: body.objective as 'balanced' | 'sharpe' | 'total_return' | undefined,
      trainDays: toNum(body.trainDays),
      testDays: toNum(body.testDays),
      stepDays: toNum(body.stepDays),
      maxFolds: toNum(body.maxFolds),
    });
    const traceId =
      req.traceId || req.headers?.['x-trace-id'] || req.headers?.['x-request-id'] || 'UNKNOWN';
    return { success: true, data, traceId: String(traceId) };
  }
}
