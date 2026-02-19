import { Body, Controller, Get, Post, Req } from '@nestjs/common';
import { IsArray, IsOptional, IsString } from 'class-validator';
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
    @Body() body: ValidateOosDto,
    @Req() req: { traceId?: string; headers?: Record<string, string | undefined> },
  ) {
    const data = await this.factorService.robustnessCheck(body);
    const traceId =
      req.traceId || req.headers?.['x-trace-id'] || req.headers?.['x-request-id'] || 'UNKNOWN';
    return { success: true, data, traceId: String(traceId) };
  }
}
