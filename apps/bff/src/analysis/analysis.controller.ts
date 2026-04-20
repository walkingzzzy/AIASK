import { Body, Controller, Get, Param, Post, Req } from '@nestjs/common';
import { IsIn, IsOptional, IsString } from 'class-validator';
import { DEEP_ANALYSIS_TASKS, type DeepAnalysisTask } from '@aiask/shared-types';
import { AnalysisService } from './analysis.service';

class CreateDeepStockRunDto {
  @IsOptional() @IsString() code?: string;
  @IsOptional() @IsIn([...DEEP_ANALYSIS_TASKS]) task?: DeepAnalysisTask;
  @IsOptional() @IsString() runId?: string;
  @IsOptional() @IsString() investmentStyle?: string;
  @IsOptional() @IsString() market?: string;
}

class RunParamDto {
  @IsString() runId!: string;
}

@Controller('v1/analysis')
export class AnalysisController {
  constructor(private readonly analysisService: AnalysisService) {}

  @Post('deep-stock/runs')
  async createRun(
    @Body() body: CreateDeepStockRunDto,
    @Req() req: { user?: { sub?: string; id?: string }; traceId?: string; headers?: Record<string, string | undefined> },
  ) {
    const userId = req.user?.sub ?? req.user?.id;
    const data = await this.analysisService.createRun({
      code: body.code,
      task: body.task,
      runId: body.runId,
      investmentStyle: body.investmentStyle,
      market: body.market,
      userId,
    });
    const traceId = req.traceId || req.headers?.['x-trace-id'] || req.headers?.['x-request-id'] || 'UNKNOWN';
    return { success: true, data, traceId: String(traceId) };
  }

  @Get('deep-stock/runs/:runId')
  async getRun(
    @Param() params: RunParamDto,
    @Req() req: { traceId?: string; headers?: Record<string, string | undefined> },
  ) {
    const data = await this.analysisService.getRun(params.runId);
    const traceId = req.traceId || req.headers?.['x-trace-id'] || req.headers?.['x-request-id'] || 'UNKNOWN';
    return { success: true, data, traceId: String(traceId) };
  }

  @Get('deep-stock/runs/:runId/report')
  async getRunReport(
    @Param() params: RunParamDto,
    @Req() req: { traceId?: string; headers?: Record<string, string | undefined> },
  ) {
    const data = await this.analysisService.getRunReport(params.runId);
    const traceId = req.traceId || req.headers?.['x-trace-id'] || req.headers?.['x-request-id'] || 'UNKNOWN';
    return { success: true, data, traceId: String(traceId) };
  }
}
