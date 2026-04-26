import { Body, Controller, Get, Param, Post, Query, Req } from '@nestjs/common';
import { Roles } from '../rbac/roles.decorator';
import { StrategyOperatorService } from './strategy-operator.service';
import { StrategyOperatorJobDto, Req_, tid } from './dto';

@Controller('strategy-market')
export class StrategyOperatorController {
  constructor(private readonly operator: StrategyOperatorService) {}

  @Get('operator/parity')
  @Roles('admin')
  async parity(@Req() req: Req_) {
    const data = this.operator.parity();
    return { success: true, data, traceId: tid(req) };
  }

  @Get('execution-audit/verification')
  @Roles('admin')
  async executionAuditVerification(@Query('strategy_id') strategyId: string, @Req() req: Req_) {
    const data = await this.operator.executionAuditVerification({ strategy_id: strategyId });
    return { success: true, data, traceId: tid(req) };
  }

  @Post('operator/jobs')
  @Roles('admin')
  async createJob(@Body() body: StrategyOperatorJobDto, @Req() req: Req_) {
    const data = await this.operator.createOperatorJob(body, { traceId: tid(req) });
    return { success: true, data, traceId: tid(req) };
  }

  @Get('operator/jobs/:jobId')
  @Roles('admin')
  async getJob(@Param('jobId') jobId: string, @Req() req: Req_) {
    const data = await this.operator.getOperatorJob(jobId);
    return { success: true, data, traceId: tid(req) };
  }
}
