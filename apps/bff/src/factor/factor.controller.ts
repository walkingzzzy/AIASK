import { Body, Controller, Get, Post, Query, Req } from '@nestjs/common';
import { IsArray, IsBoolean, IsInt, IsOptional, IsString, Max, Min } from 'class-validator';
import { Type } from 'class-transformer';
import { FactorService } from './factor.service';

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

@Controller('factor')
export class FactorController {
  constructor(private readonly factorService: FactorService) {}

  @Get('library')
  async getLibrary(
    @Req() req: { traceId?: string; headers?: Record<string, string | undefined> },
  ) {
    const data = await this.factorService.getLibrary();
    const traceId =
      req.traceId || req.headers?.['x-trace-id'] || req.headers?.['x-request-id'] || 'UNKNOWN';
    return { success: true, data, traceId: String(traceId) };
  }

  @Post('calculate')
  async calculateFactor(
    @Body() body: CalculateFactorDto,
    @Req() req: { traceId?: string; headers?: Record<string, string | undefined> },
  ) {
    const data = await this.factorService.calculateFactor(body);
    const traceId =
      req.traceId || req.headers?.['x-trace-id'] || req.headers?.['x-request-id'] || 'UNKNOWN';
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
    const traceId =
      req.traceId || req.headers?.['x-trace-id'] || req.headers?.['x-request-id'] || 'UNKNOWN';
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
    const traceId =
      req.traceId || req.headers?.['x-trace-id'] || req.headers?.['x-request-id'] || 'UNKNOWN';
    return { success: true, data, traceId: String(traceId) };
  }


  @Post('ic')
  async calculateIc(
    @Body() body: CalculateIcDto,
    @Req() req: { traceId?: string; headers?: Record<string, string | undefined> },
  ) {
    const data = await this.factorService.calculateIc(body);
    const traceId =
      req.traceId || req.headers?.['x-trace-id'] || req.headers?.['x-request-id'] || 'UNKNOWN';
    return { success: true, data, traceId: String(traceId) };
  }

  @Post('backtest')
  async backtestFactor(
    @Body() body: BacktestFactorDto,
    @Req() req: { traceId?: string; headers?: Record<string, string | undefined> },
  ) {
    const data = await this.factorService.backtestFactor(body);
    const traceId =
      req.traceId || req.headers?.['x-trace-id'] || req.headers?.['x-request-id'] || 'UNKNOWN';
    return { success: true, data, traceId: String(traceId) };
  }

  @Post('validate-oos')
  async validateOos(
    @Body() body: ValidateOosDto,
    @Req() req: { traceId?: string; headers?: Record<string, string | undefined> },
  ) {
    const data = await this.factorService.validateOos(body);
    const traceId =
      req.traceId || req.headers?.['x-trace-id'] || req.headers?.['x-request-id'] || 'UNKNOWN';
    return { success: true, data, traceId: String(traceId) };
  }

  @Post('robustness-check')
  async robustnessCheck(
    @Body() body: RobustnessCheckDto,
    @Req() req: { traceId?: string; headers?: Record<string, string | undefined> },
  ) {
    const data = await this.factorService.robustnessCheck(body);
    const traceId =
      req.traceId || req.headers?.['x-trace-id'] || req.headers?.['x-request-id'] || 'UNKNOWN';
    return { success: true, data, traceId: String(traceId) };
  }

  @Post('batch-compute')
  async batchCompute(
    @Body() body: BatchComputeDto,
    @Req() req: { traceId?: string; headers?: Record<string, string | undefined> },
  ) {
    const data = await this.factorService.batchCompute(body);
    const traceId =
      req.traceId || req.headers?.['x-trace-id'] || req.headers?.['x-request-id'] || 'UNKNOWN';
    return { success: true, data, traceId: String(traceId) };
  }
}
