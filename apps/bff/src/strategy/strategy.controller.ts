import { Body, Controller, Delete, Get, Param, Post, Query, Req, UnauthorizedException } from '@nestjs/common';
import { Throttle } from '@nestjs/throttler';
import { StrategyMarketService } from './strategy.service';
import { Roles } from '../rbac/roles.decorator';
import {
  ListDto,
  RankDto,
  RefreshRankingDto,
  CreateDto,
  SubscribeDto,
  ReviewDto,
  UpdateMetricsDto,
  SignalsQueryDto,
  EventsQueryDto,
  DailySnapshotsQueryDto,
  TaskRunsQueryDto,
  Req_,
  tid,
} from './dto';

@Controller('strategy-market')
export class StrategyMarketController {
  constructor(private readonly svc: StrategyMarketService) {}

  private currentUserId(req: Req_): string {
    const userId = req.user?.id?.trim();
    if (!userId) {
      throw new UnauthorizedException('登录状态无效');
    }
    return userId;
  }

  @Get('list')
  async list(@Query() q: ListDto, @Req() req: Req_) {
    const data = await this.svc.list({ status: q.status, strategy_type: q.strategy_type, limit: q.limit, offset: q.offset });
    return { success: true, data, traceId: tid(req) };
  }

  @Get('ranking')
  async ranking(@Query() q: RankDto, @Req() req: Req_) {
    const data = await this.svc.rank({
      status: q.status,
      strategy_type: q.strategy_type,
      limit: q.limit,
      offset: q.offset,
      rank_keys: q.rank_keys,
    });
    return { success: true, data, traceId: tid(req) };
  }

  @Post('ranking/refresh')
  @Roles('admin')
  async refreshRanking(@Body() body: RefreshRankingDto, @Req() req: Req_) {
    const data = await this.svc.refreshRankingCaches({
      strategy_types: body.strategy_types,
      limits: body.limits,
      rank_keys_sets: body.rank_keys_sets,
    });
    return { success: true, data, traceId: tid(req) };
  }

  @Get('my-subscriptions')
  async mySubs(@Req() req: Req_) {
    const data = await this.svc.mySubscriptions(this.currentUserId(req));
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

  @Get('task-runs')
  async taskRuns(@Query() q: TaskRunsQueryDto, @Req() req: Req_) {
    const data = await this.svc.taskRuns({
      strategy_id: q.strategy_id,
      task_name: q.task_name,
      task_scope: q.task_scope,
      status: q.status,
      limit: q.limit,
    });
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

  @Get(':id')
  async detail(@Param('id') id: string, @Req() req: Req_) {
    const data = await this.svc.detail(id);
    return { success: true, data, traceId: tid(req) };
  }

  @Post('create')
  async create(@Body() body: CreateDto, @Req() req: Req_) {
    const data = await this.svc.create({
      ...body,
      author_id: this.currentUserId(req),
    });
    return { success: true, data, traceId: tid(req) };
  }

  @Post(':id/publish')
  @Roles('admin')
  async publish(@Param('id') id: string, @Req() req: Req_) {
    const data = await this.svc.publish(id);
    return { success: true, data, traceId: tid(req) };
  }

  @Post(':id/archive')
  @Roles('admin')
  async archive(@Param('id') id: string, @Req() req: Req_) {
    const data = await this.svc.archive(id);
    return { success: true, data, traceId: tid(req) };
  }

  @Post(':id/update-metrics')
  @Roles('admin')
  async updateMetrics(@Param('id') id: string, @Body() body: UpdateMetricsDto, @Req() req: Req_) {
    const data = await this.svc.updateMetrics(id, body);
    return { success: true, data, traceId: tid(req) };
  }

  @Post(':id/subscribe')
  async subscribe(@Param('id') id: string, @Body() _body: SubscribeDto, @Req() req: Req_) {
    const data = await this.svc.subscribe(id, this.currentUserId(req));
    return { success: true, data, traceId: tid(req) };
  }

  @Delete(':id/subscribe')
  async unsubscribe(@Param('id') id: string, @Req() req: Req_) {
    const data = await this.svc.unsubscribe(id, this.currentUserId(req));
    return { success: true, data, traceId: tid(req) };
  }

  @Post(':id/review')
  async review(@Param('id') id: string, @Body() body: ReviewDto, @Req() req: Req_) {
    const data = await this.svc.review(id, this.currentUserId(req), body.rating, body.comment);
    return { success: true, data, traceId: tid(req) };
  }

  @Post(':id/submit')
  @Roles('admin')
  async submit(@Param('id') id: string, @Req() req: Req_) {
    const data = await this.svc.submit(id);
    return { success: true, data, traceId: tid(req) };
  }

  @Get(':id/signals')
  @Throttle({ default: { ttl: 60000, limit: 30 } })
  async signals(@Param('id') id: string, @Query() q: SignalsQueryDto, @Req() req: Req_) {
    const data = await this.svc.getSignals(id, this.currentUserId(req), { limit: q.limit });
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
  @Roles('admin')
  async lifecycleScan(@Req() req: Req_) {
    const data = await this.svc.lifecycleScan();
    return { success: true, data, traceId: tid(req) };
  }
}
