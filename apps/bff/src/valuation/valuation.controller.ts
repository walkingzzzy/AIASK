import { Body, Controller, Post, Req } from '@nestjs/common';
import { IsArray, IsNumber, IsOptional, IsString, Matches } from 'class-validator';
import { ValuationService } from './valuation.service';

class DcfDto {
  @IsString() @Matches(/^\d{6}$/) code!: string;
  @IsOptional() @IsNumber() discountRate?: number;
  @IsOptional() @IsNumber() growthRate?: number;
  @IsOptional() @IsNumber() years?: number;
}

class DdmDto {
  @IsString() @Matches(/^\d{6}$/) code!: string;
  @IsOptional() @IsNumber() dividend?: number;
  @IsOptional() @IsNumber() growthRate?: number;
  @IsOptional() @IsNumber() requiredReturn?: number;
}

class RelativeDto {
  @IsString() @Matches(/^\d{6}$/) code!: string;
  @IsOptional() @IsArray() metrics?: string[];
  @IsOptional() @IsArray() peers?: string[];
}

class ScenarioDcfDto {
  @IsString() @Matches(/^\d{6}$/) code!: string;
  @IsOptional() @IsNumber() baseRevenue?: number;
  @IsOptional() @IsString() industry?: string;
  @IsOptional() @IsNumber() years?: number;
}

@Controller('valuation')
export class ValuationController {
  constructor(private readonly valuationService: ValuationService) {}

  @Post('dcf')
  async dcf(@Body() body: DcfDto, @Req() req: { traceId?: string; headers?: Record<string, string | undefined> }) {
    const data = await this.valuationService.dcf(body);
    const traceId = req.traceId || req.headers?.['x-trace-id'] || req.headers?.['x-request-id'] || 'UNKNOWN';
    return { success: true, data, traceId: String(traceId) };
  }

  @Post('ddm')
  async ddm(@Body() body: DdmDto, @Req() req: { traceId?: string; headers?: Record<string, string | undefined> }) {
    const data = await this.valuationService.ddm(body);
    const traceId = req.traceId || req.headers?.['x-trace-id'] || req.headers?.['x-request-id'] || 'UNKNOWN';
    return { success: true, data, traceId: String(traceId) };
  }

  @Post('relative')
  async relative(@Body() body: RelativeDto, @Req() req: { traceId?: string; headers?: Record<string, string | undefined> }) {
    const data = await this.valuationService.relative(body);
    const traceId = req.traceId || req.headers?.['x-trace-id'] || req.headers?.['x-request-id'] || 'UNKNOWN';
    return { success: true, data, traceId: String(traceId) };
  }

  @Post('scenario-dcf')
  async scenarioDcf(@Body() body: ScenarioDcfDto, @Req() req: { traceId?: string; headers?: Record<string, string | undefined> }) {
    const data = await this.valuationService.scenarioDcf(body);
    const traceId = req.traceId || req.headers?.['x-trace-id'] || req.headers?.['x-request-id'] || 'UNKNOWN';
    return { success: true, data, traceId: String(traceId) };
  }
}