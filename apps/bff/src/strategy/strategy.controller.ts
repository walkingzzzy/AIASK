import { Body, Controller, Delete, Get, Param, Post, Query, Req } from '@nestjs/common';
import { IsArray, IsBoolean, IsInt, IsOptional, IsString, Max, Min } from 'class-validator';
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

class EventsQueryDto {
  @IsOptional() @IsString() event_type?: string;
  @IsOptional() @IsString() from_status?: string;
  @IsOptional() @IsString() to_status?: string;
  @IsOptional() @IsString() actor_id?: string;
  @IsOptional() @IsString() start_time?: string;
  @IsOptional() @IsString() end_time?: string;
  @IsOptional() @Type(() => Number) @IsInt() @Min(1) @Max(200) limit?: number;
}

class FactoryRunsQueryDto {
  @IsOptional() @Type(() => Number) @IsInt() @Min(1) @Max(100) limit?: number;
}

class DailySnapshotsQueryDto {
  @IsOptional() @Type(() => Number) @IsInt() @Min(1) @Max(200) limit?: number;
  @IsOptional() @IsString() start_date?: string;
  @IsOptional() @IsString() end_date?: string;
}

class IncubationMetricsQueryDto {
  @IsOptional() @Type(() => Number) @IsInt() @Min(1) @Max(365) limit?: number;
  @IsOptional() @IsString() start_date?: string;
  @IsOptional() @IsString() end_date?: string;
}

class RiskEventsQueryDto {
  @IsOptional() @IsString() account_id?: string;
  @IsOptional() @IsString() status?: string;
  @IsOptional() @IsString() severity?: string;
  @IsOptional() @Type(() => Number) @IsInt() @Min(1) @Max(500) limit?: number;
}

class VectorProfilesQueryDto {
  @IsOptional() @IsString() profile_type?: string;
  @IsOptional() @IsString() similar_to?: string;
  @IsOptional() @Type(() => Number) @IsInt() @Min(1) @Max(200) limit?: number;
}

class VectorIndexesQueryDto {
  @IsOptional() @IsString() index_name?: string;
  @IsOptional() @IsString() status?: string;
  @IsOptional() @Type(() => Number) @IsInt() @Min(1) @Max(200) limit?: number;
}

class VectorReconcileDto {
  @IsOptional() @IsString() index_name?: string;
  @IsOptional() @IsString() profile_type?: string;
  @IsOptional() @Type(() => Number) @IsInt() @Min(1) @Max(5000) limit_profiles?: number;
}

class VectorRebuildDto {
  @IsOptional() @IsString() index_name?: string;
  @IsOptional() @IsString() index_version?: string;
  @IsOptional() @Transform(({ value }) => (typeof value === 'string' ? value.split(',') : value))
  @IsArray() @IsString({ each: true })
  statuses?: string[];
  @IsOptional() @Type(() => Number) @IsInt() @Min(1) @Max(1000) limit?: number;
  @IsOptional() @IsString() profile_type?: string;
  @IsOptional() @IsString() vector_method?: string;
}

class DomainEventsQueryDto {
  @IsOptional() @IsString() aggregate_type?: string;
  @IsOptional() @IsString() event_type?: string;
  @IsOptional() @IsString() source?: string;
  @IsOptional() @IsString() correlation_id?: string;
  @IsOptional() @Type(() => Number) @IsInt() @Min(1) @Max(500) limit?: number;
}

class ResolveRiskEventDto {
  @IsOptional() @IsString() resolution?: string;
}

class AiGenerateDto {
  @IsOptional() @Type(() => Number) @IsInt() @Min(1) @Max(10) limit?: number;
  @IsOptional() @IsString() parent_strategy_id?: string;
  @IsOptional() @Transform(({ value }) => value === true || value === 'true') @IsBoolean() auto_submit?: boolean;
}

