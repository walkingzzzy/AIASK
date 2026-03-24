import { Body, Controller, Get, Post, Query, Req } from '@nestjs/common';
import { IsArray, IsBoolean, IsIn, IsInt, IsNumber, IsObject, IsOptional, IsString, Max, Min } from 'class-validator';
import { Type } from 'class-transformer';
import { FactorService } from './factor.service';
import { Roles } from '../rbac/roles.decorator';

class CalculateFactorDto {
  @IsString()
  factor_name!: string;

  @IsArray()
  @IsString({ each: true })
  stock_codes!: string[];

  @IsOptional()
  @IsString()
  start_date?: string;

  @IsOptional()
  @IsString()
  end_date?: string;
}

class CalculateIcDto {
  @IsString()
  factor_name!: string;

  @IsArray()
  @IsString({ each: true })
  stock_codes!: string[];
}

class BacktestFactorDto {
  @IsString()
  factor_name!: string;

  @IsArray()
  @IsString({ each: true })
  stock_codes!: string[];

  @IsOptional()
  @IsString()
  start_date?: string;

  @IsOptional()
  @IsString()
  end_date?: string;
}

class ValidateOosDto {
  @IsString()
  factor_name!: string;

  @IsArray()
  @IsString({ each: true })
  stock_codes!: string[];

  @IsOptional()
  @IsString()
  start_date?: string;

  @IsOptional()
  @IsString()
  end_date?: string;
}

class RobustnessCheckDto {
  @IsString()
  factor_name!: string;

  @IsArray()
  @IsString({ each: true })
  stock_codes!: string[];

  @IsOptional()
  @IsString()
  start_date?: string;

  @IsOptional()
  @IsString()
  end_date?: string;
}

class BatchComputeDto {
  @IsArray() @IsString({ each: true }) codes!: string[];
  @IsOptional() @IsArray() @IsString({ each: true }) factors?: string[];
  @IsOptional() @Type(() => Boolean) @IsBoolean() persist?: boolean;
  @IsOptional() @Type(() => Boolean) @IsBoolean() compute_ic?: boolean;
  @IsOptional() @Type(() => Number) @IsInt() @Min(1) @Max(60) period?: number;
}

class LlmFactorMiningDto {
  @IsArray()
  @IsString({ each: true })
  stock_codes!: string[];

  @IsOptional() @Type(() => Number) @IsInt() @Min(1) @Max(16) candidate_count?: number;
  @IsOptional() @Type(() => Number) @IsInt() @Min(120) @Max(360) lookback_bars?: number;
  @IsOptional() @Type(() => Number) @IsInt() @Min(7) @Max(90) alternative_lookback_days?: number;
  @IsOptional() @Type(() => Boolean) @IsBoolean() allow_fallback?: boolean;
  @IsOptional() @Type(() => Boolean) @IsBoolean() persist_artifact?: boolean;
  @IsOptional() @IsString() artifact_id?: string;
  @IsOptional() @IsString() dedup_mode?: string;
  @IsOptional() @Type(() => Number) @IsNumber() dedup_high_similarity_threshold?: number;
  @IsOptional() @Type(() => Number) @IsNumber() dedup_failure_similarity_threshold?: number;
  @IsOptional() @Type(() => Boolean) @IsBoolean() startup_warmup?: boolean;
  @IsOptional() @Type(() => Boolean) @IsBoolean() startup_warmup_force?: boolean;
  @IsOptional() @Type(() => Number) @IsInt() @Min(1) @Max(20) startup_warmup_limit?: number;
  @IsOptional() @IsString() startup_warmup_task_type?: string;
}

class ValidateCandidateDto {
  @IsOptional() @IsString() artifact_id?: string;
  @IsOptional() @Type(() => Number) @IsInt() @Min(0) candidate_index?: number;
  @IsOptional() @IsObject() candidate?: Record<string, unknown>;
  @IsOptional() @IsArray() @IsString({ each: true }) stock_codes?: string[];
  @IsOptional() @Type(() => Number) @IsInt() @Min(120) @Max(500) lookback_bars?: number;
  @IsOptional() @Type(() => Number) @IsInt() @Min(3) @Max(30) horizon_days?: number;
  @IsOptional() @Type(() => Number) @IsInt() @Min(20) @Max(120) max_dates?: number;
  @IsOptional() @Type(() => Boolean) @IsBoolean() persist_artifact?: boolean;
  @IsOptional() @Type(() => Boolean) @IsBoolean() write_memory?: boolean;
  @IsOptional() @IsString() output_artifact_id?: string;
}

