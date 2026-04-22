import { Body, Controller, Get, Param, Post, Query, Req } from '@nestjs/common';
import { StrategyMarketService } from './strategy.service';
import { Roles } from '../rbac/roles.decorator';
import { Public } from '../rbac/public.decorator';
import { FactoryRunsQueryDto, AiGenerateDto, AiExperimentsQueryDto, Req_, ReviewWorkflowQueryDto, tid } from './dto';

@Controller('strategy-market')
export class StrategyFactoryController {
  constructor(private readonly svc: StrategyMarketService) {}

  @Get('factory/status')
  @Public()
  async factoryStatus(@Req() req: Req_) {
    const data = await this.svc.factoryStatus();
    return { success: true, data, traceId: tid(req) };
  }

  @Get('factory/observability')
  @Public()
  async factoryObservability(@Req() req: Req_) {
    const data = await this.svc.factoryObservability();
    return { success: true, data, traceId: tid(req) };
  }

  @Post('factory/run-once')
  @Roles('admin')
  async factoryRunOnce(@Req() req: Req_) {
    const data = await this.svc.factoryRunOnce();
    return { success: true, data, traceId: tid(req) };
  }

  @Get('factory/runs')
  @Public()
  async factoryRuns(@Query() q: FactoryRunsQueryDto, @Req() req: Req_) {
    const data = await this.svc.factoryRuns(q.limit);
    return { success: true, data, traceId: tid(req) };
  }

  @Get('factory/runs/:runId')
  @Public()
  async factoryRunDetail(@Param('runId') runId: string, @Req() req: Req_) {
    const data = await this.svc.factoryRunDetail(runId);
    return { success: true, data, traceId: tid(req) };
  }

  @Get('factory/topn/latest')
  @Public()
  async factoryTopnLatest(@Query('limit') limit: string, @Req() req: Req_) {
    const data = await this.svc.factoryTopnLatest(limit ? Number(limit) : undefined);
    return { success: true, data, traceId: tid(req) };
  }

  @Get('factory/runs/:runId/topn')
  @Public()
  async factoryRunTopn(@Param('runId') runId: string, @Query('limit') limit: string, @Req() req: Req_) {
    const data = await this.svc.factoryRunTopn(runId, limit ? Number(limit) : undefined);
    return { success: true, data, traceId: tid(req) };
  }

  @Get('factory/dispatches/:dispatchId')
  @Public()
  async factoryDispatchStatus(@Param('dispatchId') dispatchId: string, @Req() req: Req_) {
    const data = await this.svc.factoryDispatchStatus(dispatchId);
    return { success: true, data, traceId: tid(req) };
  }

  @Get(':id/review-report')
  @Public()
  async reviewReport(@Param('id') id: string, @Req() req: Req_) {
    const data = await this.svc.reviewReport(id);
    return { success: true, data, traceId: tid(req) };
  }

  @Post(':id/review-report/recheck')
  async reviewReportRecheck(@Param('id') id: string, @Req() req: Req_) {
    const data = await this.svc.reviewReportRecheck(id);
    return { success: true, data, traceId: tid(req) };
  }

  @Get(':id/review-workflow')
  @Public()
  async reviewWorkflow(@Param('id') id: string, @Query() query: ReviewWorkflowQueryDto, @Req() req: Req_) {
    const data = await this.svc.reviewWorkflow(id, query, {
      userId: req.user?.id,
      role: req.user?.role,
    });
    return { success: true, data, traceId: tid(req) };
  }

  @Get(':id/closure-review')
  @Public()
  async closureReview(
    @Param('id') id: string,
    @Query('as_of') asOf: string,
    @Query('correlation_id') correlationId: string,
    @Req() req: Req_,
  ) {
    const data = await this.svc.closureReview(id, {
      as_of: asOf,
      correlation_id: correlationId,
      user_id: req.user?.id,
      role: req.user?.role,
    });
    return { success: true, data, traceId: tid(req) };
  }

  @Post('ai/generate')
  @Roles('admin')
  async aiGenerate(@Body() body: AiGenerateDto, @Req() req: Req_) {
    const data = await this.svc.aiGenerate({
      limit: body.limit,
      parent_strategy_id: body.parent_strategy_id,
      auto_submit: body.auto_submit,
    });
    return { success: true, data, traceId: tid(req) };
  }

  @Get('ai/experiments')
  @Public()
  async aiExperiments(@Query() q: AiExperimentsQueryDto, @Req() req: Req_) {
    const data = await this.svc.aiExperiments({
      experiment_id: q.experiment_id,
      strategy_id: q.strategy_id,
      parent_strategy_id: q.parent_strategy_id,
      generated_strategy_id: q.generated_strategy_id,
      task_run_id: q.task_run_id,
      status: q.status,
      source: q.source,
      limit: q.limit,
    });
    return { success: true, data, traceId: tid(req) };
  }
}
