import { Body, Controller, Get, Post, Query, Req } from '@nestjs/common';
import { IsArray, ArrayMinSize, IsOptional, IsString, Matches } from 'class-validator';
import { FundamentalService } from './fundamental.service';

class FundamentalQueryDto {
  @IsString()
  @Matches(/^\d{6}$/, { message: 'code 必须为 6 位数字' })
  code!: string;
}

class FundamentalHistoryQueryDto extends FundamentalQueryDto {
  @IsOptional()
  @IsString()
  @Matches(/^\d+$/, { message: 'days 必须为正整数' })
  days?: string;
}

class FinancialHistoryDto {
  @IsArray() @ArrayMinSize(1) codes!: string[];
  @IsArray() @ArrayMinSize(1) fields!: string[];
  @IsString() date!: string;
}

@Controller('fundamental')
export class FundamentalController {
  constructor(private readonly fundamentalService: FundamentalService) {}

  @Get('overview')
  async getOverview(
    @Query() query: FundamentalQueryDto,
    @Req() req: { traceId?: string; headers?: Record<string, string | undefined> },
  ) {
    const data = await this.fundamentalService.getOverview(query.code);
    const traceId =
      req.traceId || req.headers?.['x-trace-id'] || req.headers?.['x-request-id'] || 'UNKNOWN';

    return {
      success: true,
      data,
      traceId: String(traceId),
    };
  }

  @Get('history')
  async getHistory(
    @Query() query: FundamentalHistoryQueryDto,
    @Req() req: { traceId?: string; headers?: Record<string, string | undefined> },
  ) {
    const days = query.days ? Number(query.days) : 90;
    const data = await this.fundamentalService.getHistory(query.code, days);
    const traceId =
      req.traceId || req.headers?.['x-trace-id'] || req.headers?.['x-request-id'] || 'UNKNOWN';

    return {
      success: true,
      data,
      traceId: String(traceId),
    };
  }

  @Get('capital')
  async getCapital(
    @Query() query: FundamentalQueryDto,
    @Req() req: { traceId?: string; headers?: Record<string, string | undefined> },
  ) {
    const data = await this.fundamentalService.getCapital(query.code);
    const traceId =
      req.traceId || req.headers?.['x-trace-id'] || req.headers?.['x-request-id'] || 'UNKNOWN';

    return {
      success: true,
      data,
      traceId: String(traceId),
    };
  }

  @Get('peers')
  async getPeers(
    @Query() query: FundamentalQueryDto,
    @Req() req: { traceId?: string; headers?: Record<string, string | undefined> },
  ) {
    const data = await this.fundamentalService.getPeers(query.code);
    const traceId =
      req.traceId || req.headers?.['x-trace-id'] || req.headers?.['x-request-id'] || 'UNKNOWN';

    return {
      success: true,
      data,
      traceId: String(traceId),
    };
  }

  @Get('stock-info')
  async getStockInfo(@Query() query: FundamentalQueryDto, @Req() req: any) {
    const data = await this.fundamentalService.getStockInfo(query.code);
    const traceId = req.traceId || req.headers?.['x-trace-id'] || req.headers?.['x-request-id'] || 'UNKNOWN';
    return { success: true, data, traceId: String(traceId) };
  }

  @Get('financial-snapshot')
  async getFinancialSnapshot(@Query() query: FundamentalQueryDto, @Req() req: any) {
    const data = await this.fundamentalService.getFinancialSnapshot(query.code);
    const traceId = req.traceId || req.headers?.['x-trace-id'] || req.headers?.['x-request-id'] || 'UNKNOWN';
    return { success: true, data, traceId: String(traceId) };
  }

  @Post('financial-history')
  async getFinancialHistory(@Body() body: FinancialHistoryDto, @Req() req: any) {
    const data = await this.fundamentalService.getFinancialHistory(body.codes, body.fields, body.date);
    const traceId = req.traceId || req.headers?.['x-trace-id'] || req.headers?.['x-request-id'] || 'UNKNOWN';
    return { success: true, data, traceId: String(traceId) };
  }

  @Get('f10')
  async getF10(@Query() query: FundamentalQueryDto, @Req() req: any) {
    const data = await this.fundamentalService.getF10Info(query.code);
    const traceId = req.traceId || req.headers?.['x-trace-id'] || req.headers?.['x-request-id'] || 'UNKNOWN';
    return { success: true, data, traceId: String(traceId) };
  }
}
