import { Body, Controller, Get, Param, Post, Query, Req } from '@nestjs/common';
import { StrategyMarketService } from './strategy.service';
import {
  IncubationMetricsQueryDto,
  PaperOrdersQueryDto,
  PaperNavQueryDto,
  ExecutionAuditAcceptanceDto,
  IncubationSyncRunDto,
  IncubationPipelineQueryDto,
  IncubationPipelineRunDto,
  PromotionReviewsQueryDto,
  PromotionReviewRunDto,
  Req_,
  tid,
} from './dto';

@Controller('strategy-market')
export class StrategyIncubationController {
  constructor(private readonly svc: StrategyMarketService) {}

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

  @Get(':id/paper-account')
  async paperAccount(@Param('id') id: string, @Query() q: PaperNavQueryDto, @Req() req: Req_) {
    const data = await this.svc.paperAccount(id, { limit: q.limit });
    return { success: true, data, traceId: tid(req) };
  }

  @Get(':id/paper-orders')
  async paperOrders(@Param('id') id: string, @Query() q: PaperOrdersQueryDto, @Req() req: Req_) {
    const data = await this.svc.paperOrders(id, { signal_date: q.signal_date, status: q.status, limit: q.limit });
    return { success: true, data, traceId: tid(req) };
  }

  @Get(':id/paper-nav')
  async paperNav(@Param('id') id: string, @Query() q: PaperNavQueryDto, @Req() req: Req_) {
    const data = await this.svc.paperNav(id, { limit: q.limit });
    return { success: true, data, traceId: tid(req) };
  }

  @Get(':id/execution-audit')
  async executionAuditAcceptance(@Param('id') id: string, @Query() q: ExecutionAuditAcceptanceDto, @Req() req: Req_) {
    const data = await this.svc.executionAuditAcceptance(id, { backfill: q.backfill ?? false });
    return { success: true, data, traceId: tid(req) };
  }

  @Post(':id/execution-audit/run')
  async runExecutionAuditAcceptance(@Param('id') id: string, @Body() body: ExecutionAuditAcceptanceDto, @Req() req: Req_) {
    const data = await this.svc.executionAuditAcceptance(id, { backfill: body.backfill ?? true });
    return { success: true, data, traceId: tid(req) };
  }

  @Post(':id/incubation-sync/run')
  async runIncubationSync(@Param('id') id: string, @Body() body: IncubationSyncRunDto, @Req() req: Req_) {
    const data = await this.svc.runIncubationSync(id, { signal_date: body.signal_date });
    return { success: true, data, traceId: tid(req) };
  }

  @Get(':id/incubation-pipeline')
  async incubationPipeline(@Param('id') id: string, @Query() q: IncubationPipelineQueryDto, @Req() req: Req_) {
    const data = await this.svc.incubationPipeline(id, { pipeline_stage: q.pipeline_stage, pipeline_status: q.pipeline_status, limit: q.limit });
    return { success: true, data, traceId: tid(req) };
  }

  @Post(':id/incubation-pipeline/run')
  async runIncubationPipeline(@Param('id') id: string, @Body() body: IncubationPipelineRunDto, @Req() req: Req_) {
    const data = await this.svc.runIncubationPipeline(id, { statuses: body.statuses, limit: body.limit, source: body.source, auto_apply_review: body.auto_apply_review });
    return { success: true, data, traceId: tid(req) };
  }

  @Post('incubation-pipeline/run')
  async runIncubationPipelineBatch(@Body() body: IncubationPipelineRunDto, @Req() req: Req_) {
    const data = await this.svc.runIncubationPipeline(undefined, { statuses: body.statuses, limit: body.limit, source: body.source, auto_apply_review: body.auto_apply_review });
    return { success: true, data, traceId: tid(req) };
  }

  @Get(':id/promotion-reviews')
  async promotionReviews(@Param('id') id: string, @Query() q: PromotionReviewsQueryDto, @Req() req: Req_) {
    const data = await this.svc.promotionReviews(id, { status: q.status, limit: q.limit });
    return { success: true, data, traceId: tid(req) };
  }

  @Post(':id/promotion-review/run')
  async runPromotionReview(@Param('id') id: string, @Body() body: PromotionReviewRunDto, @Req() req: Req_) {
    const data = await this.svc.runPromotionReview(id, { auto_apply: body.auto_apply, source: body.source });
    return { success: true, data, traceId: tid(req) };
  }
}
