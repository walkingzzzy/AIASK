import { Controller, Get, Query, Req } from '@nestjs/common';
import { Type } from 'class-transformer';
import { IsArray, IsBoolean, IsInt, IsOptional, IsString, Matches, Min } from 'class-validator';
import { DataService } from './data.service';

class OptionChainDto {
  @IsString() underlying!: string;
  @IsOptional() @IsString() expiryMonth?: string;
  @IsOptional() @Type(() => Number) @IsInt() @Min(1) limit?: number;
}

class TradingDatesDto {
  @IsOptional() @IsString() startDate?: string;
  @IsOptional() @IsString() endDate?: string;
  @IsOptional() @Type(() => Number) @IsInt() @Min(1) count?: number;
}

class IpoDto {
  @IsOptional() @IsString() ipoType?: string;
  @IsOptional() @IsBoolean() includeFuture?: boolean;
}

class CbDto {
  @IsString() code!: string;
}

class StockCapitalDto {
  @IsString() @Matches(/^\d{6}$/) code!: string;
  @IsOptional() @IsArray() dates?: string[];
}

@Controller('data')
export class DataController {
  constructor(private readonly dataService: DataService) {}

  @Get('option-chain')
  async optionChain(@Query() query: OptionChainDto, @Req() req: { traceId?: string; headers?: Record<string, string | undefined> }) {
    const data = await this.dataService.getOptionChain(query);
    const traceId = req.traceId || req.headers?.['x-trace-id'] || req.headers?.['x-request-id'] || 'UNKNOWN';
    return { success: true, data, traceId: String(traceId) };
  }

  @Get('trading-dates')
  async tradingDates(@Query() query: TradingDatesDto, @Req() req: { traceId?: string; headers?: Record<string, string | undefined> }) {
    const data = await this.dataService.getTradingDates(query);
    const traceId = req.traceId || req.headers?.['x-trace-id'] || req.headers?.['x-request-id'] || 'UNKNOWN';
    return { success: true, data, traceId: String(traceId) };
  }

  @Get('ipo')
  async ipo(@Query() query: IpoDto, @Req() req: { traceId?: string; headers?: Record<string, string | undefined> }) {
    const data = await this.dataService.getIpoInfo(query);
    const traceId = req.traceId || req.headers?.['x-trace-id'] || req.headers?.['x-request-id'] || 'UNKNOWN';
    return { success: true, data, traceId: String(traceId) };
  }

  @Get('cb')
  async cb(@Query() query: CbDto, @Req() req: { traceId?: string; headers?: Record<string, string | undefined> }) {
    const data = await this.dataService.getCbInfo(query.code);
    const traceId = req.traceId || req.headers?.['x-trace-id'] || req.headers?.['x-request-id'] || 'UNKNOWN';
    return { success: true, data, traceId: String(traceId) };
  }

  @Get('capital')
  async capital(@Query() query: StockCapitalDto, @Req() req: { traceId?: string; headers?: Record<string, string | undefined> }) {
    const data = await this.dataService.getStockCapital(query);
    const traceId = req.traceId || req.headers?.['x-trace-id'] || req.headers?.['x-request-id'] || 'UNKNOWN';
    return { success: true, data, traceId: String(traceId) };
  }
}
