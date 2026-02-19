import { Body, Controller, Get, Post, Req } from '@nestjs/common';
import { IsArray, IsNumber, IsOptional, IsString, Matches } from 'class-validator';
import { TechnicalService } from './technical.service';

class IndicatorsDto {
  @IsString() @Matches(/^\d{6}$/) code!: string;
  @IsArray() indicators!: string[];
  @IsOptional() @IsString() period?: string;
  @IsOptional() @IsNumber() limit?: number;
}

class PatternsDto {
  @IsString() @Matches(/^\d{6}$/) code!: string;
  @IsOptional() @IsString() period?: string;
  @IsOptional() @IsNumber() limit?: number;
}

@Controller('technical')
export class TechnicalController {
  constructor(private readonly technicalService: TechnicalService) {}

  @Post('indicators')
  async indicators(@Body() body: IndicatorsDto, @Req() req: { traceId?: string; headers?: Record<string, string | undefined> }) {
    const data = await this.technicalService.calculateIndicators(body);
    const traceId = req.traceId || req.headers?.['x-trace-id'] || req.headers?.['x-request-id'] || 'UNKNOWN';
    return { success: true, data, traceId: String(traceId) };
  }

  @Post('patterns')
  async patterns(@Body() body: PatternsDto, @Req() req: { traceId?: string; headers?: Record<string, string | undefined> }) {
    const data = await this.technicalService.checkPatterns(body);
    const traceId = req.traceId || req.headers?.['x-trace-id'] || req.headers?.['x-request-id'] || 'UNKNOWN';
    return { success: true, data, traceId: String(traceId) };
  }

  @Get('available-patterns')
  async availablePatterns(@Req() req: { traceId?: string; headers?: Record<string, string | undefined> }) {
    const data = await this.technicalService.getAvailablePatterns();
    const traceId = req.traceId || req.headers?.['x-trace-id'] || req.headers?.['x-request-id'] || 'UNKNOWN';
    return { success: true, data, traceId: String(traceId) };
  }
}
