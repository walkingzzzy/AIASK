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

type TraceRequest = {
  traceId?: string;
  headers?: Record<string, string | undefined>;
};

@Controller('fundamental')
export class FundamentalController {
  constructor(private readonly fundamentalService: FundamentalService) {}

  private getTraceId(req: TraceRequest) {
    return String(
      req.traceId || req.headers?.['x-trace-id'] || req.headers?.['x-request-id'] || 'UNKNOWN',
    );
  }

  @Get('overview')
  async getOverview(@Query() query: FundamentalQueryDto, @Req() req: TraceRequest) {
    const data = await this.fundamentalService.getOverview(query.code);
    return { success: true, data, traceId: this.getTraceId(req) };
  }

  @Get('history')
  async getHistory(@Query() query: FundamentalHistoryQueryDto, @Req() req: TraceRequest) {
    const days = query.days ? Number(query.days) : 90;
    const data = await this.fundamentalService.getHistory(query.code, days);
    return { success: true, data, traceId: this.getTraceId(req) };
  }

  @Get('capital')
  async getCapital(@Query() query: FundamentalQueryDto, @Req() req: TraceRequest) {
    const data = await this.fundamentalService.getCapital(query.code);
    return { success: true, data, traceId: this.getTraceId(req) };
  }

  @Get('peers')
  async getPeers(@Query() query: FundamentalQueryDto, @Req() req: TraceRequest) {
    const data = await this.fundamentalService.getPeers(query.code);
    return { success: true, data, traceId: this.getTraceId(req) };
  }

  @Get('stock-info')
  async getStockInfo(@Query() query: FundamentalQueryDto, @Req() req: TraceRequest) {
    const data = await this.fundamentalService.getStockInfo(query.code);
    return { success: true, data, traceId: this.getTraceId(req) };
  }

  @Get('financial-snapshot')
  async getFinancialSnapshot(@Query() query: FundamentalQueryDto, @Req() req: TraceRequest) {
    const data = await this.fundamentalService.getFinancialSnapshot(query.code);
    return { success: true, data, traceId: this.getTraceId(req) };
  }

  @Post('financial-history')
  async getFinancialHistory(@Body() body: FinancialHistoryDto, @Req() req: TraceRequest) {
    const data = await this.fundamentalService.getFinancialHistory(body.codes, body.fields, body.date);
    return { success: true, data, traceId: this.getTraceId(req) };
  }

  @Get('f10')
  async getF10(@Query() query: FundamentalQueryDto, @Req() req: TraceRequest) {
    const data = await this.fundamentalService.getF10Info(query.code);
    return { success: true, data, traceId: this.getTraceId(req) };
  }
}
