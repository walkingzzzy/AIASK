import { Body, Controller, Delete, Get, Param, Post, Query, Req } from '@nestjs/common';
import { IsArray, IsInt, IsOptional, IsString, Max, Min } from 'class-validator';
import { Type, Transform } from 'class-transformer';
import { Throttle } from '@nestjs/throttler';
import { StrategyMarketService } from './strategy.service';

class ListDto {
  @IsOptional() @IsString() status?: string;
  @IsOptional() @IsString() strategy_type?: string;
  @IsOptional() @Type(() => Number) @IsInt() @Min(1) @Max(100) limit?: number;
  @IsOptional() @Type(() => Number) @IsInt() @Min(0) offset?: number;
}

class RankDto {
  @IsOptional() @IsString() strategy_type?: string;
  @IsOptional() @Type(() => Number) @IsInt() @Min(1) @Max(200) limit?: number;
  @IsOptional() @Type(() => Number) @IsInt() @Min(0) offset?: number;
  @IsOptional() @Transform(({ value }) => (typeof value === 'string' ? value.split(',') : value))
  @IsArray() @IsString({ each: true })
  rank_keys?: string[];
}

class RefreshRankingDto {
  @IsOptional()
  @Transform(({ value }) => (typeof value === 'string' ? value.split(',') : value))
  @IsArray() @IsString({ each: true })
  strategy_types?: string[];

  @IsOptional()
  @Transform(({ value }) => (typeof value === 'string' ? value.split(',').map((x: string) => Number(x)) : value))
  @IsArray() @IsInt({ each: true }) @Min(1, { each: true }) @Max(200, { each: true })
  limits?: number[];

  @IsOptional()
  rank_keys_sets?: string[][];
}

class CreateDto {
  @IsString() name!: string;
  @IsString() strategy_type!: string;
  @IsOptional() @IsString() description?: string;
  @IsOptional() @IsString() author_id?: string;
  @IsOptional() params?: Record<string, unknown>;
  @IsOptional() factor_weights?: Record<string, number>;
  @IsOptional() @IsArray() @IsString({ each: true }) tags?: string[];
  @IsOptional() @IsString() backtest_artifact_id?: string;
}


class SubscribeDto {
  @IsString() user_id!: string;
}

class ReviewDto {
  @IsString() user_id!: string;
  @Type(() => Number) @IsInt() @Min(1) @Max(5) rating!: number;
  @IsOptional() @IsString() comment?: string;
}

class UpdateMetricsDto {
  @IsOptional() @IsString() period?: string;
  @IsOptional() metrics?: Record<string, unknown>;
}

class SignalsQueryDto {
  @IsOptional() @IsString() user_id?: string;
  @IsOptional() @Type(() => Number) @IsInt() @Min(1) @Max(500) limit?: number;
}
type Req_ = { traceId?: string; headers?: Record<string, string | undefined> };
function tid(req: Req_) {
  return String(req.traceId || req.headers?.['x-trace-id'] || req.headers?.['x-request-id'] || 'UNKNOWN');
}

@Controller('strategy-market')
export class StrategyMarketController {
  constructor(private readonly svc: StrategyMarketService) {}

  @Get('list')
  async list(@Query() q: ListDto, @Req() req: Req_) {
    const data = await this.svc.list({ status: q.status, strategy_type: q.strategy_type, limit: q.limit, offset: q.offset });
    return { success: true, data, traceId: tid(req) };
  }

  @Get('ranking')
  async ranking(@Query() q: RankDto, @Req() req: Req_) {
    const data = await this.svc.rank({
      strategy_type: q.strategy_type,
      limit: q.limit,
      offset: q.offset,
      rank_keys: q.rank_keys,
    });
    return { success: true, data, traceId: tid(req) };
  }

  @Post('ranking/refresh')
  async refreshRanking(@Body() body: RefreshRankingDto, @Req() req: Req_) {
    const data = await this.svc.refreshRankingCaches({
      strategy_types: body.strategy_types,
      limits: body.limits,
      rank_keys_sets: body.rank_keys_sets,
    });
    return { success: true, data, traceId: tid(req) };
  }


  @Get('my-subscriptions')
  async mySubs(@Query('user_id') userId: string, @Req() req: Req_) {
    const data = await this.svc.mySubscriptions(userId || 'default');
    return { success: true, data, traceId: tid(req) };
  }

  @Get(':id')
  async detail(@Param('id') id: string, @Req() req: Req_) {
    const data = await this.svc.detail(id);
    return { success: true, data, traceId: tid(req) };
  }

  @Post('create')
  async create(@Body() body: CreateDto, @Req() req: Req_) {
    const data = await this.svc.create(body);
    return { success: true, data, traceId: tid(req) };
  }

  @Post(':id/publish')
  async publish(@Param('id') id: string, @Req() req: Req_) {
    const data = await this.svc.publish(id);
    return { success: true, data, traceId: tid(req) };
  }

  @Post(':id/archive')
  async archive(@Param('id') id: string, @Req() req: Req_) {
    const data = await this.svc.archive(id);
    return { success: true, data, traceId: tid(req) };
  }

  @Post(':id/update-metrics')
  async updateMetrics(@Param('id') id: string, @Body() body: UpdateMetricsDto, @Req() req: Req_) {
    const data = await this.svc.updateMetrics(id, body);
    return { success: true, data, traceId: tid(req) };
  }

  @Post(':id/subscribe')
  async subscribe(@Param('id') id: string, @Body() body: SubscribeDto, @Req() req: Req_) {
    const data = await this.svc.subscribe(id, body.user_id);
    return { success: true, data, traceId: tid(req) };
  }

  @Delete(':id/subscribe')
  async unsubscribe(@Param('id') id: string, @Query('user_id') userId: string, @Req() req: Req_) {
    const data = await this.svc.unsubscribe(id, userId || 'default');
    return { success: true, data, traceId: tid(req) };
  }

  @Post(':id/review')
  async review(@Param('id') id: string, @Body() body: ReviewDto, @Req() req: Req_) {
    const data = await this.svc.review(id, body.user_id, body.rating, body.comment);
    return { success: true, data, traceId: tid(req) };
  }

  @Post(':id/submit')
  async submit(@Param('id') id: string, @Req() req: Req_) {
    const data = await this.svc.submit(id);
    return { success: true, data, traceId: tid(req) };
  }

  @Get(':id/signals')
  @Throttle({ default: { ttl: 60000, limit: 30 } })
  async signals(@Param('id') id: string, @Query() q: SignalsQueryDto, @Req() req: Req_) {
    const data = await this.svc.getSignals(id, q.user_id || 'default', { limit: q.limit });
    return { success: true, data, traceId: tid(req) };
  }

  @Get(':id/forward-returns')
  async forwardReturns(@Param('id') id: string, @Req() req: Req_) {
    const data = await this.svc.getForwardReturns(id);
    return { success: true, data, traceId: tid(req) };
  }

  @Get(':id/signal-stats')
  async signalStats(@Param('id') id: string, @Req() req: Req_) {
    const data = await this.svc.getSignalStats(id);
    return { success: true, data, traceId: tid(req) };
  }

  @Post('lifecycle-scan')
  async lifecycleScan(@Req() req: Req_) {
    const data = await this.svc.lifecycleScan();
    return { success: true, data, traceId: tid(req) };
  }
}
