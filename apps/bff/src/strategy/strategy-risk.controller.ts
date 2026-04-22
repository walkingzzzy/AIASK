import { Body, Controller, Get, Param, Post, Query, Req } from '@nestjs/common';
import { StrategyMarketService } from './strategy.service';
import { Roles } from '../rbac/roles.decorator';
import { Public } from '../rbac/public.decorator';
import {
  RiskEventsQueryDto,
  RiskSnapshotsQueryDto,
  RiskScanRunDto,
  RiskRecoveryDto,
  ResolveRiskEventDto,
  RuntimeAlertsQueryDto,
  RuntimeAlertDispatchDto,
  RuntimeAlertAckDto,
  RuntimeControlSetDto,
  Req_,
  tid,
} from './dto';

@Controller('strategy-market')
export class StrategyRiskController {
  constructor(private readonly svc: StrategyMarketService) {}

  @Get(':id/risk-events')
  @Public()
  async riskEvents(@Param('id') id: string, @Query() q: RiskEventsQueryDto, @Req() req: Req_) {
    const data = await this.svc.riskEvents(id, {
      account_id: q.account_id,
      status: q.status,
      severity: q.severity,
      limit: q.limit,
    });
    return { success: true, data, traceId: tid(req) };
  }

  @Get(':id/risk-snapshots')
  @Public()
  async riskSnapshots(@Param('id') id: string, @Query() q: RiskSnapshotsQueryDto, @Req() req: Req_) {
    const data = await this.svc.riskSnapshots(id, {
      posture_level: q.posture_level,
      control_mode: q.control_mode,
      limit: q.limit,
    });
    return { success: true, data, traceId: tid(req) };
  }

  @Post(':id/risk-scan/run')
  @Roles('admin')
  async runRiskScan(@Param('id') id: string, @Body() body: RiskScanRunDto, @Req() req: Req_) {
    const data = await this.svc.runRiskScan(id, { enforce_actions: body.enforce_actions });
    return { success: true, data, traceId: tid(req) };
  }

  @Post(':id/risk-recovery')
  async riskRecovery(@Param('id') id: string, @Body() body: RiskRecoveryDto, @Req() req: Req_) {
    const data = await this.svc.riskRecovery(id, { source: body.source });
    return { success: true, data, traceId: tid(req) };
  }

  @Post('risk-events/:eventId/resolve')
  async resolveRiskEvent(@Param('eventId') eventId: string, @Body() body: ResolveRiskEventDto, @Req() req: Req_) {
    const data = await this.svc.resolveRiskEvent(Number(eventId), body.resolution);
    return { success: true, data, traceId: tid(req) };
  }

  @Get(':id/runtime-alerts')
  @Public()
  async runtimeAlerts(@Param('id') id: string, @Query() q: RuntimeAlertsQueryDto, @Req() req: Req_) {
    const data = await this.svc.runtimeAlerts(id, {
      status: q.status,
      category: q.category,
      severity: q.severity,
      limit: q.limit,
    });
    return { success: true, data, traceId: tid(req) };
  }

  @Post(':id/runtime-alerts/dispatch')
  async dispatchRuntimeAlerts(@Param('id') id: string, @Body() body: RuntimeAlertDispatchDto, @Req() req: Req_) {
    const data = await this.svc.runRuntimeAlertDispatch(id, { source: body.source });
    return { success: true, data, traceId: tid(req) };
  }

  @Post('runtime-alerts/:alertId/ack')
  async acknowledgeRuntimeAlert(@Param('alertId') alertId: string, @Body() body: RuntimeAlertAckDto, @Req() req: Req_) {
    const data = await this.svc.acknowledgeRuntimeAlert(Number(alertId), {
      acknowledged_by: body.acknowledged_by,
      source: body.source,
    });
    return { success: true, data, traceId: tid(req) };
  }

  @Get(':id/runtime-control')
  @Public()
  async runtimeControl(@Param('id') id: string, @Req() req: Req_) {
    const data = await this.svc.runtimeControl(id);
    return { success: true, data, traceId: tid(req) };
  }

  @Post(':id/runtime-control')
  @Roles('admin')
  async setRuntimeControl(@Param('id') id: string, @Body() body: RuntimeControlSetDto, @Req() req: Req_) {
    const data = await this.svc.setRuntimeControl(id, {
      control_mode: body.control_mode,
      reason: body.reason,
      source: body.source,
      trigger_event_type: body.trigger_event_type,
    });
    return { success: true, data, traceId: tid(req) };
  }

  @Get('runtime-cycle/status')
  @Public()
  async runtimeCycleStatus(@Req() req: Req_) {
    const data = await this.svc.runtimeCycleStatus();
    return { success: true, data, traceId: tid(req) };
  }

  @Post('runtime-cycle/run')
  async runtimeCycleRun(@Req() req: Req_) {
    const data = await this.svc.runtimeCycleRun();
    return { success: true, data, traceId: tid(req) };
  }
}