class AiExperimentsQueryDto {
  @IsOptional() @IsString() experiment_id?: string;
  @IsOptional() @IsString() strategy_id?: string;
  @IsOptional() @IsString() status?: string;
  @IsOptional() @IsString() source?: string;
  @IsOptional() @Type(() => Number) @IsInt() @Min(1) @Max(200) limit?: number;
}

class TaskRunsQueryDto {
  @IsOptional() @IsString() task_name?: string;
  @IsOptional() @IsString() task_scope?: string;
  @IsOptional() @IsString() status?: string;
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

  @Get('capabilities')
  async capabilities(@Req() req: Req_) {
    const data = await this.svc.capabilities();
    return { success: true, data, traceId: tid(req) };
  }

  @Get('daily-snapshots')
  async dailySnapshots(@Query() q: DailySnapshotsQueryDto, @Req() req: Req_) {
    const data = await this.svc.dailySnapshots({ limit: q.limit, start_date: q.start_date, end_date: q.end_date });
    return { success: true, data, traceId: tid(req) };
  }

  @Get('daily-snapshot')
  async dailySnapshot(@Query('snapshot_date') snapshotDate: string, @Req() req: Req_) {
    const data = await this.svc.dailySnapshot(snapshotDate);
    return { success: true, data, traceId: tid(req) };
  }

  @Get('factory/status')
  async factoryStatus(@Req() req: Req_) {
    const data = await this.svc.factoryStatus();
    return { success: true, data, traceId: tid(req) };
  }

  @Post('factory/run-once')
  async factoryRunOnce(@Req() req: Req_) {
    const data = await this.svc.factoryRunOnce();
    return { success: true, data, traceId: tid(req) };
  }

  @Get('factory/runs')
  async factoryRuns(@Query() q: FactoryRunsQueryDto, @Req() req: Req_) {
    const data = await this.svc.factoryRuns(q.limit);
    return { success: true, data, traceId: tid(req) };
  }

  @Get('factory/runs/:runId')
  async factoryRunDetail(@Param('runId') runId: string, @Req() req: Req_) {
    const data = await this.svc.factoryRunDetail(runId);
    return { success: true, data, traceId: tid(req) };
  }

  @Get(':id/review-report')
  async reviewReport(@Param('id') id: string, @Req() req: Req_) {
    const data = await this.svc.reviewReport(id);
    return { success: true, data, traceId: tid(req) };
  }

  @Post(':id/review-report/recheck')
  async reviewReportRecheck(@Param('id') id: string, @Req() req: Req_) {
    const data = await this.svc.reviewReportRecheck(id);
    return { success: true, data, traceId: tid(req) };
  }

  @Get(':id/events')
  async events(@Param('id') id: string, @Query() q: EventsQueryDto, @Req() req: Req_) {
    const data = await this.svc.events(id, {
      event_type: q.event_type,
      from_status: q.from_status,
      to_status: q.to_status,
      actor_id: q.actor_id,
      start_time: q.start_time,
      end_time: q.end_time,
      limit: q.limit,
    });
    return { success: true, data, traceId: tid(req) };
  }

  @Get(':id/incubation-overview')
  async incubationOverview(@Param('id') id: string, @Req() req: Req_) {
    const data = await this.svc.incubationOverview(id);
    return { success: true, data, traceId: tid(req) };
  }

  @Get(':id/incubation-accounts')
  async incubationAccounts(@Param('id') id: string, @Query('status') status: string, @Query('limit') limit: string, @Req() req: Req_) {
    const data = await this.svc.incubationAccounts(id, { status, limit: limit ? Number(limit) : undefined });
    return { success: true, data, traceId: tid(req) };
  }

  @Get(':id/incubation-metrics')
  async incubationMetrics(@Param('id') id: string, @Query() q: IncubationMetricsQueryDto, @Req() req: Req_) {
    const data = await this.svc.incubationMetrics(id, { limit: q.limit, start_date: q.start_date, end_date: q.end_date });
    return { success: true, data, traceId: tid(req) };
  }