class FactorResearchMemoryDto {
  @IsOptional() @IsString() @IsIn(['list', 'get', 'recall', 'stats']) op?: string;
  @IsOptional() @IsString() artifact_id?: string;
  @IsOptional() @IsObject() candidate?: Record<string, unknown>;
  @IsOptional() @IsString() query_text?: string;
  @IsOptional() @IsArray() @IsString({ each: true }) stock_codes?: string[];
  @IsOptional() @IsString() status?: string;
  @IsOptional() @IsString() family?: string;
  @IsOptional() @Type(() => Number) @IsInt() @Min(1) @Max(500) limit?: number;
}

class FactorCandidateRegistryDto {
  @IsOptional() @IsString() @IsIn(['list', 'get', 'summary', 'active_pool']) op?: string;
  @IsOptional() @IsString() artifact_id?: string;
  @IsOptional() @IsArray() @IsString({ each: true }) stock_codes?: string[];
  @IsOptional() @IsString() family?: string;
  @IsOptional() @IsString() grade?: string;
  @IsOptional() @IsString() recommendation?: string;
  @IsOptional() @Type(() => Number) @IsNumber() min_score?: number;
  @IsOptional() @Type(() => Boolean) @IsBoolean() only_active?: boolean;
  @IsOptional() @Type(() => Number) @IsInt() @Min(1) @Max(500) limit?: number;
}

class ReplayFactorEpisodeDto {
  @IsOptional() @IsString() @IsIn(['run', 'get', 'list', 'summary']) op?: string;
  @IsOptional() @IsString() artifact_id?: string;
  @IsOptional() @IsString() source_artifact_id?: string;
  @IsOptional() @IsArray() @IsString({ each: true }) stock_codes?: string[];
  @IsOptional() @Type(() => Number) @IsInt() @Min(1) @Max(100) candidate_limit?: number;
  @IsOptional() @Type(() => Number) @IsInt() @Min(120) @Max(500) lookback_bars?: number;
  @IsOptional() @Type(() => Number) @IsInt() @Min(3) @Max(30) horizon_days?: number;
  @IsOptional() @Type(() => Number) @IsInt() @Min(20) @Max(120) max_dates?: number;
  @IsOptional() @Type(() => Boolean) @IsBoolean() write_memory?: boolean;
  @IsOptional() @Type(() => Boolean) @IsBoolean() persist_artifact?: boolean;
  @IsOptional() @IsString() output_artifact_id?: string;
  @IsOptional() @Type(() => Number) @IsInt() @Min(1) @Max(500) limit?: number;
}

@Controller('factor')
export class FactorController {
  constructor(private readonly factorService: FactorService) {}

  @Get('library')
  async getLibrary(@Req() req: { traceId?: string; headers?: Record<string, string | undefined> }) {
    const data = await this.factorService.getLibrary();
    const traceId = req.traceId || req.headers?.['x-trace-id'] || req.headers?.['x-request-id'] || 'UNKNOWN';
    return { success: true, data, traceId: String(traceId) };
  }

  @Post('calculate')
  async calculateFactor(
    @Body() body: CalculateFactorDto,
    @Req() req: { traceId?: string; headers?: Record<string, string | undefined> },
  ) {
    const data = await this.factorService.calculateFactor(body);
    const traceId = req.traceId || req.headers?.['x-trace-id'] || req.headers?.['x-request-id'] || 'UNKNOWN';
    return { success: true, data, traceId: String(traceId) };
  }

  @Get('ic-history')
  async icHistory(
    @Query('factor_name') factorName: string,
    @Query('period') period: string,
    @Query('limit') limit: string,
    @Req() req: { traceId?: string; headers?: Record<string, string | undefined> },
  ) {
    const data = await this.factorService.icHistory({
      factor_name: factorName,
      period: period || '20',
      limit: limit ? Number(limit) : 60,
    });
    const traceId = req.traceId || req.headers?.['x-trace-id'] || req.headers?.['x-request-id'] || 'UNKNOWN';
    return { success: true, data, traceId: String(traceId) };
  }

  @Get('decay')
  async decay(
    @Query('factor_name') factorName: string,
    @Query('period') period: string,
    @Query('limit') limit: string,
    @Req() req: { traceId?: string; headers?: Record<string, string | undefined> },
  ) {
    const data = await this.factorService.decay({
      factor_name: factorName,
      period: period || '20',
      limit: limit ? Number(limit) : 60,
    });
    const traceId = req.traceId || req.headers?.['x-trace-id'] || req.headers?.['x-request-id'] || 'UNKNOWN';
    return { success: true, data, traceId: String(traceId) };
  }

  @Post('ic')
  async calculateIc(
    @Body() body: CalculateIcDto,
    @Req() req: { traceId?: string; headers?: Record<string, string | undefined> },
  ) {
    const data = await this.factorService.calculateIc(body);
    const traceId = req.traceId || req.headers?.['x-trace-id'] || req.headers?.['x-request-id'] || 'UNKNOWN';
    return { success: true, data, traceId: String(traceId) };
  }