  @Get(':id/risk-events')
  async riskEvents(@Param('id') id: string, @Query() q: RiskEventsQueryDto, @Req() req: Req_) {
    const data = await this.svc.riskEvents(id, { account_id: q.account_id, status: q.status, severity: q.severity, limit: q.limit });
    return { success: true, data, traceId: tid(req) };
  }

  @Post('risk-events/:eventId/resolve')
  async resolveRiskEvent(@Param('eventId') eventId: string, @Body() body: ResolveRiskEventDto, @Req() req: Req_) {
    const data = await this.svc.resolveRiskEvent(Number(eventId), body.resolution);
    return { success: true, data, traceId: tid(req) };
  }

  @Get(':id/vector-profiles')
  async vectorProfiles(@Param('id') id: string, @Query() q: VectorProfilesQueryDto, @Req() req: Req_) {
    const data = await this.svc.vectorProfiles(id, { profile_type: q.profile_type, similar_to: q.similar_to, limit: q.limit });
    return { success: true, data, traceId: tid(req) };
  }

  @Get('vector-indexes')
  async vectorIndexes(@Query() q: VectorIndexesQueryDto, @Req() req: Req_) {
    const data = await this.svc.vectorIndexes({ index_name: q.index_name, status: q.status, limit: q.limit });
    return { success: true, data, traceId: tid(req) };
  }

  @Post('vector-indexes/reconcile')
  async vectorReconcile(@Body() body: VectorReconcileDto, @Req() req: Req_) {
    const data = await this.svc.vectorReconcile({ index_name: body.index_name, profile_type: body.profile_type, limit_profiles: body.limit_profiles });
    return { success: true, data, traceId: tid(req) };
  }

  @Post('vector-indexes/rebuild')
  async vectorRebuild(@Body() body: VectorRebuildDto, @Req() req: Req_) {
    const data = await this.svc.vectorRebuild({ index_name: body.index_name, index_version: body.index_version, statuses: body.statuses, limit: body.limit, profile_type: body.profile_type, vector_method: body.vector_method });
    return { success: true, data, traceId: tid(req) };
  }

  @Get(':id/domain-events')
  async domainEvents(@Param('id') id: string, @Query() q: DomainEventsQueryDto, @Req() req: Req_) {
    const data = await this.svc.domainEvents(id, { aggregate_type: q.aggregate_type, event_type: q.event_type, source: q.source, correlation_id: q.correlation_id, limit: q.limit });
    return { success: true, data, traceId: tid(req) };
  }

  @Get('runtime-cycle/status')
  async runtimeCycleStatus(@Req() req: Req_) {
    const data = await this.svc.runtimeCycleStatus();
    return { success: true, data, traceId: tid(req) };
  }

  @Post('runtime-cycle/run')
  async runtimeCycleRun(@Req() req: Req_) {
    const data = await this.svc.runtimeCycleRun();
    return { success: true, data, traceId: tid(req) };
  }

  @Post('ai/generate')
  async aiGenerate(@Body() body: AiGenerateDto, @Req() req: Req_) {
    const data = await this.svc.aiGenerate({ limit: body.limit, parent_strategy_id: body.parent_strategy_id, auto_submit: body.auto_submit });
    return { success: true, data, traceId: tid(req) };
  }

  @Get('ai/experiments')
  async aiExperiments(@Query() q: AiExperimentsQueryDto, @Req() req: Req_) {
    const data = await this.svc.aiExperiments({ experiment_id: q.experiment_id, strategy_id: q.strategy_id, status: q.status, source: q.source, limit: q.limit });
    return { success: true, data, traceId: tid(req) };
  }

  @Get('task-runs')
  async taskRuns(@Query() q: TaskRunsQueryDto, @Req() req: Req_) {
    const data = await this.svc.taskRuns({ task_name: q.task_name, task_scope: q.task_scope, status: q.status, limit: q.limit });
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