  @Post('backtest')
  async backtestFactor(
    @Body() body: BacktestFactorDto,
    @Req() req: { traceId?: string; headers?: Record<string, string | undefined> },
  ) {
    const data = await this.factorService.backtestFactor(body);
    const traceId = req.traceId || req.headers?.['x-trace-id'] || req.headers?.['x-request-id'] || 'UNKNOWN';
    return { success: true, data, traceId: String(traceId) };
  }

  @Post('validate-oos')
  async validateOos(
    @Body() body: ValidateOosDto,
    @Req() req: { traceId?: string; headers?: Record<string, string | undefined> },
  ) {
    const data = await this.factorService.validateOos(body);
    const traceId = req.traceId || req.headers?.['x-trace-id'] || req.headers?.['x-request-id'] || 'UNKNOWN';
    return { success: true, data, traceId: String(traceId) };
  }

  @Post('robustness-check')
  async robustnessCheck(
    @Body() body: RobustnessCheckDto,
    @Req() req: { traceId?: string; headers?: Record<string, string | undefined> },
  ) {
    const data = await this.factorService.robustnessCheck(body);
    const traceId = req.traceId || req.headers?.['x-trace-id'] || req.headers?.['x-request-id'] || 'UNKNOWN';
    return { success: true, data, traceId: String(traceId) };
  }

  @Post('batch-compute')
  async batchCompute(
    @Body() body: BatchComputeDto,
    @Req() req: { traceId?: string; headers?: Record<string, string | undefined> },
  ) {
    const data = await this.factorService.batchCompute(body);
    const traceId = req.traceId || req.headers?.['x-trace-id'] || req.headers?.['x-request-id'] || 'UNKNOWN';
    return { success: true, data, traceId: String(traceId) };
  }

  @Post('llm-mining')
  async llmFactorMining(
    @Body() body: LlmFactorMiningDto,
    @Req() req: { traceId?: string; headers?: Record<string, string | undefined> },
  ) {
    const data = await this.factorService.llmFactorMining(body);
    const traceId = req.traceId || req.headers?.['x-trace-id'] || req.headers?.['x-request-id'] || 'UNKNOWN';
    return { success: true, data, traceId: String(traceId) };
  }

  @Post('validate-candidate')
  async validateCandidate(
    @Body() body: ValidateCandidateDto,
    @Req() req: { traceId?: string; headers?: Record<string, string | undefined> },
  ) {
    const data = await this.factorService.validateCandidate(body);
    const traceId = req.traceId || req.headers?.['x-trace-id'] || req.headers?.['x-request-id'] || 'UNKNOWN';
    return { success: true, data, traceId: String(traceId) };
  }

  @Post('research-memory')
  async factorResearchMemory(
    @Body() body: FactorResearchMemoryDto,
    @Req() req: { traceId?: string; headers?: Record<string, string | undefined> },
  ) {
    const data = await this.factorService.factorResearchMemory(body);
    const traceId = req.traceId || req.headers?.['x-trace-id'] || req.headers?.['x-request-id'] || 'UNKNOWN';
    return { success: true, data, traceId: String(traceId) };
  }

  @Post('candidate-registry')
  async factorCandidateRegistry(
    @Body() body: FactorCandidateRegistryDto,
    @Req() req: { traceId?: string; headers?: Record<string, string | undefined> },
  ) {
    const data = await this.factorService.factorCandidateRegistry(body);
    const traceId = req.traceId || req.headers?.['x-trace-id'] || req.headers?.['x-request-id'] || 'UNKNOWN';
    return { success: true, data, traceId: String(traceId) };
  }

  @Post('replay-episode')
  async replayFactorEpisode(
    @Body() body: ReplayFactorEpisodeDto,
    @Req() req: { traceId?: string; headers?: Record<string, string | undefined> },
  ) {
    const data = await this.factorService.replayFactorEpisode(body);
    const traceId = req.traceId || req.headers?.['x-trace-id'] || req.headers?.['x-request-id'] || 'UNKNOWN';
    return { success: true, data, traceId: String(traceId) };
  }

  @Get('scheduler-status')
  async schedulerStatus(@Req() req: { traceId?: string; headers?: Record<string, string | undefined> }) {
    const data = await this.factorService.schedulerStatus();
    const traceId = req.traceId || req.headers?.['x-trace-id'] || req.headers?.['x-request-id'] || 'UNKNOWN';
    return { success: true, data, traceId: String(traceId) };
  }

  @Post('scheduler-run-now')
  @Roles('admin')
  async schedulerRunNow(@Req() req: { traceId?: string; headers?: Record<string, string | undefined> }) {
    const data = await this.factorService.schedulerRunNow();
    const traceId = req.traceId || req.headers?.['x-trace-id'] || req.headers?.['x-request-id'] || 'UNKNOWN';
    return { success: true, data, traceId: String(traceId) };
  }
}
